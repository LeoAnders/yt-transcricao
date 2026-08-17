"""Servidor MCP (Model Context Protocol) para transcrição de vídeos.

Expõe a ferramenta para uma IA — Claude Code, Claude Desktop, qualquer
cliente MCP — em vez de exigir que a pessoa rode comando na mão.

Fala JSON-RPC 2.0 sobre stdio, **implementado só com a biblioteca padrão**.
Não é purismo: `pip install mcp` não funciona nesta máquina, porque o proxy
corporativo exige autenticação integrada do Windows e o pip não sabe fazê-la
(dá 407). Zero dependência é o que torna o servidor instalável aqui.

Registrar no Claude Code:

    claude mcp add yt-transcricao -- python C:/caminho/para/mcp_server.py

O protocolo trafega em stdout, então **nada mais pode escrever ali**: todo
print das outras partes é desviado para stderr.
"""

import contextlib
import json
import sys
import tempfile
from pathlib import Path

import descobrir
import limpar
import quadros
import transcrever

RAIZ = Path(__file__).parent
VERSAO_PROTOCOLO = "2024-11-05"

FERRAMENTAS = [
    {
        "name": "obter_transcricao",
        "description": (
            "Devolve a transcrição de um vídeo do YouTube, a partir da legenda "
            "automática. Aceita URL (normal, curta, Shorts, embed) ou o ID de 11 "
            "caracteres. Se o idioma pedido não existir, usa outro disponível e "
            "informa qual."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "video": {"type": "string", "description": "URL ou ID do vídeo"},
                "idioma": {"type": "string", "description": "código do idioma (padrão: pt)"},
                "com_timestamps": {
                    "type": "boolean",
                    "description": "incluir marcação de tempo (padrão: true)",
                },
            },
            "required": ["video"],
        },
    },
    {
        "name": "extrair_videos",
        "description": (
            "Encontra vídeos do YouTube em um texto ou numa página HTML, sem "
            "transcrever nada. Use para saber o que existe antes de gastar tempo. "
            "Informe 'texto' OU 'url_pagina'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "texto": {"type": "string", "description": "texto/HTML/Markdown qualquer"},
                "url_pagina": {"type": "string", "description": "URL de uma página HTML"},
            },
        },
    },
    {
        "name": "quadros_do_video",
        "description": (
            "Corta um vídeo do YouTube em imagens e devolve os caminhos. Recebe "
            "URL ou ID — baixa o vídeo sozinho. Use SEMPRE que precisar do que "
            "está escrito na tela: nome exato de campo, comando digitado, qual "
            "aba. Vale também para vídeo COM fala, porque a legenda erra jargão "
            "técnico e a tela mostra o literal. Leia as imagens depois."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "video": {"type": "string", "description": "URL ou ID do vídeo"},
                "intervalo_segundos": {
                    "type": "integer",
                    "description": "segundos entre quadros (padrão: 4)",
                },
                "pasta_saida": {"type": "string", "description": "onde gravar"},
            },
            "required": ["video"],
        },
    },
    {
        "name": "extrair_quadros",
        "description": (
            "Corta um arquivo de vídeo LOCAL em imagens. Para vídeo do YouTube "
            "use quadros_do_video, que baixa sozinho."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "caminho_video": {"type": "string", "description": "caminho do arquivo de vídeo"},
                "intervalo_segundos": {
                    "type": "integer",
                    "description": "segundos entre quadros (padrão: 4)",
                },
                "pasta_saida": {"type": "string", "description": "onde gravar (padrão: temporária)"},
            },
            "required": ["caminho_video"],
        },
    },
]


# --------------------------------------------------------------------------
# implementação das ferramentas
# --------------------------------------------------------------------------

def _proxy() -> str | None:
    return transcrever.detectar_proxy()


def _pasta(pedida: str | None, padrao: Path) -> Path:
    """Resolve a pasta de saída para caminho ABSOLUTO.

    Quem lê o resultado é outro processo, com diretório de trabalho próprio —
    devolver caminho relativo faz a imagem "não existir" do outro lado.
    """
    if not pedida:
        return padrao
    caminho = Path(pedida)
    return caminho if caminho.is_absolute() else RAIZ / caminho


def obter_transcricao(video: str, idioma: str = "pt",
                      com_timestamps: bool = True) -> str:
    urls = descobrir.normalizar([video])
    if not urls:
        return f"não reconheci '{video}' como vídeo do YouTube."

    with tempfile.TemporaryDirectory() as tmp:
        pasta = Path(tmp)
        pendentes = transcrever.baixar_legendas(urls, pasta, _proxy(), idioma)
        if pendentes:
            return (
                f"{urls[0]} não tem legenda automática em nenhum idioma.\n"
                "Vídeo sem fala não gera legenda — use quadros_do_video para "
                "ler o que está escrito na tela."
            )

        vtt = next(iter(sorted(pasta.glob("*.vtt"))))
        video_id, titulo = limpar.nome_do_arquivo(vtt)
        paragrafos = limpar.agrupar(
            limpar.extrair_falas(vtt.read_text(encoding="utf-8"))
        )
        corpo = limpar.montar_corpo(paragrafos, com_timestamps)

    return (
        f"# {titulo}\n\n"
        f"- Vídeo: https://youtu.be/{video_id}\n"
        f"- Origem: legenda automática do YouTube, não revisada "
        f"(reconhecimento de fala: jargão técnico sai torto)\n\n"
        f"---\n\n{corpo}"
    )


def extrair_videos(texto: str | None = None,
                   url_pagina: str | None = None) -> str:
    if url_pagina:
        conteudo_urls = descobrir.de_pagina(url_pagina)
        achados = [{"url": u, "rotulo_na_documentacao": None} for u in conteudo_urls]
    elif texto:
        achados = descobrir.videos_com_rotulo(texto)
    else:
        return "informe 'texto' ou 'url_pagina'."

    if not achados:
        return "nenhum vídeo do YouTube encontrado."

    linhas = [f"{len(achados)} vídeo(s):\n"]
    for item in achados:
        rotulo = item.get("rotulo_na_documentacao")
        linhas.append(f"- {rotulo + ' — ' if rotulo else ''}{item['url']}")
    return "\n".join(linhas)


def quadros_do_video(video: str, intervalo_segundos: int = 4,
                     pasta_saida: str | None = None) -> str:
    urls = descobrir.normalizar([video])
    if not urls:
        return f"não reconheci '{video}' como vídeo do YouTube."
    if not quadros.ffmpeg_disponivel():
        return ("ffmpeg não encontrado no PATH.\n"
                "instale com: winget install Gyan.FFmpeg")

    url = urls[0]
    video_id = url.split("v=")[-1]
    destino = _pasta(pasta_saida, RAIZ / "quadros" / video_id)

    # o .mp4 morre com a pasta temporária: o entregável é a imagem
    with tempfile.TemporaryDirectory() as tmp:
        origem = transcrever.baixar_video(
            url, Path(tmp) / f"{video_id}.mp4", _proxy()
        )
        if origem["arquivo"] is None:
            return f"não consegui baixar {url}: {origem['erro']}"
        relatorio = quadros.extrair_com_relatorio(
            origem["arquivo"], destino, intervalo_segundos
        )
        tem_audio = origem["tem_audio"]

    linhas = [
        f"{url} — {len(relatorio['quadros'])} quadro(s) a cada "
        f"{intervalo_segundos}s, áudio na origem: "
        f"{'sim' if tem_audio else 'NÃO (vídeo mudo)'}\n",
    ]
    for quadro in relatorio["quadros"]:
        linhas.append(f"- ({quadro['instante']}) {quadro['arquivo']}")

    if tem_audio:
        linhas.append(
            "\nO vídeo tem fala: use obter_transcricao junto. A fala diz o "
            "porquê, o quadro diz o literal — e a legenda automática erra "
            "jargão técnico, então o quadro é o que corrige."
        )
    else:
        linhas.append("\nLeia as imagens para saber o que está escrito na tela.")
    return "\n".join(linhas)


def extrair_quadros(caminho_video: str, intervalo_segundos: int = 4,
                    pasta_saida: str | None = None) -> str:
    video = Path(caminho_video)
    if not video.exists():
        return f"arquivo não encontrado: {video}"

    destino = _pasta(pasta_saida, video.parent / "quadros")
    relatorio = quadros.extrair_com_relatorio(video, destino, intervalo_segundos)

    linhas = [
        f"{video.name} — duração "
        f"{relatorio['duracao_segundos']:.0f}s, "
        f"áudio: {'sim' if relatorio['tem_audio'] else 'NÃO (vídeo mudo)'}",
        f"{len(relatorio['quadros'])} quadro(s) a cada {intervalo_segundos}s:\n",
    ]
    for quadro in relatorio["quadros"]:
        linhas.append(f"- ({quadro['instante']}) {quadro['arquivo']}")
    linhas.append("\nLeia as imagens para saber o que está escrito na tela.")
    return "\n".join(linhas)


EXECUTORES = {
    "obter_transcricao": obter_transcricao,
    "extrair_videos": extrair_videos,
    "quadros_do_video": quadros_do_video,
    "extrair_quadros": extrair_quadros,
}


# --------------------------------------------------------------------------
# transporte JSON-RPC
# --------------------------------------------------------------------------

def responder(id_requisicao, resultado=None, erro=None) -> None:
    mensagem = {"jsonrpc": "2.0", "id": id_requisicao}
    if erro is not None:
        mensagem["error"] = erro
    else:
        mensagem["result"] = resultado
    sys.stdout.write(json.dumps(mensagem, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def tratar(mensagem: dict) -> None:
    metodo = mensagem.get("method")
    id_requisicao = mensagem.get("id")

    # notificações não têm id e não recebem resposta
    if id_requisicao is None:
        return

    if metodo == "initialize":
        pedida = (mensagem.get("params") or {}).get("protocolVersion")
        responder(id_requisicao, {
            "protocolVersion": pedida or VERSAO_PROTOCOLO,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "yt-transcricao", "version": "1.0.0"},
        })

    elif metodo == "tools/list":
        responder(id_requisicao, {"tools": FERRAMENTAS})

    elif metodo == "tools/call":
        parametros = mensagem.get("params") or {}
        nome = parametros.get("name")
        argumentos = parametros.get("arguments") or {}

        executor = EXECUTORES.get(nome)
        if executor is None:
            responder(id_requisicao, erro={
                "code": -32601, "message": f"ferramenta desconhecida: {nome}",
            })
            return

        try:
            # o stdout é do protocolo; prints das outras partes vão para stderr
            with contextlib.redirect_stdout(sys.stderr):
                texto = executor(**argumentos)
            responder(id_requisicao, {
                "content": [{"type": "text", "text": texto}],
            })
        except SystemExit as parada:
            responder(id_requisicao, {
                "content": [{"type": "text", "text": f"erro: {parada}"}],
                "isError": True,
            })
        except Exception as falha:
            responder(id_requisicao, {
                "content": [{"type": "text",
                             "text": f"{type(falha).__name__}: {falha}"}],
                "isError": True,
            })

    else:
        responder(id_requisicao, erro={
            "code": -32601, "message": f"método não suportado: {metodo}",
        })


def main() -> None:
    # UTF-8 nos dois sentidos: os títulos e o texto são em pt-BR
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    for linha in sys.stdin:
        linha = linha.strip()
        if not linha:
            continue
        try:
            mensagem = json.loads(linha)
        except json.JSONDecodeError:
            continue
        tratar(mensagem)


if __name__ == "__main__":
    main()
