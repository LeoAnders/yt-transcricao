# yt-transcricao

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Windows](https://img.shields.io/badge/Windows-0078D6?logo=windows&logoColor=white)
![Dependências](https://img.shields.io/badge/depend%C3%AAncias-zero-2ea44f)
![MCP](https://img.shields.io/badge/MCP-servidor%20stdio-000000)
![Licença](https://img.shields.io/badge/licen%C3%A7a-privada-lightgrey)

Transforma vídeos **e imagens** de documentação em texto que uma IA consegue
ler — pela legenda automática do YouTube, lendo a tela quando a fala não
basta, e baixando os prints que o texto não descreve.

Usa-se por **servidor MCP**: a IA chama as ferramentas direto na conversa.
Há também uma linha de comando, documentada no fim.

## Por que existe

Documentação interna costuma ter vídeos e prints. Isso é ótimo para uma
pessoa e inútil para uma IA: o modelo não assiste vídeo, e uma imagem no
Markdown é só `![](/api/attachments.redirect?id=...)` — ou seja, nada.

Se você quer esse material dentro de uma base de conhecimento — uma skill, um
RAG, um agente —, alguém precisa convertê-lo uma vez. Na mão, trinta e cinco
vídeos de dez minutos são quase seis horas de trabalho.

## Instalação

Requisitos:

| Requisito | Para quê |
| --- | --- |
| Python 3.10+ | tudo |
| Windows | detecção de proxy e downloads autenticados usam recursos do SO |
| `ffmpeg` no PATH | só para extrair quadros (`winget install Gyan.FFmpeg`) |

**Nenhuma dependência de `pip`.** É decisão de projeto, não preguiça: em rede
corporativa com proxy autenticado, `pip install` falha com `407`, porque o pip
não faz autenticação integrada do Windows. Zero dependência é o que torna a
ferramenta instalável nesse ambiente. O `yt-dlp.exe` é baixado sozinho na
primeira execução e fica fora do repositório.

Registrar o servidor no Claude Code:

```bash
claude mcp add yt-transcricao --scope user -- python C:/caminho/para/mcp_server.py
```

Conferir:

```bash
claude mcp list        # deve aparecer "Connected"
```

No Claude Desktop, em `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "yt-transcricao": {
      "command": "python",
      "args": ["C:/caminho/para/mcp_server.py"]
    }
  }
}
```

As ferramentas de artigo precisam de um token do Outline — veja
[Outline](#outline), no fim.

## Ferramentas

| Ferramenta | O que faz |
| --- | --- |
| `extrair_videos` | acha vídeos num texto ou numa página, sem transcrever |
| `listar_videos_do_artigo` | lista os vídeos de um artigo com o rótulo da documentação |
| `obter_transcricao` | um vídeo → o texto, na resposta |
| `transcrever_artigo` | artigo inteiro → grava em disco, devolve o índice |
| `quadros_do_video` | um vídeo → imagens da tela (baixa sozinho) |
| `imagens_do_artigo` | os prints do artigo, cada um com seu contexto |
| `extrair_quadros` | idem, a partir de um arquivo de vídeo local |

### O fluxo normal

Perguntar antes de gastar, processar depois:

```
listar_videos_do_artigo   → o que existe ali
transcrever_artigo        → converte e grava
(ler no disco só o arquivo que interessa)
```

`transcrever_artigo` **não devolve o texto de propósito**. Um único artigo
pode passar de vinte mil palavras; despejar isso numa resposta estoura o
contexto e derruba a conversa. Ele devolve o índice:

```
artigo "Nome do Artigo": 3 de 4 vídeo(s) transcritos, 5.529 palavras.

pasta: transcricoes/Nome do Artigo

-  3.877 palavras  Segundo vídeo.md
-  1.240 palavras  Primeiro vídeo.md
-    412 palavras  Terceiro vídeo.md

sem legenda (1):
- https://www.youtube.com/watch?v=XXXXXXXXXXX
```

### Texto e tela são complementares

A tentação é tratar quadros como plano B para vídeo mudo. Não é: em vídeo de
tela, **a fala diz o porquê e a tela diz o literal**.

A legenda automática erra jargão — um cabeçalho como `x-cache-ttl` pode sair
transcrito como "X Cash TTL" e, dez segundos depois, como "x Cache Title". O
quadro do mesmo instante mostra o nome escrito na tela, exato. Quem reconstrói
o termo é quem lê os dois.

Por isso `transcrever_artigo` aceita `quadros`:

| Valor | Efeito |
| --- | --- |
| `"nao"` | só transcrição |
| `"sem-legenda"` | padrão — quadros só dos vídeos que não têm legenda |
| `"todos"` | transcreve **e** corta todos; mais lento, mas é o que captura a tela dos vídeos narrados |

E `quadros_do_video` existe para pedir um vídeo específico sem processar o
artigo inteiro.

As ferramentas de imagem devolvem **caminhos de arquivo**, não conteúdo —
mesma razão do índice. Quem lê as imagens é a IA, depois, e só as que
interessam. Não há OCR nem modelo de vídeo envolvido.

### Imagens do artigo

`imagens_do_artigo` baixa cada print junto do texto que o antecede no
documento. Sem esse contexto, uma pasta de PNGs não diz nada.

Documentação técnica coloca na figura justamente o que o texto não descreve —
qual aba, qual campo, o valor exato. E às vezes a figura **contradiz** o
texto: o texto traz um exemplo com erro de sintaxe e a imagem mostra a forma
correta. Uma base de conhecimento montada só com o Markdown herda o erro.

> ⚠️ Print de tela vaza credencial. `imagens/`, `quadros/` e `transcricoes/`
> estão no `.gitignore` — não remover. Ver `.claude/rules/seguranca.md`.

## Como funciona

1. **Descoberta** — links vêm de um texto, de uma página HTML ou da API do
   Outline (`documents.info`).

2. **Legenda** — o `yt-dlp` baixa a legenda automática em `.vtt`.

   O detalhe que faz a coisa existir: uma requisição comum ao endpoint
   `/api/timedtext` do YouTube recebe `200` **com corpo vazio**, porque o
   YouTube passou a exigir um token de origem de navegador real. O `yt-dlp`
   contorna pedindo os dados ao player *android vr*. Sem esse desvio não há
   legenda fora do navegador — nem com `fetch`, nem com `curl`.

3. **Limpeza** — a legenda vem em modo "rolante": cada bloco repete a linha
   anterior e traz uma tag `<c>` por palavra. Lido cru, o texto sai com cerca
   de três vezes o tamanho real. O script remove as tags, descarta as
   repetições e reagrupa em parágrafos de 30 segundos.

4. **Vídeo** — os *metadados* passam pelo proxy sem credencial, mas os *bytes*
   do `googlevideo` recebem `407`. A transferência é feita em pedaços pelo
   `Invoke-WebRequest -ProxyUseDefaultCredentials`, o único cliente da máquina
   que autentica sozinho, com os headers que o `yt-dlp` usou — sem eles a
   resposta é `403`, porque a URL é assinada para o cliente que a pediu.

5. **Quadros** — o `ffmpeg` corta um quadro a cada N segundos, com upscale:
   gravação de tela costuma vir pequena e o texto de terminal fica ilegível no
   tamanho original.

O proxy é detectado pelas variáveis `HTTP(S)_PROXY` ou pelas configurações de
Internet do Windows — nada de IP no código.

## Limitações conhecidas

- **A qualidade é de reconhecimento automático de fala.** Jargão técnico sai
  torto e não há pontuação. Um LLM reconstrói o termo pelo contexto, mas não
  serve para publicar como está.

- **Vídeo sem fala não gera legenda.** Para esses, quadros são o único
  caminho.

- **Só o YouTube tem transcrição.** Legenda automática é serviço do YouTube,
  não propriedade do vídeo. Outras plataformas podem render quadros, mas não
  texto — reconhecimento de fala exigiria `pip`, que é o `407` de novo.

- **O `googlevideo` estrangula por IP.** Downloads em sequência passam a
  receber `403`. A ferramenta espera e repete sozinha, de forma escalonada,
  mas um artigo com muitos vídeos leva tempo por causa disso.

- **O vídeo pode estar desatualizado em relação ao texto.** Um vídeo antigo
  ensina um procedimento que a página já substituiu, e a transcrição não sabe
  disso. Revise antes de usar como fonte de verdade.

- **O rótulo do link costuma divergir do título real no YouTube.** Os arquivos
  usam o título do YouTube; para cruzar com a documentação, use o link, que é
  a única chave confiável.

## Outline

As ferramentas de artigo precisam de um token, lido do ambiente **ou** de um
`.env` ao lado do script. São aceitos `OUTLINE_API_TOKEN` e `OUTLINE_API_KEY`
— se você já tem um deles no ambiente, não precisa criar `.env`.

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
| `transcrever.py` | proxy, download de legenda e de vídeo, orquestração |
| `mcp_server.py` | servidor MCP sobre os módulos acima |

`descobrir.py` e `limpar.py` são testáveis sem internet: dê um texto, cobre os
links; dê um `.vtt`, cobre o Markdown.

Convenções em [CLAUDE.md](CLAUDE.md) e `.claude/rules/` — vale ler
`seguranca.md` antes de mexer no que a ferramenta extrai.

## Linha de comando

O mesmo código, sem passar pelo MCP. Serve para diagnosticar quando o servidor
não responde e para uso avulso.

```bash
# vídeos soltos (URL normal, curta, Shorts, embed, ou só o ID)
python transcrever.py https://youtu.be/XXXXXXXXXXX

# arquivo com uma URL por linha
python transcrever.py --lista links.txt

# qualquer texto: HTML salvo, Markdown, ou o Ctrl+C de uma página
python transcrever.py --texto pagina-copiada.txt

# uma página HTML pública ou de intranet
python transcrever.py --pagina https://exemplo.com/documentacao

# um artigo do Outline, com quadros dos que não têm legenda
python transcrever.py --outline https://outline.exemplo.com/doc/artigo-XXXX --quadros

# imagens de um artigo
python imagens.py https://outline.exemplo.com/doc/artigo-XXXX

# quadros de um arquivo de vídeo local
python quadros.py video.mp4 --intervalo 4
```

Sai um `.md` por vídeo em `transcricoes/`:

```markdown
# Título do vídeo

- Vídeo: https://youtu.be/XXXXXXXXXXX
- Origem: legenda automática do YouTube, não revisada

---

(00:01) primeiro parágrafo da transcrição...
```

### Fontes de links

| Modo | Serve para | Auth |
| --- | --- | --- |
| URLs / `--lista` | você já tem os links | — |
| `--texto ARQUIVO` | **qualquer coisa** que você consiga selecionar e colar | — |
| `--pagina URL` | página HTML pública ou de intranet sem login | — |
| `--outline URL` | artigo do Outline | token |

O `--texto` é o coringa. Documentação atrás de login — SharePoint, Confluence
privado, Notion, Drive restrito — nunca abre por URL sem integração dedicada
para cada plataforma. Mas sempre dá para selecionar a página e colar num
arquivo. É feio e cobre 100% dos casos.

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
| `--quadros` | para os vídeos sem legenda, baixa e vira imagens |
| `--intervalo-quadros N` | segundos entre quadros (padrão: `4`) |
