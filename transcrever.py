"""Transcreve vídeos do YouTube a partir da legenda automática.

Uso:
    python transcrever.py https://youtu.be/xxxx https://youtu.be/yyyy
    python transcrever.py --lista links.txt
    python transcrever.py --outline https://cuka.consistem.com.br/doc/artigo-XXXX

Baixa a legenda automática de cada vídeo com o yt-dlp e grava um .md por
vídeo em `transcricoes/`, com título, link e marcação de tempo.

Por que yt-dlp e não um `fetch` direto na URL da legenda: o YouTube passou a
exigir um token de origem de navegador real no endpoint `/api/timedtext` —
uma requisição comum recebe `200` com corpo vazio. O yt-dlp contorna isso
pedindo os dados ao player "android vr", que não é submetido a essa
checagem.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import winreg
from pathlib import Path

import limpar

RAIZ = Path(__file__).parent
YTDLP = RAIZ / "yt-dlp.exe"
URL_YTDLP = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"

# aceita youtu.be/ID e youtube.com/watch?v=ID
RE_YOUTUBE = re.compile(
    r"(?:youtu\.be/|youtube\.com/watch\?v=)([A-Za-z0-9_-]{11})"
)


# --------------------------------------------------------------------------
# ambiente: proxy e yt-dlp
# --------------------------------------------------------------------------

def detectar_proxy() -> str | None:
    """Descobre o proxy pelas variáveis de ambiente ou pelas configurações do
    Windows. Evita chumbar o IP, que muda de rede para rede."""
    for var in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
        if os.environ.get(var):
            return os.environ[var]

    try:
        chave = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        )
        ativo, _ = winreg.QueryValueEx(chave, "ProxyEnable")
        if not ativo:
            return None
        servidor, _ = winreg.QueryValueEx(chave, "ProxyServer")
    except OSError:
        return None

    if not servidor:
        return None
    # o registro pode trazer "http=host:porta;https=host:porta"
    if "=" in servidor:
        for parte in servidor.split(";"):
            if parte.startswith(("https=", "http=")):
                servidor = parte.split("=", 1)[1]
                break
    return servidor if servidor.startswith("http") else f"http://{servidor}"


def garantir_ytdlp() -> Path:
    """Baixa o yt-dlp.exe na primeira execução. Usa o PowerShell porque o
    proxy corporativo exige autenticação integrada do Windows, que o urllib
    do Python não sabe fazer — o Invoke-WebRequest sabe."""
    if YTDLP.exists():
        return YTDLP

    print("yt-dlp.exe não encontrado, baixando do GitHub...")
    script = (
        f"$u='{URL_YTDLP}'; $o='{YTDLP}'; "
        "try { Invoke-WebRequest -Uri $u -OutFile $o -UseBasicParsing } "
        "catch { Invoke-WebRequest -Uri $u -OutFile $o -UseBasicParsing "
        "-Proxy ([System.Net.WebRequest]::DefaultWebProxy.GetProxy($u)) "
        "-ProxyUseDefaultCredentials }"
    )
    resultado = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0 or not YTDLP.exists():
        sys.exit(f"falha ao baixar o yt-dlp:\n{resultado.stderr.strip()}")

    print(f"  ok ({YTDLP.stat().st_size / 1_048_576:.1f} MB)")
    return YTDLP


# --------------------------------------------------------------------------
# origens dos links
# --------------------------------------------------------------------------

def ler_env(chave: str) -> str | None:
    """Lê uma chave do ambiente ou do .env ao lado do script (sem depender de
    biblioteca externa — instalar pacote depende do proxy, que nem sempre
    responde)."""
    if os.environ.get(chave):
        return os.environ[chave]

    env = RAIZ / ".env"
    if not env.exists():
        return None
    for linha in env.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        nome, _, valor = linha.partition("=")
        if nome.strip() == chave:
            return valor.strip().strip('"').strip("'")
    return None


def links_do_outline(url_doc: str) -> list[str]:
    """Lê um artigo do Outline pela API e extrai os links de YouTube na ordem
    em que aparecem no texto."""
    token = ler_env("OUTLINE_API_TOKEN")
    if not token:
        sys.exit(
            "defina OUTLINE_API_TOKEN no .env para usar --outline\n"
            "(o token sai em Outline > Settings > API Tokens)"
        )

    base = "/".join(url_doc.split("/")[:3])          # https://host
    doc_id = url_doc.rstrip("/").split("/")[-1]      # slug-XXXXXXXX

    requisicao = urllib.request.Request(
        f"{base}/api/documents.info",
        data=f'{{"id":"{doc_id}"}}'.encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    # o Outline é interno: vai direto, sem passar pelo proxy
    abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with abridor.open(requisicao, timeout=30) as resposta:
        import json

        dados = json.loads(resposta.read().decode("utf-8"))

    documento = dados.get("data", {})
    texto = documento.get("text", "")
    print(f'artigo: "{documento.get("title", doc_id)}"')

    ids: list[str] = []
    for video_id in RE_YOUTUBE.findall(texto):
        if video_id not in ids:
            ids.append(video_id)
    return [f"https://www.youtube.com/watch?v={i}" for i in ids]


def normalizar(entradas: list[str]) -> list[str]:
    """Aceita URL completa ou só o ID de 11 caracteres."""
    urls: list[str] = []
    for entrada in entradas:
        entrada = entrada.strip()
        if not entrada or entrada.startswith("#"):
            continue
        achado = RE_YOUTUBE.search(entrada)
        video_id = achado.group(1) if achado else entrada
        url = f"https://www.youtube.com/watch?v={video_id}"
        if url not in urls:
            urls.append(url)
    return urls


# --------------------------------------------------------------------------
# download
# --------------------------------------------------------------------------

def baixar_legendas(urls: list[str], pasta: Path, proxy: str | None,
                    idiomas: list[str]) -> None:
    """Baixa as legendas automáticas no diretório indicado.

    Tenta os idiomas em ordem e só busca o seguinte para os vídeos que ainda
    não têm arquivo — pedir vários de uma vez faz o YouTube responder 429.
    """
    ytdlp = garantir_ytdlp()
    pendentes = list(urls)

    for idioma in idiomas:
        if not pendentes:
            break

        comando = [
            str(ytdlp),
            "--skip-download",
            "--write-auto-subs",
            "--sub-langs", idioma,
            "--sub-format", "vtt",
            "--sleep-requests", "1",
            "--ignore-errors",
            "--no-warnings",
            "--quiet",
            "--progress",
            "-o", str(pasta / "%(id)s - %(title)s.%(ext)s"),
            *pendentes,
        ]
        if proxy:
            comando[1:1] = ["--proxy", proxy]

        print(f"buscando legenda '{idioma}' de {len(pendentes)} vídeo(s)...")
        subprocess.run(comando, check=False)

        baixados = {v.name.split(" - ")[0] for v in pasta.glob("*.vtt")}
        pendentes = [u for u in pendentes if u.split("v=")[-1] not in baixados]

    if pendentes:
        print(f"\nsem legenda automática disponível ({len(pendentes)}):")
        for url in pendentes:
            print(f"  {url}")


# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Transcreve vídeos do YouTube pela legenda automática.",
    )
    ap.add_argument("urls", nargs="*", help="URLs ou IDs de vídeos do YouTube")
    ap.add_argument("--lista", help="arquivo texto com uma URL por linha")
    ap.add_argument("--outline", help="URL de um artigo do Outline; varre os links de YouTube dele")
    ap.add_argument("--saida", default="transcricoes", help="pasta de saída (padrão: transcricoes)")
    ap.add_argument("--idioma", default="pt", help="idioma da legenda (padrão: pt)")
    ap.add_argument("--sem-proxy", action="store_true", help="ignora o proxy do Windows")
    args = ap.parse_args()

    entradas = list(args.urls)
    if args.lista:
        entradas += Path(args.lista).read_text(encoding="utf-8").splitlines()
    if args.outline:
        entradas += links_do_outline(args.outline)

    urls = normalizar(entradas)
    if not urls:
        ap.error("nenhum vídeo informado (use URLs, --lista ou --outline)")

    proxy = None if args.sem_proxy else detectar_proxy()
    print(f"{len(urls)} vídeo(s) | proxy: {proxy or 'direto'}\n")

    # "pt-orig" é a faixa original gerada pelo ASR; "pt" costuma ser a mesma
    # coisa, mas alguns vídeos só expõem uma das duas
    idiomas = [f"{args.idioma}-orig", args.idioma, f"{args.idioma}.*"]

    destino = Path(args.saida)
    if not destino.is_absolute():
        destino = RAIZ / destino

    with tempfile.TemporaryDirectory() as tmp:
        pasta_vtt = Path(tmp)
        baixar_legendas(urls, pasta_vtt, proxy, idiomas)

        arquivos = sorted(pasta_vtt.glob("*.vtt"))
        if not arquivos:
            sys.exit("\nnenhuma legenda baixada.")

        print(f"\nconvertendo {len(arquivos)} legenda(s):\n")
        total = 0
        vistos: set[str] = set()
        for vtt in arquivos:
            video_id, _ = limpar.nome_do_arquivo(vtt)
            if video_id in vistos:      # mesma faixa em dois idiomas
                continue
            vistos.add(video_id)

            arquivo, palavras = limpar.converter(vtt, destino)
            total += palavras
            print(f"  {palavras:>6} palavras  {arquivo.name}")

    print(f"\n{len(vistos)} arquivo(s) | {total} palavras")
    print(f"saída: {destino}")


if __name__ == "__main__":
    main()
