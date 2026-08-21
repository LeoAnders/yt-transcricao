"""Testes da transcrição pura — `transcricao.py` e a rota `/api/transcrever`.

`unittest` da biblioteca padrão, não pytest: o projeto tem zero dependência
de `pip` por decisão (rede corporativa com proxy autenticado devolve 407), e
uma suíte que exigisse `pip install` seria instalável em menos máquinas do que
a própria ferramenta.

Nada aqui toca a rede: `transcrever.baixar_legendas` é substituído por um
dublê que grava um `.vtt` de mentira na pasta que receber.

Rodar:

    python -m unittest discover -s testes -v
"""

from __future__ import annotations

import ast
import json
import sys
import textwrap
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import console  # noqa: E402
import transcrever  # noqa: E402
import transcricao as tr  # noqa: E402

# Legenda automática como o YouTube entrega: modo rolante, com tag por
# palavra e a linha anterior repetida no bloco seguinte.
VTT = """WEBVTT
Kind: captions
Language: pt

00:00:00.000 --> 00:00:02.500
primeira <c>fala</c> do vídeo

00:00:02.500 --> 00:00:05.000
primeira fala do vídeo
segunda fala <00:00:03.100>agora

00:00:40.000 --> 00:00:43.000
já passou dos trinta segundos
"""


class DubleDeLegenda:
    """Substitui `transcrever.baixar_legendas` sem tocar a rede."""

    def __init__(self, conteudo: str | None = VTT,
                 nome: str = "dQw4w9WgXcQ - Aula de HLS.pt-orig.vtt"):
        self.conteudo = conteudo
        self.nome = nome
        self.chamadas: list[tuple] = []

    def __call__(self, urls, pasta, proxy, idioma, com_fallback=True):
        self.chamadas.append((tuple(urls), idioma))
        if self.conteudo is None:
            return list(urls)  # nenhuma legenda: devolve os pendentes
        (Path(pasta) / self.nome).write_text(self.conteudo, encoding="utf-8")
        return []


class BaseComDuble(unittest.TestCase):
    """Troca as dependências de rede e devolve tudo ao normal no fim."""

    def setUp(self) -> None:
        self.duble = DubleDeLegenda()
        self._baixar = transcrever.baixar_legendas
        self._proxy = transcrever.detectar_proxy
        transcrever.baixar_legendas = self.duble
        transcrever.detectar_proxy = lambda: None

    def tearDown(self) -> None:
        transcrever.baixar_legendas = self._baixar
        transcrever.detectar_proxy = self._proxy


class TestObter(BaseComDuble):
    def test_devolve_dados_da_transcricao(self) -> None:
        dados = tr.obter("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

        self.assertEqual(dados["videoId"], "dQw4w9WgXcQ")
        self.assertEqual(dados["titulo"], "Aula de HLS")
        self.assertEqual(dados["url"], "https://youtu.be/dQw4w9WgXcQ")
        self.assertEqual(dados["origem"], "youtube_auto_caption")
        self.assertEqual(dados["idioma"], "pt")
        self.assertIn("primeira fala do vídeo", dados["texto"])

    def test_remove_tags_e_repeticao_da_legenda_rolante(self) -> None:
        texto = tr.obter("dQw4w9WgXcQ")["texto"]

        self.assertNotIn("<c>", texto)
        self.assertEqual(texto.count("primeira fala do vídeo"), 1)

    def test_paragrafos_carregam_o_segundo_de_inicio(self) -> None:
        paragrafos = tr.obter("dQw4w9WgXcQ")["paragrafos"]

        self.assertEqual(paragrafos[0]["segundo"], 0)
        # A janela de agrupamento é de 30s, então os 40s abrem parágrafo novo.
        self.assertEqual(len(paragrafos), 2)
        self.assertEqual(paragrafos[1]["segundo"], 40)

    def test_com_timestamps_desligado_devolve_texto_corrido(self) -> None:
        texto = tr.obter("dQw4w9WgXcQ", com_timestamps=False)["texto"]
        self.assertNotIn("(00:00)", texto)

    def test_aceita_todas_as_formas_de_link(self) -> None:
        for entrada in (
            "https://youtu.be/dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
            "dQw4w9WgXcQ",
        ):
            with self.subTest(entrada=entrada):
                self.assertEqual(tr.obter(entrada)["videoId"], "dQw4w9WgXcQ")

    def test_url_que_nao_e_video_levanta_VideoInvalido(self) -> None:
        with self.assertRaises(tr.VideoInvalido):
            tr.obter("https://vimeo.com/123456")

    def test_video_sem_legenda_levanta_SemLegenda(self) -> None:
        self.duble.conteudo = None
        with self.assertRaises(tr.SemLegenda):
            tr.obter("dQw4w9WgXcQ")

    def test_legenda_baixada_mas_sem_arquivo_tambem_e_SemLegenda(self) -> None:
        # baixar_legendas diz que não sobrou pendente, mas não gravou nada.
        self.duble.__call__ = None  # type: ignore[assignment]
        transcrever.baixar_legendas = lambda urls, pasta, proxy, idioma, com_fallback=True: []
        with self.assertRaises(tr.SemLegenda):
            tr.obter("dQw4w9WgXcQ")

    def test_reporta_o_idioma_real_quando_houve_fallback(self) -> None:
        # Pedimos pt, o vídeo só tinha en: o sufixo do arquivo é a verdade.
        self.duble.nome = "dQw4w9WgXcQ - Aula de HLS.en.vtt"
        self.assertEqual(tr.obter("dQw4w9WgXcQ", idioma="pt")["idioma"], "en")

    def test_nao_deixa_o_vtt_em_transcricoes(self) -> None:
        antes = set(p.name for p in (RAIZ / "transcricoes").glob("*.vtt"))
        tr.obter("dQw4w9WgXcQ")
        depois = set(p.name for p in (RAIZ / "transcricoes").glob("*.vtt"))
        self.assertEqual(antes, depois)


class TestSemLLM(unittest.TestCase):
    """O requisito central: este caminho não invoca modelo nenhum.

    A verificação é sobre a **AST**, não sobre o texto do arquivo: comentário e
    docstring falam de `redigir.py` e do Claude justamente para explicar por
    que eles não estão aqui, e um teste que procurasse a palavra crua
    reprovaria a documentação da própria decisão.
    """

    @staticmethod
    def _arvore(arquivo: str) -> ast.AST:
        return ast.parse((RAIZ / arquivo).read_text(encoding="utf-8"))

    @staticmethod
    def _nomes_importados(arvore: ast.AST) -> set[str]:
        nomes: set[str] = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                nomes.update(a.name.split(".")[0] for a in no.names)
            elif isinstance(no, ast.ImportFrom) and no.module:
                nomes.add(no.module.split(".")[0])
        return nomes

    @staticmethod
    def _chamadas(no: ast.AST) -> set[str]:
        """Nomes chamados no trecho, em forma pontuada (`tr.obter`, `red.redigir`)."""
        chamadas: set[str] = set()
        for filho in ast.walk(no):
            if isinstance(filho, ast.Call):
                chamadas.add(ast.unparse(filho.func))
        return chamadas

    def test_transcricao_py_nao_importa_llm_nem_subprocess(self) -> None:
        importados = self._nomes_importados(self._arvore("transcricao.py"))
        self.assertEqual(importados & {"redigir", "subprocess", "anthropic", "openai"}, set())
        # E importa exatamente o que deve compor.
        self.assertLessEqual({"descobrir", "limpar", "transcrever"}, importados)

    def test_o_corpo_de_transcrever_so_chama_transcricao_obter(self) -> None:
        arvore = self._arvore("console.py")
        funcao = next(
            no
            for no in ast.walk(arvore)
            if isinstance(no, ast.FunctionDef) and no.name == "_transcrever"
        )
        chamadas = self._chamadas(funcao)

        self.assertIn("tr.obter", chamadas)
        for proibida in chamadas:
            with self.subTest(chamada=proibida):
                self.assertFalse(
                    proibida.startswith(("red.", "redigir", "subprocess", "transc.")),
                    f"a transcrição pura não pode chamar {proibida}",
                )

    def test_a_rota_de_transcricao_dispara_transcrever_e_nao_gerar(self) -> None:
        """Confere no `do_POST` que `/api/transcrever` aponta para `_transcrever`."""
        fonte = (RAIZ / "console.py").read_text(encoding="utf-8")
        bloco = fonte[
            fonte.index('if rota.path == "/api/transcrever":') :
            fonte.index('if rota.path == "/api/gerar":')
        ]
        arvore = ast.parse(textwrap.dedent(bloco).replace("return", "pass"))
        alvos = {
            ast.unparse(palavra.value)
            for no in ast.walk(arvore)
            if isinstance(no, ast.Call)
            for palavra in no.keywords
            if palavra.arg == "target"
        }
        self.assertEqual(alvos, {"_transcrever"})

    def test_redigir_nao_e_chamado_durante_um_job_de_transcricao(self) -> None:
        """Prova em execução, não só por leitura de código."""
        duble = DubleDeLegenda()
        chamou_redigir = []

        original_baixar = transcrever.baixar_legendas
        original_proxy = transcrever.detectar_proxy
        original_redigir = console.red.redigir
        original_material = console.red.material_de_pasta
        transcrever.baixar_legendas = duble
        transcrever.detectar_proxy = lambda: None
        console.red.redigir = lambda *a, **k: chamou_redigir.append("redigir")
        console.red.material_de_pasta = lambda *a, **k: chamou_redigir.append("material")

        try:
            job = "job-teste"
            console._TRABALHOS[job] = {"estado": "rodando", "linhas": [], "erro": ""}
            console._transcrever(job, "dQw4w9WgXcQ", "pt", True)

            self.assertEqual(console._TRABALHOS[job]["estado"], "pronto")
            self.assertEqual(chamou_redigir, [])
        finally:
            transcrever.baixar_legendas = original_baixar
            transcrever.detectar_proxy = original_proxy
            console.red.redigir = original_redigir
            console.red.material_de_pasta = original_material
            console._TRABALHOS.pop("job-teste", None)


class TestTrabalhoDeTranscricao(BaseComDuble):
    def _rodar(self, job: str, url: str = "dQw4w9WgXcQ") -> dict:
        console._TRABALHOS[job] = {"estado": "rodando", "linhas": [], "erro": ""}
        self.addCleanup(console._TRABALHOS.pop, job, None)
        console._transcrever(job, url, "pt", True)
        return console._TRABALHOS[job]

    def test_sucesso_deixa_o_trabalho_pronto_com_a_transcricao(self) -> None:
        trabalho = self._rodar("t-ok")
        self.assertEqual(trabalho["estado"], "pronto")
        self.assertEqual(trabalho["transcricao"]["videoId"], "dQw4w9WgXcQ")
        self.assertIn("buscando legenda", trabalho["linhas"])

    def test_video_sem_legenda_vira_codigo_sem_legenda(self) -> None:
        self.duble.conteudo = None
        trabalho = self._rodar("t-sem-legenda")
        self.assertEqual(trabalho["estado"], "erro")
        self.assertEqual(trabalho["codigo"], "sem_legenda")

    def test_url_invalida_vira_codigo_video_invalido(self) -> None:
        trabalho = self._rodar("t-url", url="https://vimeo.com/1")
        self.assertEqual(trabalho["estado"], "erro")
        self.assertEqual(trabalho["codigo"], "video_invalido")

    def test_falha_do_processo_vira_codigo_falha_sem_derrubar_a_thread(self) -> None:
        def explodir(*_a, **_k):
            raise RuntimeError("yt-dlp saiu com código 1")

        transcrever.baixar_legendas = explodir
        trabalho = self._rodar("t-falha")
        self.assertEqual(trabalho["estado"], "erro")
        self.assertEqual(trabalho["codigo"], "falha")
        self.assertIn("yt-dlp", trabalho["erro"])


class TestRotaHttp(BaseComDuble):
    """Sobe o servidor de verdade em 127.0.0.1, numa porta efêmera."""

    def setUp(self) -> None:
        super().setUp()
        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), console.Manipulador)
        self.base = f"http://127.0.0.1:{self.servidor.server_address[1]}"
        self.thread = threading.Thread(target=self.servidor.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._parar)

    def _parar(self) -> None:
        self.servidor.shutdown()
        self.servidor.server_close()
        self.thread.join(timeout=5)

    def _chamar(self, pedido: urllib.request.Request) -> tuple[int, dict]:
        """Requisição direta, sem proxy.

        `urlopen` obedece `HTTP_PROXY` do ambiente, e numa máquina com proxy
        corporativo isso manda até `127.0.0.1` para o squid — que responde
        407. O opener com `ProxyHandler({})` é o que faz o teste testar o
        servidor local em vez da rede da empresa.
        """
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(pedido, timeout=10) as resposta:
                return resposta.status, json.loads(resposta.read().decode("utf-8"))
        except urllib.error.HTTPError as erro:
            return erro.code, json.loads(erro.read().decode("utf-8"))

    def _postar(self, rota: str, corpo: dict) -> tuple[int, dict]:
        return self._chamar(
            urllib.request.Request(
                f"{self.base}{rota}",
                data=json.dumps(corpo).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        )

    def _obter(self, rota: str) -> tuple[int, dict]:
        return self._chamar(urllib.request.Request(f"{self.base}{rota}"))

    def _esperar(self, job: str) -> dict:
        for _ in range(200):
            _, corpo = self._obter(f"/api/trabalho?id={job}")
            if corpo.get("estado") != "rodando":
                return corpo
            threading.Event().wait(0.05)
        self.fail("o trabalho não terminou")

    def test_escuta_so_em_loopback(self) -> None:
        self.assertEqual(self.servidor.server_address[0], "127.0.0.1")

    def test_fluxo_completo_devolve_so_a_transcricao(self) -> None:
        status, corpo = self._postar("/api/transcrever", {"url": "dQw4w9WgXcQ"})
        self.assertEqual(status, 200)
        job = corpo["id"]
        self.addCleanup(console._TRABALHOS.pop, job, None)

        resultado = self._esperar(job)
        self.assertEqual(resultado["estado"], "pronto")
        transcricao = resultado["transcricao"]
        self.assertEqual(transcricao["videoId"], "dQw4w9WgXcQ")
        self.assertIn("texto", transcricao)
        # Nada de documento redigido nesta resposta.
        self.assertNotIn("arquivos", resultado)

    def test_sem_url_e_400(self) -> None:
        status, corpo = self._postar("/api/transcrever", {})
        self.assertEqual(status, 400)
        self.assertIn("url", corpo["erro"])

    def test_url_invalida_reporta_video_invalido(self) -> None:
        _, corpo = self._postar("/api/transcrever", {"url": "https://vimeo.com/1"})
        job = corpo["id"]
        self.addCleanup(console._TRABALHOS.pop, job, None)

        resultado = self._esperar(job)
        self.assertEqual(resultado["codigo"], "video_invalido")

    def test_video_sem_legenda_reporta_sem_legenda(self) -> None:
        self.duble.conteudo = None
        _, corpo = self._postar("/api/transcrever", {"url": "dQw4w9WgXcQ"})
        job = corpo["id"]
        self.addCleanup(console._TRABALHOS.pop, job, None)

        resultado = self._esperar(job)
        self.assertEqual(resultado["estado"], "erro")
        self.assertEqual(resultado["codigo"], "sem_legenda")

    def test_trabalho_desconhecido_nao_quebra(self) -> None:
        _, corpo = self._obter("/api/trabalho?id=nao-existe")
        self.assertEqual(corpo["estado"], "desconhecido")

    def test_rota_desconhecida_e_404(self) -> None:
        status, _ = self._postar("/api/nao-existe", {})
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
