# yt-transcricao

Motor que transforma vídeo do YouTube em texto e imagem que uma IA consegue
ler. Funciona como linha de comando, como servidor MCP e como API HTTP —
**a entrada é sempre um ou mais links de vídeo do YouTube, nunca artigo de
documentação** (Outline, Notion etc.): quem tiver o texto de um artigo em
mãos usa o MCP da própria ferramenta de documentação para achar os links, e
passa os links pra cá. Ver "Decisão de 2026-08-15", abaixo.

Nasceu de um problema concreto: a documentação interna da empresa tem ~35
vídeos no YouTube. Uma IA não assiste vídeo — então esse conteúdo
simplesmente não existe para uma skill ou um RAG montado sobre o texto.

## Decisão de 2026-08-15: motor, não plataforma

Este projeto **não lê artigo de documentação nem publica em destino
nenhum** — já leu (Outline, via API própria) e já publicou (Outline,
Obsidian), e os dois foram retirados daqui de propósito:

- **Ler artigo é redundante com o MCP da própria ferramenta.** Quem usa
  este projeto via agente de IA já tem o MCP do Outline (ou o que for)
  conectado — pedir a esse MCP o texto do artigo e chamar
  `descobrir.urls_em_texto` nele é estritamente melhor que este projeto
  reimplementar um cliente REST do Outline com seu próprio token.
- **A interface (React/Vite) mora em outro repositório.** Este projeto
  expõe só a API HTTP (`console.py`) e o MCP (`mcp_server.py`); quem quiser
  uma tela fala com a API, não importa este código Python. O primeiro
  consumidor é o **Vidraft** (repositório irmão), uma demo pro time de
  marketing: cola o link de um vídeo de treinamento/demonstração já
  gravado e recebe um rascunho de conteúdo com os prints reais extraídos
  do vídeo.
- **`publicar.py` continua no repositório, mas não é chamado por
  `console.py`.** Publicar num destino (Outline, Obsidian) é decisão de
  produto, não do motor — fica guardado para se um dia existir de novo um
  console de revisão interna, mas hoje é código órfão, sem consumidor.

Consequência prática: **`imagens.py` foi removido** (baixava print de
artigo do Outline — mesma redundância com o MCP), e as ferramentas de MCP
`listar_videos_do_artigo`, `transcrever_artigo` e `imagens_do_artigo`
também. A flag `--outline` saiu do `transcrever.py`.

**Pendência conhecida:** a skill `.claude/skills/extrair-conhecimento/`
ainda referencia essas ferramentas removidas — precisa ser reescrita para
orquestrar via MCP do Outline + `extrair_videos`/`obter_transcricao`/
`quadros_do_video` em vez de chamar as ferramentas antigas diretamente.

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

O proxy corporativo exige autenticação integrada do Windows, e o `pip` não
sabe fazê-la. Isso elimina de saída o SDK oficial do MCP, o `requests`, o
`faster-whisper` e qualquer biblioteca. Só a biblioteca padrão do Python.

**A restrição é do `pip`, não do `npm`.** Medido em 2026-08-14, nesta
máquina: `pip download requests` recebe `407`, enquanto `npm install react`
completa em menos de um segundo — o `npm` alcança o `registry.npmjs.org`
sem proxy configurado. Os dois foram tratados como o mesmo caso por um
tempo e não são. **Antes de descartar uma ferramenta por causa do proxy,
teste-a**; a suposição custou uma interface reescrita à toa.

Consequências que **não devem ser revertidas** sem resolver o proxy primeiro:

- o servidor MCP fala JSON-RPC 2.0 na mão, sobre stdio;
- downloads que precisam de credencial de proxy são feitos via
  `powershell -Command Invoke-WebRequest -ProxyUseDefaultCredentials`, que é
  o único cliente na máquina que autentica sozinho;
- o `yt-dlp.exe` é baixado avulso do GitHub, não instalado por pacote;
- **não há interface neste repositório** (ver "Decisão de 2026-08-15"). Se um
  dia isso mudar, a mesma lógica de "`npm` funciona, `pip` não" volta a valer.

## Estrutura

```
descobrir.py     Acha vídeos em texto/página — extração PURA, sem Outline
limpar.py        Converte .vtt em Markdown — PURO, não conhece rede
quadros.py       Extrai quadros de vídeo via ffmpeg (para vídeo sem fala)
transcrever.py   Linha de comando: proxy, download, orquestração
redigir.py       Transcrição + quadros → documento, pelo `claude` da máquina
publicar.py      Destinos (Outline, Obsidian) — órfão, sem consumidor hoje
console.py       API HTTP do motor — stdlib em 127.0.0.1, sem interface
mcp_server.py    Servidor MCP sobre os módulos acima
```

A interface (React/Vite) que consome a API do `console.py` mora no
repositório irmão **Vidraft**, não aqui.

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

- **As ferramentas de MCP que geram arquivo não devolvem o texto na
  resposta.** Gravam em disco e devolvem o índice. Um único vídeo bem falado
  já passa de mil palavras; devolver o corpo inteiro de vários de uma vez
  estoura o contexto e derruba a conversa. `/api/gerar` no `console.py` segue
  a mesma lógica: devolve o caminho do arquivo, não o corpo.

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
python transcrever.py https://youtu.be/xxxx        # transcreve um ou mais vídeos
python transcrever.py https://youtu.be/xxxx --quadros   # + imagens dos sem legenda
python transcrever.py --texto arquivo.txt          # de qualquer texto colado
python quadros.py video.mp4                        # quadros de vídeo local sem fala

python redigir.py transcricoes/<pasta>             # transcrição → documento
python console.py                                  # API em 127.0.0.1:8765, sem interface

# testar o MCP na mão
Get-Content teste.jsonl | python mcp_server.py
```

`publicar.py` (Outline, Obsidian) segue no repositório mas não é chamado por
nada hoje — ver "Decisão de 2026-08-15".

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
- `.claude/rules/taskmaster.md` — o backlog e o fluxo de uma tarefa até o
  merge; **uma tarefa é um PR**, que é a mesma regra do `commits.md`
- `.claude/rules/estilo-codigo.md` — estilo e verificação antes de commitar
- `.claude/rules/seguranca.md` — **obrigatório**: o conteúdo extraído já
  continha tokens de API reais

## Skills

**As duas seguintes estão QUEBRADAS depois da decisão de 2026-08-15** — ambas
chamam `imagens.py`/as ferramentas de MCP de artigo do Outline, que foram
removidas. Precisam ser reescritas para orquestrar via MCP do Outline antes
de voltar a funcionar:

- `.claude/skills/extrair-conhecimento/` — o fluxo completo de virar um
  artigo de documentação em conhecimento utilizável, incluindo a curadoria
- `.claude/skills/auditar-imagens/` — varredura de vazamento de credencial
  em print de tela

## Task Master AI Instructions
**Import Task Master's development workflow commands and guidelines, treat as if import is in the main CLAUDE.md file.**
@./.taskmaster/CLAUDE.md
