"""Descoberta de vídeos do YouTube em qualquer fonte de texto.

Separado do resto de propósito: extrair IDs de um texto é uma função pura e
testável sem rede. As fontes (arquivo, página HTML) são só maneiras diferentes
de conseguir esse texto — ler artigo de documentação (Outline, Notion, etc.)
não é responsabilidade deste projeto: quem tiver o texto em mãos (por MCP, por
exemplo) chama `urls_em_texto` nele.
"""

import os
import re
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).parent

# Todas as formas em que um vídeo do YouTube aparece em documentação. Faltar
# uma delas significa ignorar vídeo em silêncio — página de documentação
# costuma *embutir* o player (/embed/) em vez de linkar.
RE_YOUTUBE = re.compile(
    r"""(?:
          youtu\.be/                        # link curto
        | youtube\.com/watch\?(?:[^"'\s]*&)?v=   # link normal
        | youtube\.com/embed/               # player embutido
        | youtube\.com/shorts/              # shorts
        | youtube\.com/live/                # transmissão
        | youtube\.com/v/                   # formato antigo
        | youtube-nocookie\.com/embed/      # embutido sem cookie
    )([A-Za-z0-9_-]{11})""",
    re.VERBOSE,
)

CABECALHO_NAVEGADOR = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


def ids_em_texto(texto: str) -> list[str]:
    """Extrai IDs de vídeo de qualquer texto, na ordem de aparição e sem
    repetir. Funciona igual em HTML, Markdown, JSON ou lista solta."""
    vistos: list[str] = []
    for video_id in RE_YOUTUBE.findall(texto):
        if video_id not in vistos:
            vistos.append(video_id)
    return vistos


def urls_em_texto(texto: str) -> list[str]:
    return [f"https://www.youtube.com/watch?v={i}" for i in ids_em_texto(texto)]


# rótulo de link Markdown: [Introdução à API](https://youtu.be/xxxx)
RE_ROTULO = re.compile(r"\[([^\]]+)\]\(\s*(?:<)?([^)>\s]+)")


def videos_com_rotulo(texto: str) -> list[dict]:
    """Extrai os vídeos com o rótulo que a documentação usa para cada link.

    Serve para listar o conteúdo de um artigo sem baixar nada. Vale lembrar
    que esse rótulo costuma **divergir** do título real no YouTube — a
    documentação renomeia. O link é a única chave confiável.
    """
    rotulos: dict[str, str] = {}
    for rotulo, alvo in RE_ROTULO.findall(texto):
        achado = RE_YOUTUBE.search(alvo)
        if achado:
            rotulos.setdefault(achado.group(1), rotulo.strip())

    return [
        {
            "id": video_id,
            "url": f"https://youtu.be/{video_id}",
            "rotulo_na_documentacao": rotulos.get(video_id),
        }
        for video_id in ids_em_texto(texto)
    ]


def normalizar(entradas: list[str]) -> list[str]:
    """Aceita URL completa (qualquer formato) ou o ID de 11 caracteres cru."""
    urls: list[str] = []
    for entrada in entradas:
        entrada = entrada.strip()
        if not entrada or entrada.startswith("#"):
            continue

        achado = RE_YOUTUBE.search(entrada)
        if achado:
            video_id = achado.group(1)
        elif re.fullmatch(r"[A-Za-z0-9_-]{11}", entrada):
            video_id = entrada
        else:
            print(f"  ignorado (não parece vídeo do YouTube): {entrada}")
            continue

        url = f"https://www.youtube.com/watch?v={video_id}"
        if url not in urls:
            urls.append(url)
    return urls


# --------------------------------------------------------------------------
# fontes
# --------------------------------------------------------------------------

def de_arquivo(caminho: str) -> list[str]:
    """Extrai links de um arquivo qualquer: lista de URLs, Markdown, HTML
    salvo, ou o Ctrl+C de uma página colado num .txt.

    É o modo coringa: documentação atrás de login (SharePoint, Confluence
    privado, Notion, Google Drive restrito) nunca abre por URL sem integração
    dedicada, mas sempre dá para selecionar a página e colar num arquivo.
    """
    texto = Path(caminho).read_text(encoding="utf-8", errors="replace")
    return urls_em_texto(texto)


def de_pagina(url: str) -> list[str]:
    """Busca uma página HTML e extrai os links de YouTube dela.

    Serve para documentação pública ou de intranet sem login. Páginas que
    exigem autenticação devolvem a tela de login — use `de_arquivo` nesses
    casos.
    """
    requisicao = urllib.request.Request(url, headers=CABECALHO_NAVEGADOR)
    with urllib.request.urlopen(requisicao, timeout=30) as resposta:
        bruto = resposta.read()

    # o charset declarado costuma ser confiável; se não, cai em utf-8 tolerante
    codificacao = resposta.headers.get_content_charset() or "utf-8"
    try:
        texto = bruto.decode(codificacao, errors="replace")
    except LookupError:
        texto = bruto.decode("utf-8", errors="replace")

    achados = urls_em_texto(texto)
    if not achados:
        print(
            "  nenhum vídeo encontrado na página.\n"
            "  se ela exige login, salve o conteúdo num arquivo e use --texto"
        )
    return achados


def ler_env(chave: str) -> str | None:
    """Lê do ambiente ou do .env ao lado do script. Sem biblioteca externa:
    instalar pacote depende do proxy, que nem sempre autentica."""
    for nome in _nomes_aceitos(chave):
        if os.environ.get(nome):
            return os.environ[nome]

    env = RAIZ / ".env"
    if not env.exists():
        return None

    aceitos = _nomes_aceitos(chave)
    for linha in env.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        nome, _, valor = linha.partition("=")
        if nome.strip() in aceitos:
            return valor.strip().strip('"').strip("'")
    return None


# O MCP do Outline configurado nesta máquina usa OUTLINE_API_KEY. Aceitar os
# dois nomes evita pedir que o mesmo segredo seja duplicado num .env só porque
# a ferramenta escolheu outro nome.
SINONIMOS = {
    "OUTLINE_API_TOKEN": ("OUTLINE_API_TOKEN", "OUTLINE_API_KEY"),
    "OUTLINE_API_KEY": ("OUTLINE_API_KEY", "OUTLINE_API_TOKEN"),
}


def _nomes_aceitos(chave: str) -> tuple[str, ...]:
    return SINONIMOS.get(chave, (chave,))


# Leitura de artigo do Outline foi removida daqui de propósito: duplicava o
# que o MCP do Outline já faz (autenticado, já conectado em quem usa este
# projeto via agente). Quem precisar dos vídeos de um artigo do Outline busca
# o texto pelo MCP do Outline e chama `urls_em_texto`/`ids_em_texto` nele —
# funções acima, agnósticas de origem. Ver a análise de 2026-08-15.
