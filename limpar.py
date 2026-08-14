"""Converte legendas .vtt do YouTube em Markdown legível.

A legenda automática do YouTube vem em modo "rolante": cada bloco repete a
linha anterior e traz uma tag `<c>` por palavra, com timestamp próprio. Lido
cru, o texto sai com cerca de três vezes o tamanho real e é ilegível. Este
módulo desfaz as duas coisas e reagrupa a fala em parágrafos ancorados no
tempo.

É puro: não conhece rede, proxy nem yt-dlp — recebe arquivos, devolve texto.
"""

import re
from pathlib import Path

# tags inline da legenda: <00:00:01.439> e <c>/</c>
RE_TAG = re.compile(r"<[^>]*>")
RE_TEMPO = re.compile(r"^(\d\d):(\d\d):(\d\d)\.\d+\s+-->")

# a cada quantos segundos abrir um novo parágrafo com marcação de tempo
JANELA_SEGUNDOS = 30


def _segundos(h: str, m: str, s: str) -> int:
    return int(h) * 3600 + int(m) * 60 + int(s)


def extrair_falas(texto_vtt: str) -> list[tuple[int, str]]:
    """Devolve [(segundo_de_inicio, linha_de_fala)] já sem tags e sem repetição."""
    falas: list[tuple[int, str]] = []
    inicio = 0

    for linha in texto_vtt.splitlines():
        marcador = RE_TEMPO.match(linha)
        if marcador:
            inicio = _segundos(*marcador.groups())
            continue

        if not linha.strip() or linha.startswith(("WEBVTT", "Kind:", "Language:")):
            continue

        fala = RE_TAG.sub("", linha).strip()
        if not fala:
            continue

        # o modo rolante reimprime a linha anterior no bloco seguinte
        if falas and falas[-1][1] == fala:
            continue

        falas.append((inicio, fala))

    return falas


def agrupar(falas: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Junta as falas em parágrafos de ~JANELA_SEGUNDOS, para dar âncora de
    tempo sem encher o texto de timestamp a cada linha."""
    if not falas:
        return []

    paragrafos: list[tuple[int, str]] = []
    buffer: list[str] = []
    marco = falas[0][0]

    for segundo, fala in falas:
        if segundo - marco >= JANELA_SEGUNDOS and buffer:
            paragrafos.append((marco, " ".join(buffer)))
            buffer = []
            marco = segundo
        buffer.append(fala)

    if buffer:
        paragrafos.append((marco, " ".join(buffer)))

    return paragrafos


def nome_do_arquivo(vtt: Path) -> tuple[str, str]:
    """Separa "<id> - <título>.<lang>.vtt" em (id, título)."""
    nome = vtt.name
    for sufixo in (".vtt",):
        if nome.endswith(sufixo):
            nome = nome[: -len(sufixo)]
    # remove o código de idioma que o yt-dlp acrescenta (.pt-orig, .pt, ...)
    nome = re.sub(r"\.[a-zA-Z-]+$", "", nome)
    video_id, _, titulo = nome.partition(" - ")
    return video_id.strip(), (titulo.strip() or video_id.strip())


def converter(vtt: Path, destino: Path) -> tuple[Path, int]:
    """Converte um .vtt em .md no destino. Devolve (arquivo, nº de palavras)."""
    video_id, titulo = nome_do_arquivo(vtt)
    paragrafos = agrupar(extrair_falas(vtt.read_text(encoding="utf-8")))

    corpo = "\n\n".join(
        f"({s // 60:02d}:{s % 60:02d}) {t}" for s, t in paragrafos
    )

    conteudo = (
        f"# {titulo}\n\n"
        f"- Vídeo: https://youtu.be/{video_id}\n"
        f"- Origem: legenda automática do YouTube, não revisada\n\n"
        f"---\n\n{corpo}\n"
    )

    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / f"{titulo}.md"
    arquivo.write_text(conteudo, encoding="utf-8")
    return arquivo, len(corpo.split())
