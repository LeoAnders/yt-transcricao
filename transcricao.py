"""Por que este módulo existe.

**Transcrição pura**: um link de vídeo do YouTube entra, texto sai. Nada de
LLM, nada de documento redigido, nada de `redigir.py`.

A API já tinha `/api/gerar`, que transcreve **e depois** redige com o `claude`
da máquina. Isso é útil para gerar documentação, e é exatamente o que um
consumidor que só quer o texto não pode chamar: ele paga o tempo do LLM, e o
resultado vem interpretado quando o que ele queria era o dado. O primeiro
consumidor desse recorte é o Vidport, que resume com o Codex do próprio
usuário — e portanto não pode ter Claude no caminho.

Este módulo não é uma reimplementação: ele **compõe** o que já existe —
`transcrever.baixar_legendas` para a parte de rede (proxy, yt-dlp, o desvio
pelo player *android vr* que faz a legenda existir fora do navegador) e
`limpar.*` para converter o `.vtt` rolante em parágrafos legíveis.

Devolve `dict`, não Markdown: quem chama monta a apresentação que quiser. O
`obter_transcricao` do MCP continua devolvendo Markdown porque quem lê ali é
um modelo numa conversa.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import descobrir
import limpar
import transcrever

# Idioma padrão da legenda. Mesmo valor da linha de comando.
IDIOMA_PADRAO = "pt"


class SemLegenda(Exception):
    """O vídeo não tem legenda automática em nenhum idioma.

    Não é falha da ferramenta: vídeo sem fala não gera legenda. Merece
    exceção própria para quem chama poder dizer isso ao usuário em vez de
    mostrar "erro".
    """


class VideoInvalido(Exception):
    """O que veio não é link/ID de vídeo do YouTube."""


def obter(video: str, idioma: str = IDIOMA_PADRAO,
          com_timestamps: bool = True) -> dict:
    """Transcreve um vídeo e devolve os dados.

    ```
    {
      "videoId": "...",
      "titulo": "...",
      "url": "https://youtu.be/...",
      "idioma": "pt",
      "origem": "youtube_auto_caption",
      "texto": "(00:00) ...",
      "paragrafos": [{"segundo": 0, "texto": "..."}],
    }
    ```

    `paragrafos` vai junto com `texto` de propósito: o texto serve para ler e
    para mandar a um modelo, os parágrafos servem para quem quer os tempos
    sem reparsear o que a gente acabou de formatar.
    """
    urls = descobrir.normalizar([video])
    if not urls:
        raise VideoInvalido(f"não reconheci '{video}' como vídeo do YouTube")

    url = urls[0]

    # Pasta temporária: o `.vtt` é insumo, não resultado. Gravá-lo em
    # `transcricoes/` deixaria legenda crua acumulando no disco de quem só
    # pediu o texto — e `transcricoes/` está no .gitignore por conter
    # conteúdo potencialmente sensível (ver .claude/rules/seguranca.md).
    with tempfile.TemporaryDirectory() as tmp:
        pasta = Path(tmp)
        pendentes = transcrever.baixar_legendas(
            urls, pasta, transcrever.detectar_proxy(), idioma
        )
        if pendentes:
            raise SemLegenda(
                f"{url} não tem legenda automática em nenhum idioma"
            )

        vtts = sorted(pasta.glob("*.vtt"))
        if not vtts:
            # baixar_legendas disse que baixou, mas não há arquivo: cobre o
            # caso de o yt-dlp gravar com nome inesperado em vez de estourar
            # IndexError aqui dentro.
            raise SemLegenda(f"nenhuma legenda foi gravada para {url}")

        vtt = vtts[0]
        video_id, titulo = limpar.nome_do_arquivo(vtt)
        paragrafos = limpar.agrupar(
            limpar.extrair_falas(vtt.read_text(encoding="utf-8"))
        )
        texto = limpar.montar_corpo(paragrafos, com_timestamps)
        idioma_real = _idioma_do_arquivo(vtt) or idioma

    return {
        "videoId": video_id,
        "titulo": titulo,
        "url": f"https://youtu.be/{video_id}",
        "idioma": idioma_real,
        "origem": "youtube_auto_caption",
        "texto": texto,
        "paragrafos": [
            {"segundo": segundo, "texto": trecho} for segundo, trecho in paragrafos
        ],
    }


def _idioma_do_arquivo(vtt: Path) -> str | None:
    """Lê o idioma do sufixo que o yt-dlp acrescenta (`.pt-orig.vtt`).

    Importa porque existe fallback: pedimos `pt` e o vídeo pode ser em `en`.
    Quem chama precisa saber em que idioma o texto veio, senão manda resumir
    "em português" um texto em inglês sem perceber.
    """
    partes = vtt.name.split(".")
    if len(partes) < 3:
        return None
    codigo = partes[-2]
    return codigo.removesuffix("-orig") or None
