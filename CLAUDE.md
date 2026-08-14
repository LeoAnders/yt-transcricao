# yt-transcricao

Ferramenta que transforma vídeos e imagens de documentação em texto que uma
IA consegue ler. Funciona como linha de comando **e** como servidor MCP.

Nasceu de um problema concreto: a documentação interna da empresa tem ~35
vídeos no YouTube e dezenas de prints de tela. Uma IA não assiste vídeo nem
enxerga imagem linkada — então esse conteúdo simplesmente não existe para
uma skill ou um RAG montado sobre o texto.

## Idioma

Todo o projeto é em **pt-BR**: comentários, docstrings, mensagens de commit,
documentação e respostas da IA. Identificadores de código em inglês só quando
o termo técnico é natural (`fetch`, `chunk`); o resto em português
(`baixar_legendas`, `anexos_com_contexto`).

## Restrição que define a arquitetura

**Zero dependências de `pip`.** Não é purismo — é requisito de ambiente:

```
pip install <qualquer coisa>  →  407 Proxy Authentication Required
```

O proxy corporativo exige autenticação integrada do Windows, e nem o `pip`
nem o `npm` sabem fazê-la. Isso elimina de saída o SDK oficial do MCP, o
`requests`, o `faster-whisper` e qualquer biblioteca. Só a biblioteca padrão
do Python.

Consequências que **não devem ser revertidas** sem resolver o proxy primeiro:

- o servidor MCP fala JSON-RPC 2.0 na mão, sobre stdio;
- downloads que precisam de credencial de proxy são feitos via
  `powershell -Command Invoke-WebRequest -ProxyUseDefaultCredentials`, que é
  o único cliente na máquina que autentica sozinho;
- o `yt-dlp.exe` é baixado avulso do GitHub, não instalado por pacote;
- **a interface é React sem `npm` e sem empacotador.** As três bibliotecas
  (`react`, `react-dom`, `htm`) são builds UMD baixadas avulsas na primeira
  execução pelo `Invoke-WebRequest`, exatamente como o `yt-dlp.exe`, e ficam em
  `web/vendor/`, fora do versionamento. **Nada de CDN**: a página não pode
  depender de rede externa em runtime, porque trata conteúdo interno.

  O `htm` é o que dispensa o Babel — dá sintaxe praticamente igual a JSX por
  template literal, em 1,4 KB, interpretada pelo próprio navegador. Trocar por
  `babel-standalone` "para usar JSX de verdade" custaria ~2 MB e uma
  transpilação a cada carregamento; não fazer isso é decisão, não esquecimento.

  O `console.py` não decide nada — só chama `redigir` e `publicar` —, então
  trocar a interface de novo não toca no motor.

## Estrutura

```
descobrir.py     Acha vídeos em texto/página/Outline — extração PURA
limpar.py        Converte .vtt em Markdown — PURO, não conhece rede
imagens.py       Baixa as imagens de um artigo do Outline
quadros.py       Extrai quadros de vídeo via ffmpeg (para vídeo sem fala)
transcrever.py   Linha de comando: proxy, download, orquestração
redigir.py       Transcrição + quadros → documento, pelo `claude` da máquina
publicar.py      Destinos (Outline, Obsidian) e as travas de publicação
console.py       Console local de revisão — HTTP da stdlib em 127.0.0.1
web/             Interface em React: console.html, app.js, app.css
web/vendor/      react, react-dom e htm — baixados avulsos, não versionados
mcp_server.py    Servidor MCP sobre os módulos acima
```

`descobrir.py` e `limpar.py` são puros de propósito: dá um texto, cobra os
links; dá um `.vtt`, cobra o Markdown. Testáveis sem internet e sem
`yt-dlp`. Manter assim.

## Decisões de arquitetura (não mudar sem motivo forte)

- **Legenda automática, não reconhecimento de fala.** O YouTube já gerou o
  texto; rodar Whisper em cima seria pagar horas de CPU por qualidade que o
  LLM recupera sozinho pelo contexto.

- **A legenda vem pelo `yt-dlp`, nunca por `fetch` direto.** Uma requisição
  comum a `/api/timedtext` recebe `200` **com corpo vazio** — o YouTube passa
  a exigir token de origem de navegador real. O `yt-dlp` contorna pedindo os
  dados ao player *android vr*. **Isso é uma fragilidade conhecida**: quando o
  YouTube fechar essa porta, a ferramenta para, e não há plano B fácil.

- **`transcrever_artigo` não devolve o texto na resposta do MCP.** Grava em
  disco e devolve o índice. Um único artigo rendeu 23.420 palavras; despejar
  isso numa resposta estoura o contexto e derruba a conversa.

- **Vídeo sem fala → quadros lidos pela própria IA**, não serviço externo de
  compreensão de vídeo. Ver `.claude/rules/seguranca.md`.

- **O vídeo em si não é baixado pelo `yt-dlp`.** Os *metadados* passam pelo
  proxy sem credencial (é assim que a URL do `googlevideo` é obtida), mas os
  *bytes* recebem `407` mesmo com `--proxy`. A transferência é feita em
  pedaços pelo `Invoke-WebRequest -Proxy … -ProxyUseDefaultCredentials`, o
  único cliente da máquina que autentica sozinho. Ver `baixar_video`.

- **Download do `googlevideo` usa `&range=` como parâmetro de URL.** É o que o
  próprio `yt-dlp` faz, e o fatiamento evita o estrangulamento e o timeout de
  requisição única e grande. Nota: o header `Range` também respondeu `206`
  corretamente num teste em 2026-08-14 — a afirmação anterior de que "o header
  devolve zero bytes" não reproduziu. O parâmetro está mantido por ser o
  caminho testado em todos os formatos, não porque o header seja quebrado.

## Comandos úteis

```bash
python transcrever.py --outline <url>      # transcreve um artigo inteiro
python transcrever.py --outline <url> --quadros   # + imagens dos sem legenda
python transcrever.py --texto arquivo.txt  # de qualquer texto colado
python imagens.py <url-artigo>             # baixa as imagens do artigo
python quadros.py video.mp4                # quadros de vídeo local sem fala

python redigir.py transcricoes/<artigo>    # transcrição → documento
python publicar.py <arquivo.md> --base <url> --colecao <id>
python publicar.py --base <url> --listar-colecoes   # leitura, para achar o id
python console.py --outline <url>          # a interface, em 127.0.0.1:8765

# testar o MCP na mão
Get-Content teste.jsonl | python mcp_server.py
```

Não há suíte de testes automatizados. A verificação é manual e está descrita
em `.claude/rules/estilo-codigo.md`.

## Limites propositais (não implementar)

- **Nada de serviço externo de análise de vídeo/imagem.** O conteúdo é
  interno e frequentemente tem credencial na tela.
- **Não transcrever áudio.** Exigiria `pip` (bloqueado) e resolve pouco: onde
  não há legenda, geralmente não há fala.
- **Não versionar o conteúdo extraído.** Ver `.claude/rules/seguranca.md`.

## Regras

Consultar antes de desenvolver:

- `.claude/rules/commits.md` — padrão de commits
- `.claude/rules/estilo-codigo.md` — estilo e verificação antes de commitar
- `.claude/rules/seguranca.md` — **obrigatório**: o conteúdo extraído já
  continha tokens de API reais

## Skills

- `.claude/skills/extrair-conhecimento/` — o fluxo completo de virar um
  artigo de documentação em conhecimento utilizável, incluindo a curadoria
- `.claude/skills/auditar-imagens/` — varredura de vazamento de credencial
  em print de tela
