"""Por que este módulo existe.

O fluxo inteiro já funciona por linha de comando, e por linha de comando ele
serve uma pessoa só: quem sabe os comandos. O portão humano — conferir as
pendências antes de publicar — é justamente a parte que precisa ser fácil,
porque é a parte que, sendo chata, deixa de ser feita.

Aqui ele vira tela: o documento de um lado, o que ainda não foi decidido do
outro, o destino num seletor, e o botão de publicar desabilitado enquanto
houver bloqueio.

**Escopo deliberado: local, um usuário, sem autenticação.** Escuta em
127.0.0.1 e só. Um servidor que atende outras pessoas com a credencial de uma
só é compartilhamento de conta, e a resposta para isso é chave de API da
empresa — outro projeto, outra conta de custo. Ver o design em
`docs/superpowers/specs/2026-08-14-camada-editorial-design.md`.

A separação HTTP ↔ pipeline é proposital: este módulo não decide nada. Quem
recusa publicação é o `publicar.py`, porque interface se contorna.
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
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import descobrir
import publicar as pub
import redigir as red

RAIZ = Path(__file__).resolve().parent
# Os assets da interface ficam em `web/`, separados dos módulos Python: o que é
# página não se mistura com o que é processo. A fronteira que importa, porém,
# não é a pasta — é este módulo não decidir nada. Ver a docstring acima.
WEB = RAIZ / "web"
PAGINA = WEB / "console.html"
VENDOR = WEB / "vendor"

# React sem `npm`, pelo mesmo caminho do yt-dlp.exe: arquivo avulso baixado na
# primeira execução, fora do versionamento. São builds UMD, que expõem globais
# e dispensam empacotador.
#
# O `htm` é o que torna isso viável sem Babel: dá sintaxe praticamente igual a
# JSX usando template literal, em 1,4 KB. Com Babel seriam ~2 MB e uma
# transpilação a cada carregamento da página. Trocar `htm` por Babel "para
# poder usar JSX de verdade" é justamente o caminho que este comentário existe
# para evitar.
BIBLIOTECAS = {
    "react.js": "https://unpkg.com/react@18.3.1/umd/react.production.min.js",
    "react-dom.js": "https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js",
    "htm.js": "https://unpkg.com/htm@3.1.1/dist/htm.umd.js",
}

TIPOS = {".html": "text/html", ".js": "application/javascript",
         ".css": "text/css", ".svg": "image/svg+xml"}

# Trabalho em andamento, por id. Uma geração leva minutos: fazê-la dentro do
# handler deixaria o navegador pendurado até o timeout. O trabalho vai para uma
# thread e a página pergunta o estado.
_TRABALHOS: dict[str, dict] = {}
_TRAVA = threading.Lock()


# --------------------------------------------------------------------------
# bibliotecas da interface
# --------------------------------------------------------------------------


def garantir_bibliotecas(silencioso: bool = False) -> None:
    """Baixa React, ReactDOM e htm na primeira execução.

    Usa o PowerShell pelo mesmo motivo de `transcrever.garantir_ytdlp`: o proxy
    corporativo exige autenticação integrada do Windows, que o urllib do Python
    não sabe fazer e o Invoke-WebRequest sabe.
    """
    VENDOR.mkdir(parents=True, exist_ok=True)
    faltando = {n: u for n, u in BIBLIOTECAS.items() if not (VENDOR / n).exists()}
    if not faltando:
        return

    if not silencioso:
        print(f"baixando {len(faltando)} biblioteca(s) da interface...")

    for nome, url in faltando.items():
        alvo = VENDOR / nome
        script = (
            f"$u='{url}'; $o='{alvo}'; "
            "try { Invoke-WebRequest -Uri $u -OutFile $o -UseBasicParsing } "
            "catch { Invoke-WebRequest -Uri $u -OutFile $o -UseBasicParsing "
            "-Proxy ([System.Net.WebRequest]::DefaultWebProxy.GetProxy($u)) "
            "-ProxyUseDefaultCredentials }"
        )
        resultado = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True,
        )
        if resultado.returncode != 0 or not alvo.exists():
            sys.exit(f"falha ao baixar {nome}:\n{resultado.stderr.strip()}")
        if not silencioso:
            print(f"  {nome} ({alvo.stat().st_size // 1024} KB)")


# --------------------------------------------------------------------------
# trabalho em segundo plano
# --------------------------------------------------------------------------


def _anotar(job: str, linha: str) -> None:
    with _TRAVA:
        _TRABALHOS[job]["linhas"].append(linha)


def _gerar(job: str, url: str, com_quadros: bool, intervalo: int,
           base_saida: Path) -> None:
    """Baixa (via `transcrever.py`) e redige. Roda numa thread."""
    try:
        _anotar(job, f"analisando {url}")
        titulo, urls = descobrir.de_outline(url)
        pasta = base_saida / red._seguro(titulo)
        _anotar(job, f'artigo: "{titulo}" — {len(urls)} vídeo(s)')

        comando = [sys.executable, str(RAIZ / "transcrever.py"),
                   "--outline", url, "--saida", str(pasta)]
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
            pasta, titulo=titulo, fonte=url, fonte_tipo="outline",
            interno=True, intervalo_quadros=intervalo,
        )
        artigos = red.redigir(material)

        destino = pasta / "documentacao"
        destino.mkdir(parents=True, exist_ok=True)
        for artigo in artigos:
            arquivo = destino / f"{red._seguro(artigo.titulo)}.md"
            arquivo.write_text(artigo.markdown(), encoding="utf-8")
            marca = "BLOQUEADO" if artigo.bloqueado else f"{len(artigo.pendencias)} pendência(s)"
            _anotar(job, f"{arquivo.name} [{marca}]")

        with _TRAVA:
            _TRABALHOS[job]["estado"] = "pronto"
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

    O arquivo é a verdade: alguém pode ter editado à mão entre gerar e revisar.
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


def _documentos(base: Path) -> list[dict]:
    achados = []
    for arquivo in sorted(base.glob("*/documentacao/*.md")):
        try:
            artigo = pub.ler_documento(arquivo)
        except pub.PublicarErro:
            continue
        pendencias = _pendencias_do_texto(artigo.corpo)
        achados.append({
            "arquivo": str(arquivo.relative_to(base)),
            "titulo": artigo.titulo,
            "artigo_de": arquivo.parent.parent.name,
            "palavras": len(artigo.corpo.split()),
            "pendencias": len(pendencias),
            "bloqueado": any(p["bloqueia"] for p in pendencias),
            "interno": artigo.front_matter.get("interno", True),
        })
    return achados


def _resolver(arquivo: Path, linha_alvo: str) -> int:
    """Tira uma pendência do documento. Devolve quantas sobraram.

    Resolver é decisão humana e fica registrada onde importa: no arquivo. Se a
    lista esvazia, o cabeçalho sai junto — documento sem pendência não deve
    carregar um aviso vazio, que é como aviso vira ruído que ninguém lê.
    """
    texto = arquivo.read_text(encoding="utf-8")
    linhas = texto.splitlines()
    restantes = [l for l in linhas if l.strip() != linha_alvo.strip()]

    corpo = "\n".join(restantes)
    sobraram = _pendencias_do_texto(corpo)
    if not sobraram:
        limpas, dentro = [], False
        for linha in restantes:
            if linha.startswith("## ") and "Conferir antes de usar" in linha:
                dentro = True
                continue
            if dentro and linha.startswith("## "):
                dentro = False
            if not dentro:
                limpas.append(linha)
        corpo = "\n".join(limpas)

    arquivo.write_text(corpo.lstrip("\n").replace("\n\n\n", "\n\n") + "\n",
                       encoding="utf-8")
    return len(sobraram)


# --------------------------------------------------------------------------
# servidor
# --------------------------------------------------------------------------


class Manipulador(BaseHTTPRequestHandler):
    base_documentos = Path("transcricoes")
    base_outline = ""
    pasta_obsidian = ""

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
        # com a página perguntando o estado a cada segundo, isso vira ruído
        pass

    # ---------------- GET ----------------

    def do_GET(self) -> None:  # noqa: N802 — nome exigido pela stdlib
        rota = urllib.parse.urlparse(self.path)
        consulta = urllib.parse.parse_qs(rota.query)

        try:
            if rota.path in ("/", "/index.html"):
                self._estatico("console.html")
                return

            if rota.path == "/api/documentos":
                self._responder(_documentos(self.base_documentos))
                return

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

            if rota.path == "/api/colecoes":
                if not self.base_outline:
                    self._responder([])
                    return
                destino = pub.DestinoOutline(self.base_outline, "")
                self._responder(destino.colecoes())
                return

            if rota.path == "/api/trabalho":
                job = consulta.get("id", [""])[0]
                with _TRAVA:
                    self._responder(_TRABALHOS.get(job) or {"estado": "desconhecido"})
                return

            # o que não é API é arquivo de `web/`: app.js, app.css, vendor/*
            if not rota.path.startswith("/api/"):
                self._estatico(rota.path)
                return

            self._responder({"erro": "rota desconhecida"}, 404)

        except ValueError as erro:
            # pedido malformado (caminho fora da base, JSON torto) não é falha
            # do servidor: a página precisa distinguir "você pediu errado" de
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
                titulo, urls = descobrir.de_outline(corpo["url"])
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

            if rota.path == "/api/resolver":
                arquivo = self._arquivo(corpo["arquivo"])
                sobraram = _resolver(arquivo, corpo["linha"])
                self._responder({"pendencias": sobraram})
                return

            if rota.path == "/api/publicar":
                arquivo = self._arquivo(corpo["arquivo"])
                artigo = pub.ler_documento(arquivo)
                if corpo.get("destino") == "obsidian":
                    if not self.pasta_obsidian:
                        raise pub.PublicarErro(
                            "cofre do Obsidian não configurado: inicie com "
                            "--obsidian <pasta>"
                        )
                    destino = pub.DestinoObsidian(Path(self.pasta_obsidian))
                else:
                    destino = pub.DestinoOutline(self.base_outline,
                                                 corpo.get("colecao", ""))
                onde = pub.publicar(artigo, destino,
                                    rascunho=bool(corpo.get("rascunho", True)))
                self._responder({"onde": onde})
                return

            self._responder({"erro": "rota desconhecida"}, 404)

        except pub.PublicarErro as erro:
            # recusa não é falha do servidor: é a resposta certa, e a página
            # mostra o motivo em vez de um 500 genérico
            self._responder({"erro": str(erro)}, 409)
        except Exception as erro:  # noqa: BLE001
            self._responder({"erro": str(erro)}, 500)

    # ---------------- caminhos ----------------

    def _estatico(self, relativo: str) -> None:
        """Serve um arquivo de `web/`, e nada fora dela.

        Mesma razão de `_arquivo`: sem a checagem, `/../.env` lê o token. Aqui
        a base é outra, então a checagem também precisa ser.
        """
        base = WEB.resolve()
        alvo = (base / relativo.lstrip("/")).resolve()
        if not alvo.is_file() or base not in alvo.parents:
            self._responder({"erro": f"não encontrado: {relativo}"}, 404)
            return

        dados = alvo.read_bytes()
        tipo = TIPOS.get(alvo.suffix, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", f"{tipo}; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

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


def main() -> None:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Console local de revisão e publicação."
    )
    parser.add_argument("--porta", type=int, default=8765)
    parser.add_argument("--documentos", default="transcricoes",
                        help="onde procurar os documentos gerados")
    parser.add_argument("--outline", default=descobrir.ler_env("OUTLINE_URL") or "",
                        help="https://outline.suaempresa.com")
    parser.add_argument("--obsidian", default=descobrir.ler_env("OBSIDIAN_VAULT") or "",
                        help="pasta do cofre do Obsidian")
    parser.add_argument("--sem-navegador", action="store_true")
    args = parser.parse_args()

    Manipulador.base_documentos = Path(args.documentos)
    Manipulador.base_outline = args.outline.rstrip("/")
    Manipulador.pasta_obsidian = args.obsidian

    if not PAGINA.is_file():
        sys.exit(f"página não encontrada: {PAGINA}")

    garantir_bibliotecas()

    # 127.0.0.1, nunca 0.0.0.0: sem autenticação, escutar na rede exporia o
    # conteúdo interno para qualquer máquina do escritório.
    servidor = ThreadingHTTPServer(("127.0.0.1", args.porta), Manipulador)
    endereco = f"http://127.0.0.1:{args.porta}"
    print(f"console em {endereco}")
    print(f"documentos: {Path(args.documentos).resolve()}")
    print("Ctrl+C para parar")

    if not args.sem_navegador:
        webbrowser.open(endereco)

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nparado")


if __name__ == "__main__":
    main()
