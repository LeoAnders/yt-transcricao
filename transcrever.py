"""Transcreve vídeos do YouTube a partir da legenda automática.

Uso:
    python transcrever.py https://youtu.be/xxxx https://youtu.be/yyyy
    python transcrever.py --lista links.txt
    python transcrever.py --texto pagina-copiada.txt
    python transcrever.py --pagina https://exemplo.com/documentacao
    python transcrever.py --outline https://outline.suaempresa.com/doc/artigo-XXXX

Grava um .md por vídeo em `transcricoes/`, com título, link e marcação de
tempo.

Por que yt-dlp e não um `fetch` direto na URL da legenda: o YouTube passou a
exigir um token de origem de navegador real no endpoint `/api/timedtext` —
uma requisição comum recebe `200` com corpo vazio. O yt-dlp contorna isso
pedindo os dados ao player "android vr", que não é submetido a essa
checagem.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import winreg
from pathlib import Path

import descobrir
import limpar

RAIZ = Path(__file__).parent
YTDLP = RAIZ / "yt-dlp.exe"
URL_YTDLP = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"


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


def garantir_ytdlp(silencioso: bool = False) -> Path:
    """Baixa o yt-dlp.exe na primeira execução. Usa o PowerShell porque o
    proxy corporativo pode exigir autenticação integrada do Windows, que o
    urllib do Python não sabe fazer — o Invoke-WebRequest sabe."""
    if YTDLP.exists():
        return YTDLP

    if not silencioso:
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
        capture_output=True, text=True,
    )
    if resultado.returncode != 0 or not YTDLP.exists():
        sys.exit(f"falha ao baixar o yt-dlp:\n{resultado.stderr.strip()}")

    if not silencioso:
        print(f"  ok ({YTDLP.stat().st_size / 1_048_576:.1f} MB)")
    return YTDLP


# --------------------------------------------------------------------------
# download das legendas
# --------------------------------------------------------------------------

def idiomas_disponiveis(url: str, proxy: str | None) -> list[str]:
    """Lista os códigos de legenda automática que o vídeo tem, para o fallback
    saber o que pedir em vez de chutar."""
    comando = [
        str(garantir_ytdlp(silencioso=True)),
        "--skip-download", "--no-warnings",
        "--print-json", "--quiet", url,
    ]
    if proxy:
        comando[1:1] = ["--proxy", proxy]

    resultado = subprocess.run(comando, capture_output=True, text=True)
    try:
        dados = json.loads(resultado.stdout.strip().splitlines()[0])
    except (json.JSONDecodeError, IndexError):
        return []
    return list(dados.get("automatic_captions", {}).keys())


def baixar_legendas(urls: list[str], pasta: Path, proxy: str | None,
                    idioma: str, com_fallback: bool = True) -> list[str]:
    """Baixa as legendas automáticas. Devolve as URLs que ficaram sem legenda.

    A ordem é do mais específico ao mais genérico, e cada tentativa só busca
    os vídeos que ainda não têm arquivo — pedir vários idiomas de uma vez faz
    o YouTube responder 429.
    """
    ytdlp = garantir_ytdlp()
    pendentes = list(urls)
    tentativas = [f"{idioma}-orig", idioma, f"{idioma}.*"]

    def executar(codigo: str, alvos: list[str]) -> None:
        comando = [
            str(ytdlp),
            "--skip-download", "--write-auto-subs",
            "--sub-langs", codigo,
            "--sub-format", "vtt",
            "--sleep-requests", "1",
            "--ignore-errors", "--no-warnings", "--quiet",
            "-o", str(pasta / "%(id)s - %(title)s.%(ext)s"),
            *alvos,
        ]
        if proxy:
            comando[1:1] = ["--proxy", proxy]
        print(f"buscando legenda '{codigo}' de {len(alvos)} vídeo(s)...")
        # a saída do yt-dlp é capturada: quando este módulo roda sob o
        # servidor MCP, o stdout carrega JSON-RPC e qualquer texto solto
        # quebra o protocolo
        subprocess.run(comando, check=False, capture_output=True, text=True)

    def ainda_faltam(alvos: list[str]) -> list[str]:
        prontos = {v.name.split(" - ")[0] for v in pasta.glob("*.vtt")}
        return [u for u in alvos if u.split("v=")[-1] not in prontos]

    for codigo in tentativas:
        if not pendentes:
            return []
        executar(codigo, pendentes)
        pendentes = ainda_faltam(pendentes)

    # fallback de idioma: o vídeo pode simplesmente não ser no idioma pedido.
    # Em vez de devolver vazio sem explicação, usa o que existir e avisa.
    if com_fallback and pendentes:
        for url in list(pendentes):
            outros = [c for c in idiomas_disponiveis(url, proxy)
                      if not c.startswith(idioma)]
            if not outros:
                continue
            escolhido = outros[0]
            print(f"  '{idioma}' indisponível em {url.split('v=')[-1]}; "
                  f"usando '{escolhido}'")
            executar(escolhido, [url])
        pendentes = ainda_faltam(pendentes)

    return pendentes


# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Transcreve vídeos do YouTube pela legenda automática.",
    )
    ap.add_argument("urls", nargs="*", help="URLs ou IDs de vídeos do YouTube")
    ap.add_argument("--lista", help="arquivo com uma URL por linha")
    ap.add_argument("--texto", help="arquivo qualquer (HTML salvo, Markdown, texto colado)")
    ap.add_argument("--pagina", help="URL de uma página HTML; extrai os links de YouTube dela")
    ap.add_argument("--outline", help="URL de um artigo do Outline")
    ap.add_argument("--saida", default="transcricoes", help="pasta de saída")
    ap.add_argument("--idioma", default="pt", help="idioma da legenda (padrão: pt)")
    ap.add_argument("--sem-timestamps", action="store_true",
                    help="texto corrido, sem marcação de tempo")
    ap.add_argument("--sem-fallback", action="store_true",
                    help="não tenta outro idioma quando o pedido não existe")
    ap.add_argument("--sem-proxy", action="store_true", help="ignora o proxy do Windows")
    args = ap.parse_args()

    entradas = list(args.urls)
    destino_padrao = args.saida

    if args.lista:
        entradas += Path(args.lista).read_text(encoding="utf-8").splitlines()
    if args.texto:
        entradas += descobrir.de_arquivo(args.texto)
    if args.pagina:
        entradas += descobrir.de_pagina(args.pagina)
    if args.outline:
        titulo, achados = descobrir.de_outline(args.outline)
        print(f'artigo: "{titulo}"')
        entradas += achados
        # sem --saida explícito, separa por artigo: é o que evita o inchaço
        # de jogar dezenas de assuntos numa pasta só
        if args.saida == "transcricoes":
            destino_padrao = str(Path("transcricoes") / _seguro(titulo))

    urls = descobrir.normalizar(entradas)
    if not urls:
        ap.error("nenhum vídeo encontrado (use URLs, --lista, --texto, --pagina ou --outline)")

    proxy = None if args.sem_proxy else detectar_proxy()
    print(f"{len(urls)} vídeo(s) | proxy: {proxy or 'direto'}\n")

    destino = Path(destino_padrao)
    if not destino.is_absolute():
        destino = RAIZ / destino

    with tempfile.TemporaryDirectory() as tmp:
        pasta_vtt = Path(tmp)
        pendentes = baixar_legendas(
            urls, pasta_vtt, proxy, args.idioma,
            com_fallback=not args.sem_fallback,
        )

        if pendentes:
            print(f"\nsem legenda automática ({len(pendentes)}):")
            for url in pendentes:
                print(f"  {url}")
            print("  vídeo sem fala não gera legenda — para esses, use quadros.py")

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

            arquivo, palavras = limpar.converter(
                vtt, destino, com_timestamps=not args.sem_timestamps
            )
            total += palavras
            print(f"  {palavras:>6} palavras  {arquivo.name}")

    print(f"\n{len(vistos)} arquivo(s) | {total} palavras")
    print(f"saída: {destino}")


def _seguro(nome: str) -> str:
    """Nome de pasta válido no Windows."""
    for proibido in '<>:"/\\|?*':
        nome = nome.replace(proibido, "-")
    return nome.strip(" .") or "sem-titulo"


if __name__ == "__main__":
    main()
