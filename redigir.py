"""Por que este módulo existe.

O resto do projeto entrega **insumo**: uma pasta de `.md` crus, um por vídeo,
cheios do jargão torto que o reconhecimento de fala do YouTube produz. Ninguém
lê isso, e uma IA que consome isso reproduz o ruído.

Aqui o insumo vira documento: agrupado por assunto (não por vídeo), escrito
como procedimento, com a procedência no cabeçalho para quem for indexar, e —
o mais importante — com a lista do que a máquina **não conseguiu decidir
sozinha**.

O que sai daqui é proposta, nunca verdade publicável. A transcrição não sabe
que envelheceu, e o conteúdo extraído já continha token de API real legível em
print de tela. Ver `.claude/rules/seguranca.md`.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# Medido em 2026-08-14, mesma pergunta trivial, mesma máquina: o `claude` sobe
# com 50.782 tokens de contexto quando herda o diretório do projeto (CLAUDE.md,
# as skills, o schema de cada MCP conectado) e com 7.279 tokens com estes flags
# rodando fora dele — US$ 0,30 contra US$ 0,04 por chamada. Este módulo chama
# uma vez por assunto e uma por lote de quadros, então tirar qualquer um dos
# dois multiplica a conta por sete sem ganhar nada: o modelo não precisa do
# contexto do projeto, tudo que ele usa vai no prompt.
FLAGS_ENXUTOS = ["--tools", "", "--strict-mcp-config"]

# Quadros por chamada. Mais que isso e o contexto da leitura de imagem começa a
# competir com a instrução; menos e o modelo perde a continuidade da tela.
QUADROS_POR_LOTE = 12

ESPERA_PADRAO = 900  # segundos; artigo grande com muitos assuntos demora


class RedigirErro(RuntimeError):
    """Falha que o chamador precisa ver, não exceção que mata o processo."""


# --------------------------------------------------------------------------
# estruturas
# --------------------------------------------------------------------------


@dataclass
class Transcricao:
    video_id: str
    titulo: str
    texto: str
    leitura: str = "legenda"  # legenda | quadros
    duracao: str = ""


@dataclass
class Quadro:
    video_id: str
    instante: str
    caminho: Path


@dataclass
class Imagem:
    caminho: Path
    legenda: str = ""


@dataclass
class Material:
    """Tudo que existe sobre um assunto, antes de virar texto.

    `texto_artigo` é o que a página escrita afirma. É o campo que torna a
    revisão inteligente: sem ele não há como detectar que o vídeo ensina um
    caminho que a documentação já desaconselhou. Quando a entrada é link solto
    ele vem vazio, e essa classe de pendência simplesmente não é gerada.
    """

    titulo: str
    fonte: str = ""
    fonte_tipo: str = "links"  # outline | notion | links | texto
    interno: bool = True
    texto_artigo: str = ""
    transcricoes: list[Transcricao] = field(default_factory=list)
    quadros: list[Quadro] = field(default_factory=list)
    imagens: list[Imagem] = field(default_factory=list)


@dataclass
class Pendencia:
    tipo: str  # credencial | conflito | jargao | idade
    texto: str
    bloqueia: bool = False
    referencia: str = ""


@dataclass
class Artigo:
    titulo: str
    corpo: str
    front_matter: dict = field(default_factory=dict)
    pendencias: list[Pendencia] = field(default_factory=list)

    @property
    def bloqueado(self) -> bool:
        return any(p.bloqueia for p in self.pendencias)

    def markdown(self) -> str:
        """O documento como vai para o disco, com as pendências NO TOPO.

        Elas ficam antes do conteúdo de propósito: quem abre o arquivo tem que
        esbarrar no que ainda não foi decidido antes de acreditar no resto. Um
        destilado entregue como verdade é o modo conhecido de este fluxo dar
        errado — ver a skill `extrair-conhecimento`.
        """
        partes = [f"---\n{_yaml(self.front_matter)}---\n"]
        if self.pendencias:
            partes.append(_bloco_pendencias(self.pendencias))
        partes.append(self.corpo.strip() + "\n")
        return "\n".join(partes)


# --------------------------------------------------------------------------
# chamada ao modelo
# --------------------------------------------------------------------------


def _executavel() -> str:
    caminho = shutil.which("claude")
    if caminho is None:
        raise RedigirErro(
            "`claude` não encontrado no PATH. Este módulo usa o Claude Code já "
            "instalado na máquina — não há SDK a instalar, porque `pip` está "
            "bloqueado pelo proxy (ver CLAUDE.md)."
        )
    return caminho


def _chamar(prompt: str, *, ferramentas: str = "",
            pastas: list[Path] | None = None,
            espera: int = ESPERA_PADRAO) -> str:
    """Roda `claude -p` e devolve o texto da resposta.

    O prompt vai por **stdin**, nunca em argv: um único artigo já rendeu 23.420
    palavras, e a linha de comando do Windows corta em ~32 mil caracteres sem
    dizer que cortou. O sintoma de quem "simplifica" para `-p "$texto"` é um
    prompt truncado que produz texto plausível e errado.
    """
    executavel = _executavel()
    comando = [executavel, "-p", "--output-format", "json",
               "--tools", ferramentas, "--strict-mcp-config"]
    for pasta in pastas or []:
        comando += ["--add-dir", str(pasta)]

    # O cwd é uma pasta neutra de propósito: rodar dentro do projeto faz o
    # `claude` carregar CLAUDE.md e as skills, que este prompt não usa — ver a
    # medição em FLAGS_ENXUTOS.
    try:
        saida = subprocess.run(
            comando,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=tempfile.gettempdir(),
            timeout=espera,
        )
    except subprocess.TimeoutExpired as erro:
        raise RedigirErro(f"`claude` não respondeu em {espera}s") from erro

    if saida.returncode != 0:
        raise RedigirErro(
            f"`claude` saiu com código {saida.returncode}: "
            f"{(saida.stderr or '').strip()[:400]}"
        )

    try:
        envelope = json.loads(saida.stdout)
    except json.JSONDecodeError as erro:
        raise RedigirErro(
            f"resposta do `claude` não é JSON: {saida.stdout[:400]}"
        ) from erro

    if envelope.get("is_error"):
        raise RedigirErro(f"`claude` reportou erro: {envelope.get('result')}")

    return envelope.get("result", "")


def _json_do_modelo(bruto: str) -> dict:
    """Extrai o objeto JSON da resposta.

    Mesmo instruído a devolver só JSON, o modelo às vezes embrulha em cerca de
    código ou emenda uma frase antes. Recortar do primeiro `{` ao último `}` é
    mais barato que insistir no prompt.
    """
    texto = bruto.strip()
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto, flags=re.MULTILINE)
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fim <= inicio:
        raise RedigirErro(f"nenhum objeto JSON na resposta: {bruto[:300]}")
    try:
        return json.loads(texto[inicio:fim + 1])
    except json.JSONDecodeError as erro:
        raise RedigirErro(f"JSON inválido na resposta: {erro}") from erro


# --------------------------------------------------------------------------
# quadros → texto
# --------------------------------------------------------------------------


REGRAS_QUADROS = """\
Você está lendo quadros extraídos de uma gravação de tela SEM narração, de um
sistema ERP. O quadro é a única fonte: a legenda não existe.

Descreva o que a tela mostra em texto útil para reconstruir o procedimento:
- nome literal de rotina, campo, aba, botão e menu, exatamente como aparece;
- comando digitado e a resposta que o sistema deu, transcritos;
- mensagem de erro, com o texto exato;
- a ordem em que as coisas acontecem.

Não descreva a aparência ("uma tela escura com texto branco"). Descreva o
conteúdo.

IGNORE o que não faz parte da rotina documentada: aba de navegador, barra de
tarefas, notificação, relógio, nome de outra ferramenta aberta ao fundo. Isso
não ajuda ninguém a executar o procedimento e ainda expõe o ambiente de quem
gravou.

ATENÇÃO — segurança: se algum quadro mostrar credencial (token, senha, chave de
API, header Authorization, usuário em prompt de autenticação), NÃO transcreva o
valor. Registre a ocorrência em `credenciais`, dizendo apenas onde está.

Responda com um único objeto JSON:
{"texto": "<a descrição corrida>",
 "credenciais": [{"instante": "MM:SS", "onde": "<qual campo/tela>"}]}
"""


def descrever_quadros(quadros_do_video: list[Quadro], titulo: str,
                      *, por_lote: int = QUADROS_POR_LOTE
                      ) -> tuple[str, list[Pendencia]]:
    """Converte os quadros de UM vídeo em texto, e denuncia credencial na tela.

    Precisa da ferramenta `Read` (é o que abre a imagem) e de `--add-dir` na
    pasta dos quadros, porque o cwd da chamada é neutro.
    """
    if not quadros_do_video:
        return "", []

    pastas = sorted({q.caminho.parent.resolve() for q in quadros_do_video})
    partes: list[str] = []
    pendencias: list[Pendencia] = []

    for inicio in range(0, len(quadros_do_video), por_lote):
        lote = quadros_do_video[inicio:inicio + por_lote]
        lista = "\n".join(
            f"- {q.instante} → {q.caminho.resolve()}" for q in lote
        )
        prompt = (
            f"{REGRAS_QUADROS}\n"
            f"Vídeo: {titulo}\n"
            f"Leia estes quadros, na ordem:\n{lista}\n"
        )
        dados = _json_do_modelo(_chamar(prompt, ferramentas="Read", pastas=pastas))
        if dados.get("texto"):
            partes.append(str(dados["texto"]).strip())

        for achado in dados.get("credenciais") or []:
            instante = str(achado.get("instante", "?"))
            pendencias.append(Pendencia(
                tipo="credencial",
                texto=(
                    f"Possível credencial na tela em {instante}, "
                    f"em {achado.get('onde', 'campo não identificado')}. "
                    "Confira e recorte o quadro antes de publicar."
                ),
                bloqueia=True,
                referencia=f"{lote[0].video_id}@{instante}",
            ))

    return "\n\n".join(partes), pendencias


# --------------------------------------------------------------------------
# agrupar por assunto
# --------------------------------------------------------------------------


REGRAS_AGRUPAR = """\
Você recebe a lista de vídeos de um artigo de documentação técnica. Agrupe-os
por ASSUNTO, não por vídeo: dezenove vídeos de "implementar uma API" costumam
ser três ou quatro assuntos, e é isso que impede o número de arquivos de
crescer junto com o número de vídeos.

Regras:
- todo vídeo entra em exatamente um assunto;
- respeite a ordem em que os vídeos aparecem — ela costuma ser a ordem do
  procedimento;
- o título do assunto é o que a pessoa procuraria, não o nome do vídeo.

Responda com um único objeto JSON:
{"assuntos": [{"titulo": "<assunto>", "videos": ["<id>", "<id>"]}]}
"""


def agrupar_assuntos(material: Material, *, amostra_linhas: int = 25) -> list[dict]:
    """Primeira passagem: só títulos e o começo de cada transcrição.

    É deliberadamente barata. Mandar as transcrições inteiras aqui estoura o
    contexto no artigo grande, que é justamente o que precisa de agrupamento.
    """
    if len(material.transcricoes) <= 1:
        return [{
            "titulo": material.titulo,
            "videos": [t.video_id for t in material.transcricoes],
        }]

    blocos = []
    for t in material.transcricoes:
        amostra = "\n".join(t.texto.splitlines()[:amostra_linhas])
        blocos.append(
            f"### {t.video_id} — {t.titulo} ({t.leitura})\n{amostra}"
        )

    prompt = (
        f"{REGRAS_AGRUPAR}\n"
        f"Artigo: {material.titulo}\n\n"
        + "\n\n".join(blocos)
    )
    dados = _json_do_modelo(_chamar(prompt))
    assuntos = dados.get("assuntos") or []
    if not assuntos:
        raise RedigirErro("o agrupamento não devolveu assunto nenhum")
    return assuntos


# --------------------------------------------------------------------------
# redigir um assunto
# --------------------------------------------------------------------------


REGRAS_REDIGIR = """\
Transforme o material abaixo em documentação que uma pessoa leia e uma IA
consuma. O mesmo texto serve os dois — o que difere é o cuidado, não o formato.

COMO ESCREVER
- Procedimento, não resumo: passos numerados, na ordem em que acontecem.
- Cada `##` é uma unidade de assunto fechada. Quem cair direto nela entende.
- Nome exato sempre, pronome nunca. "na aba `Serviço` do Cadastro de Usuário",
  jamais "na aba mencionada acima" — referência que depende do parágrafo
  anterior quebra tanto o leitor quanto o recorte de indexação.
- Reconstrua o jargão que o reconhecimento de fala destruiu, usando o contexto
  e o que os quadros mostram. Se deduziu, registre em `pendencias`.
- Diga o que dá errado e a mensagem que aparece.
- Registre o que a documentação escrita omite e só o vídeo mostra.
- Quando houver "QUADROS DISPONÍVEIS" de um vídeo, ilustre os passos que se
  beneficiam de imagem embutindo o quadro em Markdown com o caminho EXATO da
  lista — `![tela em 00:04:18](quadros/<id>/quadro_003.jpg)` — e nunca invente
  um caminho que não esteja listado. Sem quadro disponível, cite só o instante
  entre parênteses: `(00:04:18)`.
- Descarte saudação, "como falei no vídeo anterior", passo dito e refeito.

O QUE VIRA PENDÊNCIA (o que você NÃO pode decidir sozinho)
- `conflito`: o vídeo ensina um caminho e o texto escrito do artigo diz outra
  coisa. Nunca escolha em silêncio.
- `jargao`: termo que você deduziu e não tem certeza.
- `idade`: procedimento que parece ter envelhecido — tela com campo que o texto
  não menciona, versão citada, ferramenta descontinuada.
Fato técnico verificável no próprio material, você resolve; não vira pendência.

Responda com um único objeto JSON:
{"titulo": "<título do documento>",
 "corpo": "<markdown, SEM front-matter e SEM título de nível 1>",
 "pendencias": [{"tipo": "conflito|jargao|idade",
                 "texto": "<o que conferir, em uma ou duas frases>",
                 "referencia": "<id do vídeo e instante, ou o trecho do artigo>"}]}
"""


def _redigir_assunto(material: Material, assunto: dict,
                     descricoes: dict[str, str]) -> Artigo:
    ids = set(assunto.get("videos") or [])
    escolhidas = [t for t in material.transcricoes if t.video_id in ids]

    blocos = []
    for t in escolhidas:
        texto = descricoes.get(t.video_id) or t.texto
        origem = "quadros da tela" if t.leitura == "quadros" else "legenda automática"
        blocos.append(f"### {t.titulo}  [{t.video_id}, {origem}]\n{texto}")

        # caminho relativo à pasta do artigo (últimos 3 segmentos: sempre
        # "quadros/<id>/quadro_NNN.jpg", venha `pasta` relativa ou absoluta) —
        # é esse o caminho que o modelo deve embutir, nunca o absoluto: o
        # documento não deve carregar a estrutura de disco de quem gerou.
        do_video = [q for q in material.quadros if q.video_id == t.video_id]
        if do_video:
            lista = "\n".join(
                f"  {q.instante} → {'/'.join(q.caminho.parts[-3:])}" for q in do_video
            )
            blocos.append(f"QUADROS DISPONÍVEIS de {t.video_id}:\n{lista}")

    partes = [REGRAS_REDIGIR, f"Assunto: {assunto.get('titulo', material.titulo)}"]
    if material.texto_artigo.strip():
        partes.append(
            "TEXTO ESCRITO DO ARTIGO (compare com os vídeos; divergência vira "
            f"pendência do tipo `conflito`):\n{material.texto_artigo.strip()}"
        )
    if material.imagens:
        listadas = "\n".join(
            f"- {i.caminho.name}{f' — {i.legenda}' if i.legenda else ''}"
            for i in material.imagens
        )
        partes.append(f"IMAGENS DISPONÍVEIS NO ARTIGO:\n{listadas}")
    partes.append("MATERIAL DOS VÍDEOS:\n" + "\n\n".join(blocos))

    dados = _json_do_modelo(_chamar("\n\n".join(partes)))

    pendencias = [
        Pendencia(
            tipo=str(p.get("tipo", "jargao")),
            texto=str(p.get("texto", "")).strip(),
            bloqueia=False,
            referencia=str(p.get("referencia", "")),
        )
        for p in (dados.get("pendencias") or [])
        if str(p.get("texto", "")).strip()
    ]

    return Artigo(
        titulo=str(dados.get("titulo") or assunto.get("titulo") or material.titulo),
        corpo=str(dados.get("corpo") or "").strip(),
        pendencias=pendencias,
    )


def redigir(material: Material) -> list[Artigo]:
    """Material bruto → um `Artigo` por assunto, com as pendências ao lado.

    Duas passagens: agrupar e depois redigir. Uma chamada só, com tudo dentro,
    não cabe no contexto no artigo grande — e artigo grande é o caso que
    importa.
    """
    if not material.transcricoes:
        raise RedigirErro("nada a redigir: o material não tem transcrição")

    # Quadros viram texto antes de tudo, porque a partir daqui o resto do fluxo
    # é textual — inclusive o agrupamento, que precisa saber do que o vídeo mudo
    # trata.
    descricoes: dict[str, str] = {}
    bloqueios: list[Pendencia] = []
    por_video: dict[str, list[Quadro]] = {}
    for q in material.quadros:
        por_video.setdefault(q.video_id, []).append(q)

    for t in material.transcricoes:
        lote = por_video.get(t.video_id) or []
        if not lote:
            continue
        texto, achados = descrever_quadros(lote, t.titulo)
        if texto:
            descricoes[t.video_id] = (
                f"{t.texto}\n\n[da tela]\n{texto}" if t.texto.strip() else texto
            )
        bloqueios.extend(achados)

    artigos = []
    for assunto in agrupar_assuntos(material):
        artigo = _redigir_assunto(material, assunto, descricoes)
        # A pendência de credencial é do material, não do assunto: ela acompanha
        # todo documento que use aquele vídeo, senão um dos arquivos sai sem o
        # bloqueio e é justamente esse que alguém publica.
        ids = set(assunto.get("videos") or [])
        artigo.pendencias.extend(
            p for p in bloqueios if p.referencia.split("@")[0] in ids
        )
        artigo.front_matter = _front_matter(material, artigo, assunto)
        artigos.append(artigo)

    return artigos


# --------------------------------------------------------------------------
# front-matter
# --------------------------------------------------------------------------


def _bloco_pendencias(pendencias: list[Pendencia]) -> str:
    linhas = ["## ⚠️ Conferir antes de usar", ""]
    # bloqueio primeiro: credencial na tela não é uma dúvida entre outras
    for p in sorted(pendencias, key=lambda p: not p.bloqueia):
        marca = "**BLOQUEIA A PUBLICAÇÃO** — " if p.bloqueia else ""
        origem = f" _({p.referencia})_" if p.referencia else ""
        linhas.append(f"- {marca}{p.texto}{origem}")
    return "\n".join(linhas) + "\n"


def _front_matter(material: Material, artigo: Artigo, assunto: dict) -> dict:
    ids = set(assunto.get("videos") or [])
    return {
        "titulo": artigo.titulo,
        "fonte": material.fonte,
        "fonte_tipo": material.fonte_tipo,
        # Trava de destino: quem publica recusa destino externo com isto ligado.
        # A checagem é no `publicar`, não na interface — interface se contorna.
        "interno": material.interno,
        "videos": [
            {"id": t.video_id, "titulo": t.titulo, "leitura": t.leitura}
            for t in material.transcricoes if t.video_id in ids
        ],
        "revisado": False,
    }


def _yaml(dados: dict, nivel: int = 0) -> str:
    """YAML suficiente para o front-matter que este módulo produz.

    Escrito à mão porque `pyyaml` exigiria `pip`, que o proxy bloqueia. Cobre
    só o que é gerado aqui: escalares, lista de escalares e lista de dicionários
    rasos. Não é um serializador geral e não deve virar um.
    """
    recuo = "  " * nivel
    linhas = []
    for chave, valor in dados.items():
        if isinstance(valor, bool):
            linhas.append(f"{recuo}{chave}: {'true' if valor else 'false'}")
        elif isinstance(valor, (int, float)):
            linhas.append(f"{recuo}{chave}: {valor}")
        elif isinstance(valor, list):
            if not valor:
                linhas.append(f"{recuo}{chave}: []")
                continue
            linhas.append(f"{recuo}{chave}:")
            for item in valor:
                if isinstance(item, dict):
                    interno = _yaml(item, nivel + 2).splitlines()
                    linhas.append(f"{recuo}  - {interno[0].strip()}")
                    linhas.extend(f"{recuo}    {l.strip()}" for l in interno[1:])
                else:
                    linhas.append(f"{recuo}  - {_escalar(item)}")
        else:
            linhas.append(f"{recuo}{chave}: {_escalar(valor)}")
    return "\n".join(linhas) + "\n"


def _escalar(valor) -> str:
    texto = str(valor)
    if texto == "":
        return '""'
    # aspas quando o valor poderia ser lido como outra coisa que não string
    if re.search(r'^[\s>|&*!%@`\[\]{}#-]|[:#]\s|["\']|^(true|false|null|~)$', texto):
        return '"' + texto.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return texto


# --------------------------------------------------------------------------
# material a partir do que já está em disco
# --------------------------------------------------------------------------


CABECALHO_VIDEO = re.compile(r"^- Vídeo:\s*https://youtu\.be/([\w-]+)", re.MULTILINE)
CABECALHO_TITULO = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def material_de_pasta(pasta: Path, *, titulo: str = "", fonte: str = "",
                      fonte_tipo: str = "links", interno: bool = True,
                      intervalo_quadros: int = 10) -> Material:
    """Monta o `Material` a partir de `transcricoes/<artigo>/`.

    Lê o formato que o `transcrever.py` já grava — `# título`, a linha
    `- Vídeo: https://youtu.be/<id>`, e o corpo depois do `---` — mais os
    quadros em `quadros/<video_id>/quadro_NNN.jpg`.
    """
    pasta = Path(pasta)
    if not pasta.is_dir():
        raise RedigirErro(f"pasta não encontrada: {pasta}")

    transcricoes = []
    for arquivo in sorted(pasta.glob("*.md")):
        bruto = arquivo.read_text(encoding="utf-8")
        achado = CABECALHO_VIDEO.search(bruto)
        video_id = achado.group(1) if achado else arquivo.stem
        # o título de verdade vem do cabeçalho `# título`, não do nome do
        # arquivo — o nome é cortado em 80 caracteres (ver limpar.converter),
        # o cabeçalho não.
        achado_titulo = CABECALHO_TITULO.search(bruto)
        titulo_video = achado_titulo.group(1).strip() if achado_titulo else arquivo.stem
        _, _, corpo = bruto.partition("\n---\n")
        transcricoes.append(Transcricao(
            video_id=video_id,
            titulo=titulo_video,
            texto=(corpo or bruto).strip(),
        ))

    quadros_achados = []
    raiz = pasta / "quadros"
    pastas_de_video = sorted(p for p in raiz.glob("*") if p.is_dir()) if raiz.is_dir() else []
    for pasta_video in pastas_de_video:
        arquivos = sorted(pasta_video.glob("quadro_*.jpg"))
        for indice, arquivo in enumerate(arquivos):
            segundos = indice * intervalo_quadros
            quadros_achados.append(Quadro(
                video_id=pasta_video.name,
                instante=f"{segundos // 60:02d}:{segundos % 60:02d}",
                caminho=arquivo,
            ))
        # vídeo que só tem quadro (mudo) não gerou .md; entra como transcrição
        # vazia para não sumir do agrupamento
        if arquivos and not any(t.video_id == pasta_video.name for t in transcricoes):
            transcricoes.append(Transcricao(
                video_id=pasta_video.name,
                titulo=pasta_video.name,
                texto="",
                leitura="quadros",
            ))
        elif arquivos:
            for t in transcricoes:
                if t.video_id == pasta_video.name and not t.texto:
                    t.leitura = "quadros"

    return Material(
        titulo=titulo or pasta.name,
        fonte=fonte,
        fonte_tipo=fonte_tipo,
        interno=interno,
        transcricoes=transcricoes,
        quadros=quadros_achados,
        imagens=[Imagem(caminho=p)
                 for p in sorted((pasta / "imagens").glob("*")) if p.is_file()],
    )


# --------------------------------------------------------------------------
# linha de comando
# --------------------------------------------------------------------------


def _seguro(nome: str) -> str:
    """Nome de pasta/arquivo válido no Windows.

    Cortado em 80 caracteres: título de vídeo real não tem limite de
    tamanho, e sem cortar o caminho completo (pasta + arquivo, dentro de
    onde quer que o projeto esteja) pode passar dos 260 caracteres que o
    Windows aceita sem suporte a caminho longo — reproduzido em 2026-08-17
    com um título de 42 caracteres numa pasta clonada mais funda que o
    normal.
    """
    nome = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", nome)
    nome = nome.strip(" .") or "sem-titulo"
    return nome[:80].rstrip(" .") or "sem-titulo"


def main() -> None:
    # O console do Windows abre em cp1252 e o que é impresso aqui vem do modelo.
    # Um único caractere fora dessa tabela derruba o comando no fim do trabalho,
    # depois de já ter gasto todas as chamadas. Reconfigurar custa nada.
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Transforma uma pasta de transcrições em documentação."
    )
    parser.add_argument("pasta", help="pasta de transcricoes/<artigo>")
    parser.add_argument("--saida", help="onde gravar (padrão: <pasta>/documentacao)")
    parser.add_argument("--titulo", default="", help="título do artigo de origem")
    parser.add_argument("--fonte", default="", help="URL de origem, para o front-matter")
    parser.add_argument("--fonte-tipo", default="links",
                        choices=["outline", "notion", "links", "texto"])
    parser.add_argument("--publico", action="store_true",
                        help="marca o material como NÃO interno (libera destino externo)")
    parser.add_argument("--intervalo-quadros", type=int, default=10,
                        help="o mesmo intervalo usado ao extrair os quadros")
    args = parser.parse_args()

    material = material_de_pasta(
        Path(args.pasta),
        titulo=args.titulo,
        fonte=args.fonte,
        fonte_tipo=args.fonte_tipo,
        interno=not args.publico,
        intervalo_quadros=args.intervalo_quadros,
    )

    com_quadros = len({q.video_id for q in material.quadros})
    print(f"{len(material.transcricoes)} vídeo(s), "
          f"{com_quadros} com quadros, {len(material.imagens)} imagem(ns)")

    try:
        artigos = redigir(material)
    except RedigirErro as erro:
        sys.exit(f"falhou: {erro}")

    destino = Path(args.saida or (Path(args.pasta) / "documentacao"))
    destino.mkdir(parents=True, exist_ok=True)

    print()
    for artigo in artigos:
        arquivo = destino / f"{_seguro(artigo.titulo)}.md"
        arquivo.write_text(artigo.markdown(), encoding="utf-8")
        marca = "BLOQUEADO" if artigo.bloqueado else f"{len(artigo.pendencias)} pendência(s)"
        print(f"  {arquivo.name}  [{marca}]")

    bloqueados = [a for a in artigos if a.bloqueado]
    if bloqueados:
        print("\n  ATENÇÃO: possível credencial na tela. Confira antes de "
              "publicar — o valor não foi copiado para nenhum arquivo.")
        for artigo in bloqueados:
            for p in artigo.pendencias:
                if p.bloqueia:
                    print(f"    {p.referencia}: {p.texto}")

    print(f"\nsaída: {destino.resolve()}")


if __name__ == "__main__":
    main()
