# Task Master

O backlog deste projeto vive no Task Master, em `.taskmaster/tasks/tasks.json`,
versionado junto com o código.

Existe por um motivo específico: as decisões deste projeto se perdem em
conversa. O que sobra num `tasks.json` é o **porquê** de cada pendência — e a
maior parte das tarefas aqui nasceu de uma limitação conhecida, não de uma
ideia. Uma tarefa sem o motivo escrito é uma tarefa que alguém vai reabrir
daqui a três meses perguntando "por que isso importava?".

## Sem chave de API

Os três papéis (`main`, `research`, `fallback`) usam o provedor `claude-code`,
que fala com o `claude` já instalado na máquina. **Não configure
`ANTHROPIC_API_KEY` nem nenhuma outra chave** — não é necessário, e chave em
arquivo de projeto é superfície de vazamento (ver `seguranca.md`).

O `.mcp.json` foi propositalmente enxugado: o `init` do Task Master escreve
nove chaves de exemplo (`YOUR_ANTHROPIC_API_KEY_HERE` e companhia), que são um
convite para alguém preencher e commitar. Se rodar `init` de novo, enxugue
outra vez.

## Uma tarefa, um PR

É a ponte com o `commits.md`, e não é coincidência: lá, **um PR trata de um
assunto só**, porque o squash colapsa o branch num commit no `main`. Aqui,
**uma tarefa é um assunto**. Então:

```bash
task-master next                              # o que fazer agora
task-master show <id>                         # ler os detalhes antes de mexer
task-master set-status --id=<id> --status=in-progress

git checkout -b feat/nome-descritivo          # tipo do commits.md
# ... commits segmentados dentro do branch ...
gh pr create --base main --title "feat: descricao"
gh pr merge <n> --squash --delete-branch

task-master set-status --id=<id> --status=done
```

O `set-status --done` vem **depois do merge**, não depois do código escrito.
Tarefa concluída com PR aberto é tarefa que mente para quem olha o quadro.

Tarefa grande demais para um PR não é uma tarefa: quebre com
`task-master expand --id=<id>`, e cada subtarefa vira um PR.

## O que escrever numa tarefa

O campo `details` é onde mora o valor. Ele precisa responder três coisas:

- **por que isto existe** — a limitação concreta, com o caso real quando
  houver ("o documento cita 00:04:18 e a imagem não aparece");
- **onde mexer** — arquivo e função, para quem pegar não ter que redescobrir;
- **como verificar** — não há suíte automatizada neste repositório
  (`estilo-codigo.md`), então a verificação manual precisa estar escrita na
  tarefa, senão não acontece.

Tarefa que só diz o que fazer, sem o porquê e sem como conferir, não deveria
ser criada.

## Criar sem gastar chamada de modelo

`add-task --prompt` chama a IA para redigir a tarefa. Quando você já sabe o que
quer, use os campos manuais — é instantâneo e o texto sai como você escreveu:

```bash
task-master add-task --priority high \
  --title "..." --description "..." --details "..." \
  --dependencies 2,3
```

Guarde o `--prompt` e o `--research` para quando o assunto for genuinamente
mal definido.

## Dependências dizem a ordem, não a importância

`--dependencies` existe para impedir trabalho na ordem errada — mexer na
interface antes de saber se ela abre num navegador, por exemplo. Depois de
mexer nelas, rode:

```bash
task-master validate-dependencies
```

Dependência circular trava o `next` e o sintoma é ele não sugerir nada.

## Nunca escrever numa tarefa

Vale a mesma regra de todo o resto (`seguranca.md`):

- **valor de token, senha ou chave** — nem para exemplificar. O `tasks.json` é
  versionado;
- **trecho de conteúdo extraído** — nada de `transcricoes/`, `imagens/` ou
  `quadros/` colado em descrição. Descreva o problema, não cole o material;
- **nome de cliente ou dado de pessoa** que tenha aparecido num print.

## Comandos do dia a dia

```bash
task-master list                     # o quadro inteiro
task-master list --status=pending    # só o que falta
task-master next                     # a próxima respeitando dependências
task-master show <id>                # detalhes de uma
task-master set-status --id=<id> --status=done
task-master add-task ...             # nova tarefa
task-master expand --id=<id>         # quebrar em subtarefas
task-master validate-dependencies    # conferir o grafo
```

Os comandos também existem como `/tm:*` dentro do Claude Code — mesma coisa,
por outro caminho.
