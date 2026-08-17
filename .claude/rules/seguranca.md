# Segurança

Esta regra existe por evidência, não por precaução teórica. Ao extrair as
imagens de **um único artigo** da documentação interna, foram encontrados
**dois tokens de API reais** legíveis em print de tela:

- um JWT completo no campo `API Token` do Cadastro de Usuário;
- outro no header `Authorization` de uma requisição no Insomnia.

E o vídeo anexado a outro artigo exibe um **nome de usuário** num prompt de
autenticação do Subversion.

Ou seja: **o conteúdo que esta ferramenta extrai deve ser tratado como
potencialmente contendo credenciais.**

## Nunca versionar o conteúdo extraído

`transcricoes/`, `imagens/` e `quadros/` estão no `.gitignore`. **Não
remover.** Não versionar "só um exemplo", não colar trecho de imagem em
documentação, não subir print para issue.

O repositório é privado, mas repositório privado vira público por engano e
histórico do git não esquece.

## Nunca mandar conteúdo interno para serviço externo

Foi uma decisão explícita de arquitetura descartar serviços hospedados de
compreensão de vídeo/imagem (TwelveLabs Pegasus e equivalentes), por três
motivos, nesta ordem de peso:

1. o conteúdo tem credencial na tela — enviar é vazamento;
2. exigiria URL pública do vídeo, que documentação interna não tem;
3. o domínio da API estava bloqueado no proxy de qualquer forma.

Vídeo sem fala se resolve **local**: `ffmpeg` extrai os quadros e a própria
IA da conversa lê as imagens. Para texto em terminal isso é tecnicamente
superior — um modelo de vídeo descreveria "um terminal com texto branco",
enquanto ler o quadro entrega o comando digitado e a resposta.

## Segredos

- Desde a decisão de 2026-08-15 (ver `CLAUDE.md`), o motor em uso
  (`console.py`, `mcp_server.py`, `transcrever.py`) **não lê nenhum segredo
  próprio** — a entrada é só link de vídeo do YouTube, sem autenticação.
  `publicar.py` continua lendo `OUTLINE_API_KEY`/`OUTLINE_API_TOKEN` e
  `OBSIDIAN_VAULT` de `.env`, mas está órfão, sem consumidor hoje.
- Se algum dia ler segredo de novo: **preferir a variável de ambiente que já
  existe** a pedir que o segredo seja duplicado num arquivo novo — duplicar
  segredo aumenta a superfície.
- Nunca imprimir o valor de um token em log, em saída de comando ou em
  resposta. Para diagnosticar, imprimir só presença e tamanho.

## Ao encontrar credencial no conteúdo extraído

Avisar imediatamente e de forma destacada, **sem reproduzir o valor**.
Identificar onde está (artigo, imagem, instante do vídeo) para que possa ser
revogada e a mídia corrigida.
