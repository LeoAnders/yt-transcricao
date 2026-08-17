# yt-transcricao

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Windows](https://img.shields.io/badge/Windows-0078D6?logo=windows&logoColor=white)
![Dependências](https://img.shields.io/badge/depend%C3%AAncias-zero-2ea44f)
![MCP](https://img.shields.io/badge/MCP-servidor%20stdio-000000)
![Licença](https://img.shields.io/badge/licen%C3%A7a-privada-lightgrey)

Transforma vídeo do YouTube em texto e imagem que uma IA consegue ler — pela
legenda automática, e lendo a tela quando a fala não basta.

Usa-se por **servidor MCP** (a IA chama as ferramentas direto na conversa),
por **linha de comando**, ou por **API HTTP** (para uma interface própria —
ver [Vidraft](../vidraft), o primeiro consumidor). A entrada é sempre link de
vídeo do YouTube — **não lê artigo de documentação** (Outline, Notion etc.):
isso é redundante com o MCP da própria ferramenta de documentação, que já
resolve "achar o texto/os links" melhor do que este projeto reimplementaria.
Ver "Decisão de 2026-08-15" em [CLAUDE.md](CLAUDE.md).

## Por que existe

Documentação interna costuma ter vídeo. Isso é ótimo para uma pessoa e inútil
para uma IA: o modelo não assiste vídeo.

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

## Ferramentas

| Ferramenta | O que faz |
| --- | --- |
| `extrair_videos` | acha vídeos num texto ou numa página, sem transcrever |
| `obter_transcricao` | um vídeo → o texto, na resposta |
| `quadros_do_video` | um vídeo → imagens da tela (baixa sozinho) |
| `extrair_quadros` | idem, a partir de um arquivo de vídeo local |

### O fluxo normal

Perguntar antes de gastar, processar depois. Se o ponto de partida é um
artigo de documentação (Outline, Notion, uma página qualquer), busque o texto
pelo MCP da própria ferramenta de documentação e passe pra cá:

```
(MCP da documentação: pega o texto do artigo)
extrair_videos            → quais vídeos existem ali, sem transcrever
obter_transcricao         → um por um, o texto que interessa
quadros_do_video          → para os que não têm fala, ou onde a tela importa
```

Vídeo com muita fala pode passar de mil palavras; para vários de uma vez,
prefira gravar em disco em vez de devolver tudo na resposta — é o que o
`transcrever.py` (linha de comando) e o `/api/gerar` (API HTTP) já fazem.

### Texto e tela são complementares

A tentação é tratar quadros como plano B para vídeo mudo. Não é: em vídeo de
tela, **a fala diz o porquê e a tela diz o literal**.

A legenda automática erra jargão — um cabeçalho como `x-cache-ttl` pode sair
transcrito como "X Cash TTL" e, dez segundos depois, como "x Cache Title". O
quadro do mesmo instante mostra o nome escrito na tela, exato. Quem reconstrói
o termo é quem lê os dois.

Por isso `transcrever.py` (linha de comando) e `/api/gerar` (API HTTP)
aceitam `--quadros`: para os vídeos sem legenda, baixa e vira imagem. E
`quadros_do_video` existe, no MCP, para pedir um vídeo específico sem
processar um lote inteiro.

As ferramentas de imagem devolvem **caminhos de arquivo**, não conteúdo —
mesma razão do índice. Quem lê as imagens é a IA, depois, e só as que
interessam. Não há OCR nem modelo de vídeo envolvido.

> ⚠️ Quadro de vídeo vaza credencial (já aconteceu: token de API legível em
> tela gravada). `quadros/` e `transcricoes/` estão no `.gitignore` — não
> remover. Ver `.claude/rules/seguranca.md`.

## Como funciona

1. **Descoberta** — links vêm de um texto ou de uma página HTML. Artigo de
   documentação (Outline, Notion) não é lido por aqui — ver a nota no topo
   deste README.

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

## API HTTP

Para quem quer uma interface própria em vez de MCP ou linha de comando,
`console.py` expõe a mesma lógica por HTTP, sem autenticação — pensado para
rodar na mesma máquina de quem usa (ver `.claude/rules/seguranca.md`):

```bash
python console.py            # 127.0.0.1:8765
```

| Rota | O que faz |
| --- | --- |
| `POST /api/analisar` | encontra vídeo(s) no texto colado, sem baixar nada |
| `POST /api/gerar` | baixa, transcreve e redige em segundo plano; devolve o id do trabalho |
| `GET /api/trabalho?id=` | estado do trabalho e, quando pronto, os arquivos gerados |
| `GET /api/documento?arquivo=` | conteúdo de um documento gerado, com as pendências |
| `GET /api/midia?arquivo=` | serve um quadro/imagem referenciado no documento |

O primeiro consumidor é o [Vidraft](../vidraft), repositório irmão.

## Estrutura

| Arquivo | Responsabilidade |
| --- | --- |
| `descobrir.py` | acha vídeos em texto/página — extração **pura**, sem Outline |
| `limpar.py` | converte `.vtt` em Markdown — **puro**, não conhece rede |
| `quadros.py` | extrai quadros via ffmpeg |
| `transcrever.py` | proxy, download de legenda e de vídeo, orquestração |
| `redigir.py` | transcrição + quadros → documento, pelo `claude` da máquina |
| `console.py` | API HTTP sobre os módulos acima |
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

# um ou mais vídeos, com quadros dos que não têm legenda
python transcrever.py https://youtu.be/XXXX https://youtu.be/YYYY --quadros

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

| Modo | Serve para |
| --- | --- |
| URLs / `--lista` | você já tem os links |
| `--texto ARQUIVO` | **qualquer coisa** que você consiga selecionar e colar |
| `--pagina URL` | página HTML pública ou de intranet sem login |

O `--texto` é o coringa. Documentação atrás de login — SharePoint, Confluence
privado, Notion, Outline, Drive restrito — nunca abre por URL sem integração
dedicada para cada plataforma; use o MCP dessa plataforma para conseguir o
texto e cole num arquivo. É feio e cobre 100% dos casos.

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
