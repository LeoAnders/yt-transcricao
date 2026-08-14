"""Transcreve vídeos do YouTube a partir da legenda automática.

Uso:
    python transcrever.py https://youtu.be/xxxx https://youtu.be/yyyy
    python transcrever.py --lista links.txt
    python transcrever.py --texto pagina-copiada.txt
    python transcrever.py --pagina https://exemplo.com/documentacao
    python transcrever.py --outline https://outline.suaempresa.com/doc/artigo-XXXX
    python transcrever.py --outline <url> --quadros   # + quadros dos sem legenda

Grava um .md por vídeo em `transcricoes/`, com título, link e marcação de
tempo. Com `--quadros`, os vídeos que não têm legenda (tipicamente os sem
fala) viram imagens em `transcricoes/<artigo>/quadros/<id>/` para a IA ler.

Por que yt-dlp e não um `fetch` direto na URL da legenda: o YouTube passou a
exigir um token de origem de navegador real no endpoint `/api/timedtext` —
uma requisição comum recebe `200` com corpo vazio. O yt-dlp contorna isso
pedindo os dados ao player "android vr", que não é submetido a essa
checagem.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import winreg
from pathlib import Path

import descobrir
import limpar
import quadros

RAIZ = Path(__file__).parent
YTDLP = RAIZ / "yt-dlp.exe"
URL_YTDLP = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"

# Fatia do download de vídeo. O googlevideo estrangula requisição única e
# grande, e o proxy corporativo derruba conexão longa; o próprio yt-dlp fatia
# por esse motivo. Aumentar isso reintroduz timeout em vídeo de dezenas de MB.
PEDACO_BYTES = 8 * 1024 * 1024

# Resolução é o fator limitante para ler texto de terminal no quadro, então
# pede-se o maior formato até 1080p. `avc1` primeiro porque é o codec que
# qualquer build de ffmpeg decodifica; os fallbacks cobrem vídeo que só tem
# vp9/av1 ou que é menor que o teto.
FORMATO_VIDEO = "bv*[vcodec^=avc1][height<=1080]/bv*[height<=1080]/bv*/b"


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
# download do vídeo (para os que não têm legenda)
# --------------------------------------------------------------------------

# Baixa em pedaços via Invoke-WebRequest. É o único cliente na máquina que faz
# autenticação integrada do Windows no proxy: o `yt-dlp -f <video>` e o urllib
# recebem "407 Proxy Authentication Required" nos bytes do googlevideo, mesmo
# com --proxy. Os *metadados* passam sem credencial, por isso a URL vem do
# yt-dlp e só a transferência vem para cá.
#
# A URL e o destino chegam por variável de ambiente de propósito: URL de
# googlevideo tem `&`, `;` e `=` que o `powershell -Command` interpretaria.
_SCRIPT_DOWNLOAD = r"""
$ErrorActionPreference = 'Stop'
$u = $env:YTV_URL
$pedaco = [int]$env:YTV_PEDACO

# GetProxy devolve a própria URL quando não há proxy configurado; nesse caso
# passar -Proxy apontaria o download para si mesmo.
$px = [System.Net.WebRequest]::DefaultWebProxy.GetProxy($u)
$parametros = @{ UseBasicParsing = $true; TimeoutSec = 120 }
if ($px.Host -ne ([Uri]$u).Host) {
    $parametros.Proxy = $px
    $parametros.ProxyUseDefaultCredentials = $true
}

$arquivo = [System.IO.File]::Create($env:YTV_SAIDA)
try {
    $inicio = 0
    while ($true) {
        $fim = $inicio + $pedaco - 1
        # `&range=` como PARÂMETRO DE URL. O header Range funciona em alguns
        # formatos, mas o parâmetro é o que o yt-dlp usa e vale para todos.
        $r = Invoke-WebRequest -Uri "$u&range=$inicio-$fim" @parametros
        $bytes = $r.Content
        if ($bytes.Length -eq 0) { break }
        $arquivo.Write($bytes, 0, $bytes.Length)
        $inicio += $bytes.Length
        if ($bytes.Length -lt $pedaco) { break }   # último pedaço
    }
} finally {
    $arquivo.Close()
}
Write-Output $inicio
"""


def dados_do_video(url: str, proxy: str | None) -> dict:
    """Resolve a URL direta do googlevideo, o tamanho e se a origem tem áudio.

    Devolve `{"url": "", ...}` quando não há formato utilizável — quem chama
    trata como "sem quadros" em vez de abortar o lote inteiro.

    O `tem_audio` vem da lista de formatos da ORIGEM, não do arquivo baixado:
    baixa-se video-only de propósito (áudio é peso inútil para virar imagem),
    então o .mp4 local nunca tem faixa de áudio e olhar para ele responderia
    sempre "mudo".
    """
    comando = [
        str(garantir_ytdlp(silencioso=True)),
        "--no-warnings", "--quiet",
        "-f", FORMATO_VIDEO,
        "--print", "%(filesize,filesize_approx)s|%(formats.:.acodec)s|%(url)s",
        url,
    ]
    if proxy:
        comando[1:1] = ["--proxy", proxy]

    resultado = subprocess.run(comando, capture_output=True, text=True)
    linha = resultado.stdout.strip().splitlines()
    if not linha or linha[0].count("|") < 2:
        return {"url": "", "tamanho": 0, "tem_audio": False}

    tamanho, codecs, direta = linha[0].split("|", 2)
    try:
        esperado = int(tamanho)
    except ValueError:
        esperado = 0              # filesize desconhecido não impede baixar

    # a lista vem como repr de Python: ['none', 'mp4a.40.2', ...]
    tem_audio = any(c not in ("none", "None", "")
                    for c in re.findall(r"'([^']*)'", codecs))
    return {"url": direta, "tamanho": esperado, "tem_audio": tem_audio}


def baixar_video(url: str, destino: Path, proxy: str | None) -> dict | None:
    """Baixa o vídeo para `destino`. None se não houver formato disponível.

    Devolve os dados de origem (`arquivo`, `tem_audio`) porque quem chama
    precisa do `tem_audio` da origem, que o arquivo baixado não revela.
    """
    dados = dados_do_video(url, proxy)
    if not dados["url"]:
        return None

    esperado = dados["tamanho"]
    ambiente = {
        **os.environ,
        "YTV_URL": dados["url"],
        "YTV_SAIDA": str(destino),
        "YTV_PEDACO": str(PEDACO_BYTES),
    }
    resultado = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _SCRIPT_DOWNLOAD],
        capture_output=True, text=True, env=ambiente,
    )
    if resultado.returncode != 0 or not destino.exists():
        print(f"  falha ao baixar o vídeo: {resultado.stderr.strip().splitlines()[-1:]}")
        return None

    baixado = destino.stat().st_size
    # Download truncado gera quadros só do começo do vídeo, e isso passaria
    # despercebido: o ffmpeg extrai o que conseguiu ler sem reclamar.
    if esperado and baixado < esperado:
        print(f"  aviso: baixou {baixado} de {esperado} bytes (vídeo incompleto)")
    return {"arquivo": destino, "tem_audio": dados["tem_audio"]}


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
# quadros dos vídeos sem legenda
# --------------------------------------------------------------------------

def quadros_dos_sem_legenda(urls: list[str], destino: Path, proxy: str | None,
                            temporaria: Path, intervalo: int = 4) -> int:
    """Baixa cada vídeo sem legenda e extrai os quadros em `destino/quadros/`.

    Devolve quantos vídeos renderam quadros. O .mp4 fica na pasta temporária e
    morre com ela: o entregável é a imagem, e vídeo interno guardado a mais é
    superfície de vazamento (ver .claude/rules/seguranca.md).
    """
    if not quadros.ffmpeg_disponivel():
        print("\n  ffmpeg não encontrado no PATH; sem quadros.")
        print("  instale com: winget install Gyan.FFmpeg")
        return 0

    print(f"\nextraindo quadros de {len(urls)} vídeo(s) sem legenda:\n")
    prontos = 0
    for url in urls:
        video_id = url.split("v=")[-1]
        origem = baixar_video(url, temporaria / f"{video_id}.mp4", proxy)
        if origem is None:
            print(f"  {video_id}: sem formato de vídeo disponível")
            continue

        relatorio = quadros.extrair_com_relatorio(
            origem["arquivo"], destino / "quadros" / video_id, intervalo
        )
        # Vídeo COM áudio e sem legenda é outro problema (o YouTube não gerou a
        # legenda ainda, ou o idioma não é o pedido) — avisa para não passar por
        # "vídeo mudo", que é o caso que os quadros resolvem.
        aviso = "  [tem áudio: talvez a legenda só não exista ainda]" if origem["tem_audio"] else ""
        print(f"  {video_id}: {len(relatorio['quadros'])} quadro(s){aviso}")
        prontos += 1

    return prontos


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
    ap.add_argument("--quadros", action="store_true",
                    help="para os vídeos sem legenda, baixa e extrai quadros para leitura por IA")
    ap.add_argument("--intervalo-quadros", type=int, default=4,
                    help="segundos entre quadros (padrão: 4)")
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

        com_quadros = 0
        if pendentes:
            print(f"\nsem legenda automática ({len(pendentes)}):")
            for url in pendentes:
                print(f"  {url}")
            if args.quadros:
                com_quadros = quadros_dos_sem_legenda(
                    pendentes, destino, proxy, pasta_vtt, args.intervalo_quadros
                )
            else:
                print("  vídeo sem fala não gera legenda — use --quadros para lê-los")

        arquivos = sorted(pasta_vtt.glob("*.vtt"))
        if not arquivos and not com_quadros:
            sys.exit("\nnenhuma legenda baixada.")

        total = 0
        vistos: set[str] = set()
        if arquivos:
            print(f"\nconvertendo {len(arquivos)} legenda(s):\n")
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
    if com_quadros:
        print(f"{com_quadros} vídeo(s) em quadros | {destino / 'quadros'}")
    print(f"saída: {destino}")


def _seguro(nome: str) -> str:
    """Nome de pasta válido no Windows."""
    for proibido in '<>:"/\\|?*':
        nome = nome.replace(proibido, "-")
    return nome.strip(" .") or "sem-titulo"


if __name__ == "__main__":
    main()
