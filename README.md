# yt-transcricao

Transforma vídeos do YouTube em texto, usando a legenda automática que o
próprio YouTube já gera.

## Por que existe

Documentação interna costuma ter vídeos. Um vídeo é ótimo para uma pessoa e
inútil para uma IA: o modelo não assiste. Se você quer que os vídeos façam
parte de uma base de conhecimento — uma skill, um RAG, um agente —, alguém
precisa transformá-los em texto uma vez.

Fazer isso na mão significa assistir tudo e digitar. Trinta e cinco vídeos
de dez minutos são quase seis horas.

Esta ferramenta faz o mesmo em poucos minutos, sem abrir vídeo nenhum. Ela
não assiste, não baixa vídeo e não roda reconhecimento de fala: pega a
legenda que o YouTube já gerou, limpa e formata.

## Requisitos

- Python 3.10+
- Windows (a detecção de proxy e o download do `yt-dlp` usam recursos do SO)

O `yt-dlp.exe` é baixado sozinho na primeira execução — nada é instalado no
sistema, e ele fica fora do repositório.

## Uso

```bash
# um ou mais vídeos
python transcrever.py https://youtu.be/p3v0EAaR2SU

# a partir de um arquivo com uma URL por linha
python transcrever.py --lista links.txt

# varrendo um artigo do Outline (pega todos os links de YouTube dele)
python transcrever.py --outline https://cuka.consistem.com.br/doc/implementar-uma-api-IWJkirUuRw

# separando a saída por assunto
python transcrever.py --lista links.txt --saida "transcricoes/Implementar uma API"
```

Aceita URL completa (`youtu.be/...`, `youtube.com/watch?v=...`) ou só o ID de
11 caracteres.

O resultado sai em `transcricoes/`, um `.md` por vídeo:

```markdown
# Introdução à API

- Vídeo: https://youtu.be/p3v0EAaR2SU
- Origem: legenda automática do YouTube, não revisada

---

(00:01) Então nesse vídeo a gente vai falar sobre api uma pequena introdução...

(00:35) dados e gravar dados no outro é como se ela como se a pi fosse uma ponte...
```

### Opções

| Opção | Para quê |
| --- | --- |
| `--lista ARQUIVO` | lê as URLs de um arquivo, uma por linha |
| `--outline URL` | varre os links de YouTube de um artigo do Outline |
| `--saida PASTA` | muda o destino (padrão: `transcricoes`) |
| `--idioma pt` | idioma da legenda (padrão: `pt`) |
| `--sem-proxy` | ignora o proxy configurado no Windows |

## Outline

O `--outline` precisa de um token de API. Copie o `.env.example` para `.env`
e preencha:

```
OUTLINE_API_TOKEN=seu_token_aqui
```

O token sai em **Outline → Settings → API Tokens**. O `.env` está no
`.gitignore` — não versione o token.

## Estrutura

| Arquivo | Responsabilidade |
| --- | --- |
| `transcrever.py` | linha de comando, proxy, download, descoberta de links |
| `limpar.py` | converte `.vtt` em Markdown — **puro**, não conhece rede |

A separação é proposital: `limpar.py` é testável sem internet e sem
`yt-dlp`, bastando um `.vtt` de exemplo.

## Como funciona

1. **Descoberta** — links de YouTube vêm da linha de comando, de um arquivo
   ou da API do Outline (`documents.info`).

2. **Download** — o `yt-dlp` baixa a legenda automática em `.vtt`.

   O detalhe que faz a coisa funcionar: uma requisição comum ao endpoint
   `/api/timedtext` do YouTube recebe `200` **com corpo vazio**, porque o
   YouTube passou a exigir um token de origem de navegador real. O `yt-dlp`
   contorna isso pedindo os dados ao player *android vr*, que não é
   submetido a essa checagem. Sem esse desvio, não há legenda fora do
   navegador.

3. **Limpeza** (`limpar.py`) — a legenda automática vem em modo "rolante":
   cada bloco repete a linha anterior e traz uma tag `<c>` por palavra, com
   timestamp próprio. Lido cru, o texto sai com cerca de três vezes o
   tamanho real. O script remove as tags, descarta as repetições e reagrupa
   a fala em parágrafos de 30 segundos.

O proxy é detectado pelas variáveis `HTTP(S)_PROXY` ou pelas configurações
de Internet do Windows — nada de IP chumbado no código.

## Limitações conhecidas

- **A qualidade é de reconhecimento automático de fala.** Jargão técnico sai
  torto: "Swagger" vira "swager" ou "suegra", "API" vira "a pi". O texto é
  bom o bastante para um LLM interpretar — e um LLM costuma reconstruir o
  termo pelo contexto —, mas não serve para publicar como está.

- **Sem pontuação.** A legenda do YouTube não pontua.

- **Só funciona onde existe legenda automática.** Vídeo sem fala não gera
  legenda. Os que falharem são listados no fim da execução; para eles seria
  preciso transcrever o áudio, o que está fora do escopo desta ferramenta.

- **Vídeo pode estar desatualizado em relação à documentação escrita.** Um
  vídeo de 2024 ensina um procedimento que a página já substituiu — e a
  transcrição não sabe disso. Revise antes de usar como fonte de verdade.

- **O título do vídeo no YouTube costuma divergir do texto do link na
  documentação.** Os arquivos usam o título real do YouTube; para cruzar com
  a documentação, use o link, que é a única chave confiável.
