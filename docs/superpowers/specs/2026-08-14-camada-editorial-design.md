# Camada editorial — design

Data: 2026-08-14 · Sub-projeto #1 de quatro (ver "Decomposição", no fim).

## O problema

A ferramenta hoje entrega **insumo**, não documentação. Ela descobre os vídeos,
baixa a legenda, fatia em quadros o que não tem fala e baixa os prints do
artigo. O que sai disso é uma pasta de `.md` crus, um por vídeo — e transformar
isso em algo que alguém leia continua sendo trabalho humano conduzido à mão
numa conversa com a IA.

O gargalo mudou de lugar: não é mais assistir seis horas de vídeo, é destilar o
que saiu delas. Esta camada fecha esse gargalo.

## O que já existe e não deve ser refeito

| Módulo | Papel | Puro? |
| ------ | ----- | ----- |
| `descobrir.py` | acha vídeos em texto/página/Outline | sim |
| `limpar.py` | `.vtt` → Markdown | sim |
| `imagens.py` | baixa as imagens de um artigo do Outline | não |
| `quadros.py` | extrai quadros via `ffmpeg` | não |
| `transcrever.py` | proxy, download, orquestração da CLI | não |
| `mcp_server.py` | as ferramentas acima como MCP | não |

A restrição de **zero dependências de `pip`** continua valendo e não é
negociável aqui — ver `CLAUDE.md`. Nada neste desenho introduz biblioteca
externa.

## Decisões

### 1. Quem redige é o `claude` já instalado, chamado por subprocess

Verificado em 2026-08-14: `claude 2.1.232`, com `-p/--print`,
`--output-format json` e `--append-system-prompt`. É o mesmo padrão de contorno
que o projeto já usa para o proxy (`powershell Invoke-WebRequest`): a máquina
tem uma ferramenta que resolve, e a gente chama ela.

**O prompt vai por `stdin`, nunca por argumento.** Um artigo rendeu 23.420
palavras; a linha de comando do Windows corta em ~32 mil caracteres e o erro
resultante não diz que foi truncamento. Quem "simplificar" isso para `-p "$texto"`
quebra em silêncio nos artigos grandes, que são justamente os que importam.

Consequência de licença, registrada aqui para não se perder: isso funciona para
**uso individual, na máquina de quem gera**. Um servidor atendendo várias
pessoas com essa credencial é compartilhamento de conta — a versão em rede
exige chave de API da empresa. Ver "Fora de escopo".

### 2. Duas passagens, não uma chamada gigante

1. **Agrupar** — uma chamada curta recebe só os títulos e as primeiras linhas de
   cada transcrição e devolve os assuntos. Dezenove vídeos viram, digamos, quatro
   assuntos.
2. **Redigir** — uma chamada por assunto, com as transcrições e os quadros
   daquele grupo.

Isso existe por dois motivos: cabe no contexto, e cumpre a regra de consolidar
**por assunto, não por vídeo** — é o que impede o número de arquivos de crescer
junto com o número de vídeos.

### 3. Um documento serve os dois públicos

A pergunta "artigo para humano ou material para IA?" tinha uma premissa errada:
um procedimento bem escrito já é boa comida de IA. O que difere não é o corpo, é
o que vai em volta.

**Front-matter YAML** — o que a IA usa para filtrar e citar, e o humano nunca vê:

```yaml
---
titulo: Implementar uma API REST no ERP
fonte: https://outline.interno/doc/implementar-uma-api-7fK2qP
fonte_tipo: outline          # outline | notion | links | texto
interno: true                # trava destinos externos — ver Segurança
videos:
  - id: p3v0EAaR2SU
    titulo: Visão geral do template OpenAPI
    duracao: "12:04"
    leitura: legenda         # legenda | quadros
gerado_em: 2026-08-14
revisado_por: leonardo.anders
revisado_em: 2026-08-14
---
```

**Três regras no corpo**, que servem os dois públicos ao mesmo tempo:

- **Cada `##` é uma unidade de assunto fechada.** Dá recorte natural de chunk
  sem tokenizer, e deixa a página navegável por quem lê.
- **Nome exato sempre, pronome nunca.** "na aba `Serviço` do Cadastro de
  Usuário", não "na aba mencionada acima". Referência que depende do parágrafo
  anterior quebra o chunk e confunde quem chegou pelo Ctrl+F.
- **Timestamp na legenda da imagem** (`00:04:18`). O humano volta ao vídeo; a IA
  cita a origem.

Fica de fora: saudação, "como falei no vídeo anterior", passo dito e refeito,
ruído de fala.

### 4. Publicar já é indexar

Não construir RAG neste sub-projeto. O Outline publicado é buscável pelo MCP que
já está conectado — a IA lê de lá. Indexação semântica própria só entra se a
busca do Outline se mostrar insuficiente **no uso**, não por projeção.

### 5. Entrada e destino são assimétricos

Errado tratar como duas listas paralelas.

**Entrada — duas formas, e esta lista não cresce:**

- `ler_links(texto) -> list[Video]` — YouTube, playlist, arquivo de URLs, HTML
  salvo, Ctrl+C de intranet. Sem conexão.
- `ler_artigo(url) -> Material` — artigo autenticado (Outline hoje; Notion tem a
  mesma forma). Existe porque compra três coisas que o link solto não dá: os N
  links de uma vez na ordem, os anexos atrás de token, e o **texto escrito do
  artigo** — que é o único jeito de detectar que o vídeo ensina Swagger enquanto
  a página diz que Swagger não é mais necessário.

**Destino — esta é a lista que cresce.** Cada um recebe o mesmo `Artigo` e
converte para o que a plataforma aceita: Outline (Markdown), Obsidian (arquivo
no disco), Notion (blocos da API), Redmine (Textile), GitBook, WordPress (HTML +
upload de mídia à parte).

### 6. O portão humano é obrigatório e fica antes da publicação

Não é cerimônia. Dois casos reais deste conteúdo justificam:

- um artigo cujo texto diz *"não é mais necessário o uso do Swagger"* enquanto a
  lista de vídeos logo abaixo ainda oferece *"Apresentação do Swagger Editor"* —
  um resumo ingênuo publicado ensina o time errado;
- dois tokens de API reais legíveis em print de tela.

O que sai da máquina é **proposta**, com as pendências ao lado.

## Contratos

Três módulos novos. `descobrir.py` e `limpar.py` continuam puros e não são
tocados.

### O material de entrada

`ler_links` e `ler_artigo` **não vão para `descobrir.py`** — ele é puro e não
pode tocar a rede. `ler_links` já existe lá na forma pura (recebe texto,
devolve IDs); o que falta é só a busca autenticada, que fica em
`transcrever.py`, ao lado das outras funções que já falam com o Outline.

```python
@dataclass
class Material:
    fonte: str                  # URL do artigo, ou "" para links soltos
    fonte_tipo: str             # outline | notion | links | texto
    interno: bool
    titulo: str
    texto_artigo: str           # o que a página escrita afirma; "" se não houver
    transcricoes: list[Transcricao]   # video_id, titulo, duracao, texto
    quadros: list[Quadro]             # video_id, instante, caminho
    imagens: list[Imagem]             # caminho, legenda no artigo
```

O campo `texto_artigo` é o que torna a revisão inteligente: sem ele não há como
detectar conflito entre o que o vídeo ensina e o que a página escrita afirma.
Quando a entrada é link solto, ele vem vazio e essa classe de pendência
simplesmente não é gerada.

### `redigir.py` — não puro (chama subprocess)

```python
@dataclass
class Pendencia:
    tipo: str          # credencial | conflito | jargao | idade
    texto: str
    bloqueia: bool     # credencial bloqueia; as outras não
    referencia: str    # "p3v0EAaR2SU@00:07:41" ou o trecho do artigo

@dataclass
class Artigo:
    front_matter: dict
    corpo: str                  # Markdown, sem o front-matter
    pendencias: list[Pendencia]

def redigir(material: Material, *, intervalo_quadros: int = 10) -> list[Artigo]
```

Devolve **uma lista** — um `Artigo` por assunto, não por vídeo.

### `publicar.py` — não puro

```python
class Destino(Protocol):
    nome: str
    externo: bool                       # True bloqueia material interno
    def publicar(self, artigo: Artigo, *, rascunho: bool = True) -> str: ...
```

O retorno é a URL ou o caminho do que foi criado. Primeiro PR entrega
`DestinoOutline` e `DestinoObsidian` — o segundo é escrita de arquivo numa pasta,
custo quase zero, e valida a abstração contra algo genuinamente diferente de uma
API REST.

### `console.py` — não puro

`http.server` da biblioteca padrão, ouvindo em `127.0.0.1`, sem autenticação,
processo único, um usuário. A separação HTTP ↔ pipeline é feita desde o começo:
o console não conhece regra de negócio, só chama `descobrir`, `redigir` e
`publicar`. É o que permite trocar hospedagem depois sem reescrever o motor.

Estado em disco, em `transcricoes/<artigo>/artigo.json` — que já está no
`.gitignore`.

## Segurança

Ver `.claude/rules/seguranca.md`, que é obrigatório. Três travas concretas neste
desenho:

1. **Pendência de credencial bloqueia a publicação.** `bloqueia=True` desabilita
   o botão até resolução explícita. O valor suspeito nunca é copiado para o
   `Artigo`, nem para log, nem para a resposta — só a referência (vídeo e
   instante).
2. **`interno: true` no front-matter proíbe destino com `externo=True`.** Material
   de origem interna não chega ao WordPress nem ao GitBook, e a checagem é no
   `publicar`, não na interface — interface se contorna.
3. **Nada de conteúdo extraído no git.** A verificação com `git status --short`
   antes de cada commit continua sendo a checagem mais importante do repositório.

## Fora de escopo (deste sub-projeto)

- **Interface em rede, multiusuário, autenticada.** É o sub-projeto #4 e muda a
  conta de custo — exige chave de API da empresa.
- **RAG próprio / indexação semântica.** Ver decisão 4.
- **Destinos além de Outline e Obsidian.** Notion, Redmine, GitBook e WordPress
  entram no #2, depois que a abstração tiver dois casos reais em pé.
- **Transcrever áudio.** Continua barrado: exigiria `pip` e resolve pouco.
- **Serviço externo de análise de vídeo/imagem.** Continua barrado por
  vazamento.

## Verificação

Não há suíte automatizada neste repositório e isso não muda aqui — a
verificação é manual e está em `.claude/rules/estilo-codigo.md`. Antes de cada
PR:

```bash
python -c "import descobrir; print(len(descobrir.ids_em_texto('https://youtu.be/p3v0EAaR2SU')))"
python transcrever.py u2k8KF3d4-E --saida transcricoes/teste
python transcrever.py u2k8KF3d4-E --idioma zz --sem-fallback --quadros \
    --saida transcricoes/teste-quadros --intervalo-quadros 10
Get-Content teste.jsonl | python mcp_server.py
git status --short
```

Mexeu no `mcp_server.py`: `claude mcp list` e confirmar `Connected`.

## Decomposição e sequência

| # | Sub-projeto | Estado |
| - | ----------- | ------ |
| 1 | Camada editorial + publicação + console local | **este documento** |
| 2 | Destinos adicionais (Notion, Redmine, GitBook, WordPress) | depois |
| 3 | Trava de origem × destino, generalizada | dentro do #1, decisão 5 e Segurança |
| 4 | Interface em rede para o time | outro projeto |

PRs do #1, um assunto cada, conforme `.claude/rules/commits.md`:

1. `docs/spec-camada-editorial` — este documento
2. `feat/redigir` — `redigir.py`
3. `feat/publicar` — `publicar.py` com Outline e Obsidian
4. `feat/console` — `console.py`

## Protótipo visual

A proposta de interface foi desenhada como página de demonstração antes deste
documento, e é o que acompanha a apresentação da ideia. Não é código do produto:
nada está conectado e todos os dados são inventados, justamente porque conteúdo
interno não circula em página compartilhável.
