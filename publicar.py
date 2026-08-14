"""Por que este módulo existe.

O `redigir.py` grava documento em disco. Isso resolve para quem fica no
terminal e não resolve para o time: documentação que ninguém encontra é
documentação que não existe. Aqui o documento vai para onde as pessoas já
procuram.

Dois destinos, de propósito diferentes entre si: o Outline é API REST, o
Obsidian é arquivo numa pasta. Uma abstração validada contra dois casos
parecidos nasce torta e só se descobre no terceiro.

**As duas travas de segurança moram aqui, não na interface.** Interface se
contorna — basta chamar a função direto. Ver `.claude/rules/seguranca.md`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol

import descobrir
from redigir import Artigo


class PublicarErro(RuntimeError):
    """Recusa ou falha de publicação, para o chamador tratar."""


# --------------------------------------------------------------------------
# o contrato de destino
# --------------------------------------------------------------------------


class Destino(Protocol):
    nome: str
    externo: bool  # True = fora da empresa; recusa material interno

    def publicar(self, artigo: Artigo, *, rascunho: bool = True) -> str:
        """Devolve a URL ou o caminho do que foi criado."""
        ...


def publicar(artigo: Artigo, destino: Destino, *, rascunho: bool = True) -> str:
    """Publica com as duas travas aplicadas antes de qualquer requisição.

    A ordem importa: recusa primeiro, requisição depois. Uma checagem feita
    depois do POST não é checagem, é arrependimento.
    """
    if artigo.bloqueado:
        pendentes = [p for p in artigo.pendencias if p.bloqueia]
        raise PublicarErro(
            f"publicação bloqueada por {len(pendentes)} pendência(s) de "
            f"credencial: {pendentes[0].texto} "
            "Resolva no documento e tente de novo."
        )

    if artigo.front_matter.get("interno", True) and destino.externo:
        raise PublicarErro(
            f"material marcado como interno não vai para `{destino.nome}`, "
            "que é destino externo. Se este conteúdo é mesmo de divulgação, "
            "gere com `--publico` em vez de contornar aqui."
        )

    return destino.publicar(artigo, rascunho=rascunho)


# --------------------------------------------------------------------------
# Obsidian — arquivo numa pasta
# --------------------------------------------------------------------------


class DestinoObsidian:
    """Um cofre do Obsidian é uma pasta de `.md`. Não há API, nem token.

    É o destino mais barato que existe e o mais diferente do Outline, que é
    justamente por que ele entra junto: valida a abstração contra algo que não
    é requisição HTTP.
    """

    externo = False

    def __init__(self, pasta: Path, subpasta: str = "") -> None:
        self.pasta = Path(pasta) / subpasta if subpasta else Path(pasta)
        self.nome = f"obsidian:{self.pasta}"

    def publicar(self, artigo: Artigo, *, rascunho: bool = True) -> str:
        self.pasta.mkdir(parents=True, exist_ok=True)
        arquivo = self.pasta / f"{_nome_seguro(artigo.titulo)}.md"
        # rascunho no Obsidian não é estado do sistema, é convenção de nome:
        # o cofre não tem publicado/não publicado.
        if rascunho:
            arquivo = arquivo.with_name(f"RASCUNHO — {arquivo.name}")
        arquivo.write_text(artigo.markdown(), encoding="utf-8")
        return str(arquivo.resolve())


# --------------------------------------------------------------------------
# Outline — API REST
# --------------------------------------------------------------------------


class DestinoOutline:
    """Instância interna do Outline.

    `publish: false` cria o documento como rascunho, visível só para quem
    criou — é o que sustenta o portão humano quando a revisão não passa pela
    interface.
    """

    externo = False

    def __init__(self, base: str, colecao: str, token: str | None = None) -> None:
        self.base = base.rstrip("/")
        self.colecao = colecao
        self.token = token or descobrir.ler_env("OUTLINE_API_TOKEN")
        self.nome = f"outline:{self.base}"
        if not self.token:
            raise PublicarErro(
                "defina OUTLINE_API_TOKEN (ou OUTLINE_API_KEY) no .env\n"
                "(o token sai em Outline > Settings > API Tokens)"
            )

    def _chamar(self, rota: str, corpo: dict) -> dict:
        requisicao = urllib.request.Request(
            f"{self.base}/api/{rota}",
            data=json.dumps(corpo).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        # instância interna: vai direto, sem passar pelo proxy — mesmo motivo
        # de descobrir.documento_outline
        abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with abridor.open(requisicao, timeout=60) as resposta:
                return json.loads(resposta.read().decode("utf-8"))
        except urllib.error.HTTPError as erro:
            detalhe = erro.read().decode("utf-8", "replace")[:300]
            raise PublicarErro(f"Outline respondeu {erro.code}: {detalhe}") from erro
        except urllib.error.URLError as erro:
            raise PublicarErro(f"Outline inacessível: {erro.reason}") from erro

    def colecoes(self) -> list[dict]:
        dados = self._chamar("collections.list", {"limit": 100})
        return [{"id": c.get("id"), "nome": c.get("name")}
                for c in dados.get("data", [])]

    def publicar(self, artigo: Artigo, *, rascunho: bool = True) -> str:
        # O corpo vai SEM o front-matter: o Outline mostraria o bloco `---`
        # como texto no meio da página. A procedência é do arquivo em disco e
        # de quem indexa, não da leitura humana.
        corpo = artigo.markdown()
        _, _, sem_cabecalho = corpo.partition("\n---\n")

        dados = self._chamar("documents.create", {
            "title": artigo.titulo,
            "text": sem_cabecalho.strip(),
            "collectionId": self.colecao,
            "publish": not rascunho,
        })
        documento = dados.get("data") or {}
        caminho = documento.get("url") or ""
        return f"{self.base}{caminho}" if caminho else str(documento.get("id", ""))


# --------------------------------------------------------------------------
# ler de volta um documento gravado
# --------------------------------------------------------------------------


# Só o que a decisão de publicar precisa. Deliberadamente NÃO é um parser de
# YAML: `pyyaml` exigiria `pip`, e escrever um parser de verdade para ler dois
# campos seria trocar um problema pequeno por um grande. Se um dia o
# front-matter precisar ser lido inteiro, isto aqui não deve crescer — quem lê
# passa a ser quem escreveu (redigir.Artigo).
_TITULO = re.compile(r"^titulo:\s*(.+?)\s*$", re.MULTILINE)
_INTERNO = re.compile(r"^interno:\s*(true|false)\s*$", re.MULTILINE)


def ler_documento(arquivo: Path) -> Artigo:
    """Reconstrói o mínimo de um `Artigo` a partir do `.md` gravado."""
    texto = Path(arquivo).read_text(encoding="utf-8")
    if not texto.startswith("---\n"):
        raise PublicarErro(
            f"{arquivo} não tem front-matter; não dá para saber se o material "
            "é interno, e na dúvida este módulo não publica."
        )

    cabecalho, _, corpo = texto[4:].partition("\n---\n")

    achado = _TITULO.search(cabecalho)
    titulo = (achado.group(1).strip('"') if achado else Path(arquivo).stem)
    interno = True
    marcado = _INTERNO.search(cabecalho)
    if marcado:
        interno = marcado.group(1) == "true"

    artigo = Artigo(titulo=titulo, corpo=corpo.strip(),
                    front_matter={"titulo": titulo, "interno": interno})

    # O bloqueio viaja no texto, não em metadado à parte: o arquivo é a
    # verdade, e alguém pode ter editado o documento à mão entre gerar e
    # publicar.
    if "BLOQUEIA A PUBLICAÇÃO" in corpo:
        from redigir import Pendencia
        artigo.pendencias.append(Pendencia(
            tipo="credencial",
            texto="o documento ainda tem pendência marcada como bloqueante.",
            bloqueia=True,
        ))
    return artigo


# --------------------------------------------------------------------------
# linha de comando
# --------------------------------------------------------------------------


def _nome_seguro(nome: str) -> str:
    nome = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", nome)
    return nome.strip(" .") or "sem-titulo"


def main() -> None:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Publica um documento gerado num destino conectado."
    )
    parser.add_argument("arquivo", nargs="?", help="o .md gerado pelo redigir.py")
    parser.add_argument("--destino", choices=["outline", "obsidian"],
                        default="outline")
    parser.add_argument("--base", default=descobrir.ler_env("OUTLINE_URL") or "",
                        help="https://outline.suaempresa.com (ou OUTLINE_URL no .env)")
    parser.add_argument("--colecao", default="", help="id da coleção do Outline")
    parser.add_argument("--pasta", default=descobrir.ler_env("OBSIDIAN_VAULT") or "",
                        help="cofre do Obsidian (ou OBSIDIAN_VAULT no .env)")
    parser.add_argument("--subpasta", default="", help="subpasta dentro do cofre")
    parser.add_argument("--publicar-direto", action="store_true",
                        help="publica em vez de criar rascunho")
    parser.add_argument("--listar-colecoes", action="store_true",
                        help="mostra as coleções do Outline e sai")
    args = parser.parse_args()

    try:
        if args.listar_colecoes:
            if not args.base:
                sys.exit("informe --base ou defina OUTLINE_URL no .env")
            for colecao in DestinoOutline(args.base, "").colecoes():
                print(f"  {colecao['id']}  {colecao['nome']}")
            return

        if not args.arquivo:
            sys.exit("informe o arquivo .md a publicar")

        artigo = ler_documento(Path(args.arquivo))

        if args.destino == "obsidian":
            if not args.pasta:
                sys.exit("informe --pasta ou defina OBSIDIAN_VAULT no .env")
            destino: Destino = DestinoObsidian(Path(args.pasta), args.subpasta)
        else:
            if not args.base or not args.colecao:
                sys.exit("informe --base e --colecao (veja --listar-colecoes)")
            destino = DestinoOutline(args.base, args.colecao)

        onde = publicar(artigo, destino, rascunho=not args.publicar_direto)
    except PublicarErro as erro:
        sys.exit(f"recusado: {erro}")

    estado = "publicado" if args.publicar_direto else "rascunho"
    print(f"{estado}: {onde}")


if __name__ == "__main__":
    main()
