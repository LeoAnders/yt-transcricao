# yt-transcricao

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Windows](https://img.shields.io/badge/Windows-0078D6?logo=windows&logoColor=white)
![Dependências](https://img.shields.io/badge/depend%C3%AAncias-zero-2ea44f)
![MCP](https://img.shields.io/badge/MCP-servidor%20stdio-000000)
![Licença](https://img.shields.io/badge/licen%C3%A7a-privada-lightgrey)

Transforma vídeos **e imagens** de documentação em texto que uma IA consegue
ler — pela legenda automática do YouTube, lendo a tela quando não há fala, e
baixando os prints que o texto não descreve.

Funciona como ferramenta de linha de comando **e** como servidor MCP, para
uma IA usar direto na conversa.

## Por que existe

Documentação interna costuma ter vídeos. Um vídeo é ótimo para uma pessoa e
inútil para uma IA: o modelo não assiste. Se você quer que os vídeos façam
parte de uma base de conhecimento — uma skill, um RAG, um agente —, alguém
precisa transformá-los em texto uma vez.

Fazer isso na mão significa assistir tudo e digitar. Trinta e cinco vídeos de
dez minutos são quase seis horas.

Esta ferramenta faz o mesmo em poucos minutos, sem abrir vídeo nenhum.

## Requisitos

- Python 3.10+
- Windows (a detecção de proxy e o download do `yt-dlp` usam recursos do SO)
- `ffmpeg` no PATH — **só** para `quadros.py` (`winget install Gyan.FFmpeg`)

**Nenhuma dependência de `pip`.** Isso é decisão de projeto, não preguiça:
em rede corporativa com proxy autenticado, `pip install` falha com `407` — o
pip não faz autenticação integrada do Windows. Zero dependência é o que torna
a ferramenta instalável nesse ambiente. O `yt-dlp.exe` é baixado sozinho na
primeira execução e fica fora do repositório.

## Uso — linha de comando

```bash
# vídeos soltos (URL normal, curta, Shorts, embed, ou só o ID)
python transcrever.py https://youtu.be/p3v0EAaR2SU

# arquivo com uma URL por linha
python transcrever.py --lista links.txt

# qualquer texto: HTML salvo, Markdown, ou o Ctrl+C de uma página
python transcrever.py --texto pagina-copiada.txt

# uma página HTML pública ou de intranet
python transcrever.py --pagina https://exemplo.com/documentacao

# um artigo do Outline (cria a subpasta com o nome do artigo)
python transcrever.py --outline https://outline.suaempresa.com/doc/artigo-XXXX
```

Sai um `.md` por vídeo em `transcricoes/`:

```markdown
# Introdução à API

- Vídeo: https://youtu.be/p3v0EAaR2SU
- Origem: legenda automática do YouTube, não revisada

---

(00:01) Então nesse vídeo a gente vai falar sobre api uma pequena introdução...
```

### Fontes de links

| Modo | Serve para | Auth |
| --- | --- | --- |
| URLs / `--lista` | você já tem os links | — |
| `--texto ARQUIVO` | **qualquer coisa** que você consiga selecionar e colar | — |
| `--pagina URL` | página HTML pública ou de intranet sem login | — |
| `--outline URL` | artigo do Outline | token |

O `--texto` é o coringa. Documentação atrás de login — SharePoint, Confluence
privado, Notion, Google Drive restrito — nunca abre por URL sem integração
dedicada para cada plataforma. Mas sempre dá para selecionar a página e colar
num arquivo. É feio e cobre 100% dos casos.

A extração reconhece todas as formas de link do YouTube: `youtu.be`,
`watch?v=`, `/embed/`, `/shorts/`, `/live/`, `/v/` e `youtube-nocookie.com`.
O `/embed/` importa mais do que parece — documentação costuma **embutir** o
player em vez de linkar.

### Opções

| Opção | Para quê |
| --- | --- |
| `--saida PASTA` | muda o destino (padrão: `transcricoes`) |
| `--idioma pt` | idioma da legenda (padrão: `pt`) |
| `--sem-timestamps` | texto corrido, melhor para resumir |
| `--sem-fallback` | não tenta outro idioma quando o pedido não existe |
| `--sem-proxy` | ignora o proxy configurado no Windows |

## Vídeo sem fala

Captura de tela, demonstração muda, gravação sem narração: o YouTube não
gera legenda porque não há o que transcrever. Mas a informação está escrita
na tela.

```bash
python quadros.py video.mp4 --intervalo 4
```

Corta o vídeo em imagens (com upscale, porque gravação de tela costuma vir
pequena e o texto de terminal fica ilegível) e lista o instante de cada uma.
**Quem lê as imagens é a IA** — não há OCR nem modelo de vídeo envolvido.

A alternativa seria mandar o vídeo para um serviço de compreensão de vídeo
hospedado. Local é melhor aqui por três motivos concretos:

- o `ffmpeg` já está instalado e não custa nada;
- vídeo interno costuma ter dado sensível na tela — a gravação que motivou
  este módulo exibe um nome de usuário num prompt de autenticação, e subir
  isso para terceiro seria vazamento;
- para texto em terminal, ler o quadro é **melhor** que descrever a cena: um
  modelo de vídeo diria "um terminal com texto branco", enquanto ler o quadro
  entrega o comando digitado e a resposta que apareceu.

## Imagens da documentação

```bash
python imagens.py https://outline.suaempresa.com/doc/artigo-XXXX
```

Baixa os prints de tela do artigo em `imagens/<artigo>/`, cada um acompanhado
do texto que o antecede no documento — sem esse contexto, uma pasta de PNGs
não diz nada. Anexo que não é imagem (vídeo, PDF) é descartado.

Documentação técnica coloca na figura justamente o que o texto não descreve.
Casos reais encontrados neste acervo:

- o texto diz "libere os endpoints no cadastro de usuário" e **não diz a
  aba** — a imagem mostra que é a aba `Serviço`, não a `Segurança`;
- o texto manda escrever `"deprecated" = true`, que é **JSON inválido** — a
  imagem mostra o correto, `"deprecated": true`.

No segundo caso a figura **contradiz** o texto. Uma base de conhecimento
montada só com o Markdown herda o erro.

> ⚠️ Print de tela vaza credencial. A primeira varredura aqui encontrou dois
> tokens de API reais num único artigo. `imagens/`, `quadros/` e
> `transcricoes/` estão no `.gitignore` — não remover.

## Uso — servidor MCP

Registrar no Claude Code:

```bash
claude mcp add yt-transcricao --scope user -- python C:/github-repositories/LeoAnders/yt-transcricao/mcp_server.py
```

No Claude Desktop, em `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "yt-transcricao": {
      "command": "python",
      "args": ["C:/github-repositories/LeoAnders/yt-transcricao/mcp_server.py"]
    }
  }
}
```

Ferramentas expostas:

| Ferramenta | O que faz |
| --- | --- |
| `obter_transcricao` | um vídeo → o texto |
| `extrair_videos` | texto ou URL de página → lista de vídeos, sem transcrever |
| `listar_videos_do_artigo` | artigo do Outline → lista com o rótulo da documentação |
| `transcrever_artigo` | artigo do Outline → grava em disco, devolve o índice |
| `extrair_quadros` | vídeo local sem fala → imagens para a IA ler |

**`transcrever_artigo` não devolve o texto de propósito.** Um único artigo
rendeu 23.420 palavras aqui; despejar isso numa resposta estouraria o
contexto e derrubaria a conversa. Ele grava os arquivos e devolve o índice
com a contagem de palavras — a IA lê depois só o que interessa. `listar_…`
existe para poder escolher antes de gastar qualquer coisa.

## Outline

O `--outline` e as duas ferramentas de artigo precisam de um token. Copie o
`.env.example` para `.env`:

```
OUTLINE_API_TOKEN=seu_token_aqui
```

O token sai em **Outline → Settings → API Tokens**. O `.env` está no
`.gitignore`.

## Estrutura

| Arquivo | Responsabilidade |
| --- | --- |
| `descobrir.py` | acha vídeos em texto/página/Outline — extração **pura** |
| `limpar.py` | converte `.vtt` em Markdown — **puro**, não conhece rede |
| `imagens.py` | baixa os prints de tela de um artigo do Outline |
| `quadros.py` | extrai quadros via ffmpeg |
| `transcrever.py` | linha de comando, proxy, download |
| `mcp_server.py` | servidor MCP sobre os módulos acima |

Convenções do projeto em [CLAUDE.md](CLAUDE.md) e `.claude/rules/` — vale ler
`seguranca.md` antes de mexer no que a ferramenta extrai.

`descobrir.py` e `limpar.py` são testáveis sem internet: dê um texto, cobre
os links; dê um `.vtt`, cobre o Markdown.

## Como funciona

1. **Descoberta** — links vêm da linha de comando, de um arquivo, de uma
   página HTML ou da API do Outline (`documents.info`).

2. **Download** — o `yt-dlp` baixa a legenda automática em `.vtt`.

   O detalhe que faz a coisa existir: uma requisição comum ao endpoint
   `/api/timedtext` do YouTube recebe `200` **com corpo vazio**, porque o
   YouTube passou a exigir um token de origem de navegador real. O `yt-dlp`
   contorna isso pedindo os dados ao player *android vr*, que não é
   submetido a essa checagem. Sem esse desvio, não há legenda fora do
   navegador — nem com `fetch`, nem com `curl`.

3. **Limpeza** (`limpar.py`) — a legenda automática vem em modo "rolante":
   cada bloco repete a linha anterior e traz uma tag `<c>` por palavra. Lido
   cru, o texto sai com cerca de três vezes o tamanho real. O script remove
   as tags, descarta as repetições e reagrupa em parágrafos de 30 segundos.

O proxy é detectado pelas variáveis `HTTP(S)_PROXY` ou pelas configurações de
Internet do Windows — nada de IP no código.

## Limitações conhecidas

- **A qualidade é de reconhecimento automático de fala.** Jargão técnico sai
  torto: "Swagger" vira "swager" ou "suegra", "API" vira "a pi". Um LLM
  costuma reconstruir o termo pelo contexto, mas não serve para publicar como
  está.

- **Sem pontuação.** A legenda do YouTube não pontua.

- **Vídeo sem fala não gera legenda.** Os que falharem são listados no fim da
  execução; para esses, use `quadros.py`.

- **O vídeo pode estar desatualizado em relação à documentação escrita.** Um
  vídeo de 2024 ensina um procedimento que a página já substituiu, e a
  transcrição não sabe disso. Caso real encontrado: uma página diz "não é
  mais necessário o uso do Swagger" e a lista de vídeos logo abaixo ainda
  oferece "Apresentação do Swagger Editor". Revise antes de usar como fonte
  de verdade.

- **O rótulo do link na documentação costuma divergir do título real no
  YouTube.** Os arquivos usam o título do YouTube; para cruzar com a
  documentação, use o link, que é a única chave confiável.
