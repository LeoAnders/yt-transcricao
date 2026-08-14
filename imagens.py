"""Extrai as imagens de um artigo do Outline para que uma IA leia o que elas
mostram.

Documentação técnica coloca na figura justamente a parte que o texto não
descreve — onde clicar, qual aba, qual campo. Uma IA lendo o Markdown vê só
`![](/api/attachments.redirect?id=...)`, ou seja, nada. Este módulo baixa as
imagens e devolve cada uma junto do texto que a antecede no documento, que é
o contexto sem o qual uma pasta de PNGs não significa nada.

Serve também para auditoria: print de tela de sistema costuma vazar token,
senha e dado de cliente. Varrer os artigos e ler as imagens encontra isso.
"""

import json
import re
import sys
import urllib.request
from pathlib import Path

import descobrir

# ![legenda](/api/attachments.redirect?id=UUID) — a legenda é opcional e o
# Outline às vezes escreve o tamanho ali dentro ("null 495x324")
RE_ANEXO = re.compile(
    r"!?\[([^\]]*)\]\(\s*(?:/api/attachments\.redirect\?id=|"
    r"https?://[^/]+/api/attachments\.redirect\?id=)([0-9a-f-]{36})"
)

EXTENSOES_IMAGEM = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def anexos_com_contexto(texto: str, caracteres: int = 300) -> list[dict]:
    """Acha os anexos e captura o texto que vem antes de cada um.

    O contexto é o que transforma "imagem 3" em "a figura que ilustra a
    liberação de endpoints por usuário".
    """
    achados = []
    for casa in RE_ANEXO.finditer(texto):
        legenda, anexo_id = casa.group(1), casa.group(2)

        antes = texto[max(0, casa.start() - caracteres):casa.start()]
        # a última linha não vazia antes da imagem costuma ser a frase que a
        # apresenta
        linhas = [l.strip() for l in antes.splitlines() if l.strip()]
        contexto = linhas[-1] if linhas else ""

        achados.append({
            "id": anexo_id,
            "legenda": legenda.strip(),
            "contexto_anterior": contexto,
        })
    return achados


def _abridor():
    """Instância interna do Outline: vai direto, sem passar pelo proxy."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def url_assinada(base: str, anexo_id: str, token: str) -> tuple[str, str]:
    """Pede ao Outline a URL assinada e o nome do arquivo do anexo.

    Devolve (url, nome). A `attachments.redirect` responde 302 para uma URL
    de curta duração; o urllib segue o redirecionamento sozinho.
    """
    requisicao = urllib.request.Request(
        f"{base}/api/attachments.redirect?id={anexo_id}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with _abridor().open(requisicao, timeout=30) as resposta:
        return resposta.geturl(), resposta.headers.get("Content-Type", "")


def baixar(base: str, anexo_id: str, token: str, destino: Path,
           nome: str) -> Path | None:
    """Baixa um anexo. Devolve o caminho, ou None se não for imagem."""
    requisicao = urllib.request.Request(
        f"{base}/api/attachments.redirect?id={anexo_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with _abridor().open(requisicao, timeout=60) as resposta:
        tipo = resposta.headers.get("Content-Type", "")
        conteudo = resposta.read()

    if not tipo.startswith("image/"):
        return None

    extensao = "." + (tipo.split("/")[-1].split(";")[0] or "png")
    if extensao == ".jpeg":
        extensao = ".jpg"

    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / f"{nome}{extensao}"
    arquivo.write_bytes(conteudo)
    return arquivo


def do_artigo(url_artigo: str, destino: Path | None = None) -> dict:
    """Baixa todas as imagens de um artigo do Outline.

    Devolve o título, a pasta e a lista de imagens com contexto — pronto para
    a IA ler cada arquivo sabendo do que ele trata.
    """
    token = descobrir.ler_env("OUTLINE_API_TOKEN")
    if not token:
        sys.exit(
            "defina OUTLINE_API_TOKEN no .env\n"
            "(o token sai em Outline > Settings > API Tokens)"
        )

    titulo, texto = descobrir.documento_outline(url_artigo)
    base = "/".join(url_artigo.split("/")[:3])
    anexos = anexos_com_contexto(texto)

    if destino is None:
        from transcrever import _seguro
        destino = Path(__file__).parent / "imagens" / _seguro(titulo)

    resultado = []
    for indice, anexo in enumerate(anexos, start=1):
        arquivo = baixar(base, anexo["id"], token, destino, f"{indice:02d}")
        if arquivo is None:
            resultado.append({**anexo, "arquivo": None,
                              "observacao": "não é imagem (vídeo ou outro anexo)"})
            continue
        resultado.append({**anexo, "arquivo": str(arquivo)})

    return {"titulo": titulo, "pasta": str(destino), "imagens": resultado}


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(
        description="Baixa as imagens de um artigo do Outline para leitura por IA.",
    )
    ap.add_argument("url_artigo", help="URL do artigo no Outline")
    ap.add_argument("--saida", help="pasta de destino")
    args = ap.parse_args()

    relatorio = do_artigo(
        args.url_artigo, Path(args.saida) if args.saida else None
    )

    print(f'artigo: "{relatorio["titulo"]}"')
    print(f"pasta: {relatorio['pasta']}\n")
    for imagem in relatorio["imagens"]:
        if imagem.get("arquivo"):
            print(f"  {Path(imagem['arquivo']).name}")
        else:
            print(f"  (pulado) {imagem.get('observacao')}")
        if imagem["contexto_anterior"]:
            print(f"      contexto: {imagem['contexto_anterior'][:90]}")
    print(f"\n{sum(1 for i in relatorio['imagens'] if i.get('arquivo'))} imagem(ns).")


if __name__ == "__main__":
    main()
