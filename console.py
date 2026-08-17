"""Por que este módulo existe.

API HTTP do motor de transcrição — analisar, gerar e ler o resultado por
requisição, para quem não quer chamar `transcrever.py`/`redigir.py` na mão.

**Sem interface embutida.** A interface (React/Vite) mora em outro
repositório, que fala com esta API por HTTP; a fronteira é só isso, não o
formato — este módulo continua não decidindo nada além de orquestrar
`transcrever` e `redigir`, e a entrada continua sendo só link(s) de vídeo do
YouTube (ler artigo de documentação — Outline, Notion — é responsabilidade de
quem chama, via MCP da própria ferramenta de documentação).

**Escopo deliberado: local, um usuário, sem autenticação.** Escuta em
127.0.0.1 e só. Um servidor que atende outras pessoas com a credencial de uma
só é compartilhamento de conta, e a resposta para isso é chave de API da
empresa — outro projeto, outra conta de custo.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import traceback
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import descobrir
import publicar as pub
import redigir as red
import transcrever as transc

RAIZ = Path(__file__).resolve().parent

TIPOS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

# Trabalho em andamento, por id. Uma geração leva minutos: fazê-la dentro do
# handler deixaria quem chamou pendurado até o timeout. O trabalho vai para
# uma thread e quem chamou pergunta o estado.
_TRABALHOS: dict[str, dict] = {}
_TRAVA = threading.Lock()


# --------------------------------------------------------------------------
# trabalho em segundo plano
# --------------------------------------------------------------------------


def _anotar(job: str, linha: str) -> None:
    with _TRAVA:
        _TRABALHOS[job]["linhas"].append(linha)


def _analisar_fonte(texto: str) -> tuple[str, list[str]]:
    """Devolve (título, urls) a partir do que foi colado: um ou mais links de
    vídeo do YouTube. Só essa forma de entrada — ver a nota em descobrir.py.
    """
    urls = descobrir.urls_em_texto(texto) or descobrir.normalizar([texto])
    if not urls:
        raise ValueError("nenhum vídeo do YouTube encontrado no que foi colado")

    proxy = transc.detectar_proxy()
    meta = transc.metadados_do_video(urls[0], proxy)
    primeiro = meta.get("titulo") or f"Vídeo {urls[0].split('v=')[-1]}"
    titulo = primeiro if len(urls) == 1 else f"{primeiro} e mais {len(urls) - 1}"
    return titulo, urls


def _gerar(job: str, texto: str, com_quadros: bool, intervalo: int,
           base_saida: Path) -> None:
    """Baixa (via `transcrever.py`) e redige. Roda numa thread."""
    try:
        _anotar(job, "analisando")
        titulo, urls = _analisar_fonte(texto)
        pasta = base_saida / red._seguro(titulo)
        _anotar(job, f'"{titulo}" — {len(urls)} vídeo(s)')

        comando = [sys.executable, str(RAIZ / "transcrever.py"),
                   *urls, "--saida", str(pasta)]
        if com_quadros:
            comando += ["--quadros", "--intervalo-quadros", str(intervalo)]

        _anotar(job, "baixando legendas" + (" e quadros" if com_quadros else ""))
        # capture_output pelo mesmo motivo do mcp_server: um yt-dlp escrevendo
        # progresso no stdout herdado polui a saída deste processo.
        resultado = subprocess.run(comando, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", cwd=RAIZ)
        if resultado.returncode != 0:
            raise RuntimeError((resultado.stderr or "").strip()[:500]
                               or "transcrever.py falhou")

        _anotar(job, "redigindo")
        material = red.material_de_pasta(
            pasta, titulo=titulo, fonte=", ".join(urls), fonte_tipo="links",
            interno=True, intervalo_quadros=intervalo,
        )
        artigos = red.redigir(material)

        destino = pasta / "documentacao"
        destino.mkdir(parents=True, exist_ok=True)
        arquivos = []
        for artigo in artigos:
            arquivo = destino / f"{red._seguro(artigo.titulo)}.md"
            arquivo.write_text(artigo.markdown(), encoding="utf-8")
            arquivos.append(str(arquivo.relative_to(base_saida)))
            marca = "BLOQUEADO" if artigo.bloqueado else f"{len(artigo.pendencias)} pendência(s)"
            _anotar(job, f"{arquivo.name} [{marca}]")

        with _TRAVA:
            _TRABALHOS[job]["estado"] = "pronto"
            _TRABALHOS[job]["arquivos"] = arquivos
    except Exception as erro:  # noqa: BLE001 — a thread não pode morrer calada
        with _TRAVA:
            _TRABALHOS[job]["estado"] = "erro"
            _TRABALHOS[job]["erro"] = str(erro) or erro.__class__.__name__
        _anotar(job, traceback.format_exc(limit=1).strip().splitlines()[-1])


# --------------------------------------------------------------------------
# leitura do que já foi gerado
# --------------------------------------------------------------------------


def _pendencias_do_texto(corpo: str) -> list[dict]:
    """Lê o bloco `## ⚠️ Conferir antes de usar` de volta.

    O arquivo é a verdade: alguém pode ter editado à mão depois de gerar.
    """
    pendencias = []
    dentro = False
    for linha in corpo.splitlines():
        if linha.startswith("## ") and "Conferir antes de usar" in linha:
            dentro = True
            continue
        if dentro and linha.startswith("## "):
            break
        if dentro and linha.startswith("- "):
            texto = linha[2:].strip()
            pendencias.append({
                "texto": texto,
                "bloqueia": "BLOQUEIA A PUBLICAÇÃO" in texto,
                "linha": linha,
            })
    return pendencias


# --------------------------------------------------------------------------
# servidor
# --------------------------------------------------------------------------


class Manipulador(BaseHTTPRequestHandler):
    base_documentos = Path("transcricoes")

    def _responder(self, dados, codigo: int = 200) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _corpo(self) -> dict:
        tamanho = int(self.headers.get("Content-Length") or 0)
        if not tamanho:
            return {}
        return json.loads(self.rfile.read(tamanho).decode("utf-8"))

    def log_message(self, formato, *args) -> None:
        # o padrão escreve uma linha por requisição, inclusive as de polling —
        # com quem chama perguntando o estado a cada segundo, isso vira ruído
        pass

    # ---------------- GET ----------------

    def do_GET(self) -> None:  # noqa: N802 — nome exigido pela stdlib
        rota = urllib.parse.urlparse(self.path)
        consulta = urllib.parse.parse_qs(rota.query)

        try:
            if rota.path == "/api/documento":
                arquivo = self._arquivo(consulta.get("arquivo", [""])[0])
                artigo = pub.ler_documento(arquivo)
                self._responder({
                    "titulo": artigo.titulo,
                    "corpo": artigo.corpo,
                    "interno": artigo.front_matter.get("interno", True),
                    "pendencias": _pendencias_do_texto(artigo.corpo),
                })
                return

            if rota.path == "/api/midia":
                self._midia(consulta.get("arquivo", [""])[0])
                return

            if rota.path == "/api/trabalho":
                job = consulta.get("id", [""])[0]
                with _TRAVA:
                    self._responder(_TRABALHOS.get(job) or {"estado": "desconhecido"})
                return

            self._responder({"erro": "rota desconhecida"}, 404)

        except ValueError as erro:
            # pedido malformado (caminho fora da base) não é falha do
            # servidor: quem chamou precisa distinguir "você pediu errado" de
            # "quebrou aqui dentro"
            self._responder({"erro": str(erro)}, 400)
        except Exception as erro:  # noqa: BLE001
            self._responder({"erro": str(erro)}, 500)

    # ---------------- POST ----------------

    def do_POST(self) -> None:  # noqa: N802
        rota = urllib.parse.urlparse(self.path)
        try:
            corpo = self._corpo()

            if rota.path == "/api/analisar":
                titulo, urls = _analisar_fonte(corpo["url"])
                self._responder({"titulo": titulo, "videos": urls})
                return

            if rota.path == "/api/gerar":
                job = uuid.uuid4().hex[:12]
                with _TRAVA:
                    _TRABALHOS[job] = {"estado": "rodando", "linhas": [], "erro": ""}
                threading.Thread(
                    target=_gerar,
                    args=(job, corpo["url"], bool(corpo.get("quadros")),
                          int(corpo.get("intervalo") or 10), self.base_documentos),
                    daemon=True,
                ).start()
                self._responder({"id": job})
                return

            self._responder({"erro": "rota desconhecida"}, 404)

        except pub.PublicarErro as erro:
            self._responder({"erro": str(erro)}, 409)
        except Exception as erro:  # noqa: BLE001
            self._responder({"erro": str(erro)}, 500)

    # ---------------- caminhos ----------------

    def _arquivo(self, relativo: str) -> Path:
        """Resolve o caminho e recusa qualquer coisa fora da base.

        Sem isto, `?arquivo=../../.env` lê o token. É servidor local, mas
        local não quer dizer que qualquer página aberta no navegador não possa
        chamar esta rota.
        """
        base = self.base_documentos.resolve()
        alvo = (base / relativo).resolve()
        if not alvo.is_file() or base not in alvo.parents:
            raise ValueError(f"caminho fora da base: {relativo}")
        return alvo

    def _midia(self, relativo: str) -> None:
        """Serve um quadro/imagem de `transcricoes/` — mesma trava do
        `_arquivo`, porque o quadro embutido no artigo aponta para dentro
        dessa base, nunca para fora dela."""
        alvo = self._arquivo(relativo)
        dados = alvo.read_bytes()
        tipo = TIPOS.get(alvo.suffix.lower(), "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)


def main() -> None:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="API HTTP do motor de transcrição — sem interface embutida."
    )
    parser.add_argument("--porta", type=int, default=8765)
    parser.add_argument("--documentos", default="transcricoes",
                        help="onde gravar/procurar os documentos gerados")
    args = parser.parse_args()

    Manipulador.base_documentos = Path(args.documentos)

    # 127.0.0.1, nunca 0.0.0.0: sem autenticação, escutar na rede exporia o
    # conteúdo interno para qualquer máquina do escritório.
    servidor = ThreadingHTTPServer(("127.0.0.1", args.porta), Manipulador)
    endereco = f"http://127.0.0.1:{args.porta}"
    print(f"API em {endereco}")
    print(f"documentos: {Path(args.documentos).resolve()}")
    print("Ctrl+C para parar")

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nparado")


if __name__ == "__main__":
    main()
