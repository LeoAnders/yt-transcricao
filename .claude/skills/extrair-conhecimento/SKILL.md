---
name: extrair-conhecimento
description: Use ao transformar um artigo de documentação com vídeos e imagens em material utilizável por IA — gatilhos como "extrai o conhecimento desse artigo", "transcreve esses vídeos", "transforma essa doc em skill", "processa o artigo X do Outline". Orquestra o fluxo completo: descobrir, transcrever, extrair imagens, destilar, consolidar e submeter à curadoria humana.
---

# Extrair conhecimento de documentação com vídeo e imagem

Transcrever não é o trabalho — é o primeiro passo dele. Transcrição bruta é
insumo ruim: reconhecimento automático de fala destrói jargão técnico, não
pontua, e um arquivo por vídeo multiplica arquivos por vídeo em vez de por
assunto.

O fluxo tem seis passos e **o último é humano**. Não pular.

## 1. Descobrir o que existe, antes de baixar

```bash
python transcrever.py --outline <url>   # ou --texto / --pagina
```

Pelo MCP, `listar_videos_do_artigo` mostra o conteúdo sem gastar nada. Use
isso primeiro: saber que são 19 vídeos muda o plano em relação a 3.

O rótulo do link na documentação **costuma divergir** do título real no
YouTube. O link é a única chave confiável — nunca cruze por nome.

## 2. Transcrever

O texto sai em `transcricoes/<artigo>/`, um `.md` por vídeo.

Vídeos sem legenda aparecem listados no fim. Vídeo sem legenda quase sempre é
vídeo sem fala: vá para o passo 3.

## 3. Extrair o que só existe em imagem

```bash
python imagens.py <url-artigo>       # prints de tela do artigo
python quadros.py <video>            # vídeo mudo, gravação de tela
```

**Este passo não é opcional, e é onde mais gente erra.** Documentação técnica
coloca na figura justamente o que o texto não descreve. Casos reais deste
projeto:

- o texto diz "libere os endpoints no cadastro de usuário" e **não diz a
  aba**; a imagem mostra que é a aba `Serviço`, diferente da `Segurança`;
- o texto manda escrever `"deprecated" = true`, que é **JSON inválido**; a
  imagem mostra o correto, `"deprecated": true`;
- a estrutura real de um template — nomes das propriedades `x-`, hierarquia,
  endpoints gerados — está legível num quadro do vídeo e sai como
  *"xis a p i neime"* na transcrição.

Para gravação de tela, **o quadro vale mais que a transcrição**: a legenda diz
*por que*, o quadro diz *o quê*.

Leia as imagens e os quadros. Ao encontrar credencial, ver
`.claude/rules/seguranca.md` — avisar sem reproduzir o valor.

## 4. Destilar

Transcrição bruta → **procedimento acionável**. Alvo de 30 a 60 linhas por
assunto:

- passos numerados, na ordem em que acontecem;
- o que dá errado e a mensagem que aparece;
- nomes reais de rotina, campo, aba e botão — reconstruídos do jargão torto
  do ASR usando o que as imagens mostram;
- o que a documentação escrita omite (um vídeo revelou um passo de
  autenticação do Subversion que nenhum dos artigos menciona).

Descarte: saudação, "como eu falei no vídeo anterior", passo dito e refeito,
tudo que é ruído de fala.

## 5. Consolidar por assunto, não por vídeo

Os 19 vídeos de "Implementar uma API" viram **um** arquivo. É isso que impede
o inchaço: o número de arquivos acompanha o número de assuntos.

## 6. Curadoria humana — obrigatória

**Nunca entregue o destilado como verdade.** A transcrição não sabe que
envelheceu. Caso real: a página diz *"não é mais necessário o uso do
Swagger"* e a lista de vídeos logo abaixo ainda oferece *"Apresentação do
Swagger Editor"*. Um resumo ingênuo ensina o time a usar Swagger.

Entregue com uma **lista de pendências no topo**, contendo só o que você não
pode decidir:

```markdown
## ⚠️ Conferir antes de usar

- Vídeo ensina o caminho via Swagger Editor, mas a página diz "não é mais
  necessário o uso do Swagger" e manda usar VS Code. Descartar o trecho?
- ASR transcreveu "cê esse dáblio um A"; deduzi `%CSW1A` pelo contexto.
- Vídeo de 2024; a tela mostrada tem campo que a versão atual não tem.
```

Conflito entre vídeo e texto escrito, procedimento possivelmente caduco e
decisão de negócio vão para o humano. Fato técnico verificável no código ou
na imagem, você resolve.

A atenção do revisor é o recurso caro do fluxo — gaste só onde ela é
insubstituível.
