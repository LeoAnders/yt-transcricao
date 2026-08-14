# Padrão de commits

- Convenção **Conventional Commits em pt-BR** (mesma do resto dos projetos
  do autor).
- **Mensagem única**, uma linha, sem corpo e **sem coautor** — não adicionar
  `Co-Authored-By`, nem rodapé de "Generated with", nem qualquer outra
  atribuição a ferramenta de IA, em commit ou em descrição de PR.
- **Segmentar por assunto lógico.** Nunca um commit gigante com tudo
  misturado: uma coisa por commit, mesmo que sejam quatro commits seguidos.
- Descrição curta, minúsculas, no imperativo.

## Fluxo: branch → PR → squash

**Nunca commitar direto no `main`.** Todo trabalho nasce em branch, vira PR e
entra por **squash merge**:

```bash
git checkout -b feat/nome-descritivo
# ... commits segmentados por assunto ...
git push -u origin feat/nome-descritivo
gh pr create --base main --title "tipo: descricao" --body "..."
gh pr merge <n> --squash --delete-branch
```

O nome do branch usa o mesmo tipo do commit (`feat/`, `fix/`, `docs/`).

**O título do PR é a mensagem que sobra no `main`**, porque o squash colapsa
os commits do branch num só. Por isso ele precisa seguir o formato de commit
acima — e por isso **um PR trata de um assunto só**. Dois assuntos no mesmo
PR viram um commit misturado no `main`, que é exatamente o que a segmentação
por assunto existe para evitar.

Os commits *dentro* do branch continuam segmentados: eles são o histórico da
revisão. Quem lê o `main` vê um commit por assunto; quem lê o PR vê o passo a
passo.

O merge é feito pela IA quando pedido, mas o `main` não é emendado sem que o
PR exista — é o PR que deixa a mudança revisável depois.

## Tipos

| Tipo       | Uso                                        |
| ---------- | ------------------------------------------ |
| `feat`     | nova funcionalidade                        |
| `fix`      | correção de bug                            |
| `docs`     | documentação (README, CLAUDE.md, regras)   |
| `chore`    | manutenção, configuração, `.gitignore`     |
| `refactor` | refatoração sem mudança de comportamento   |
| `perf`     | melhoria de performance                    |
| `test`     | testes                                     |

## Formato

```
tipo: descrição curta em minúsculas no imperativo
```

Exemplos reais deste repositório:

```
feat: adiciona transcritor de videos do youtube pela legenda automatica
feat: adiciona extracao de quadros para video sem fala
feat: adiciona servidor mcp em python puro sem dependencias
docs: documenta fontes genericas, quadros e servidor mcp
```

## Antes de commitar

**Conferir que nada de conteúdo extraído entrou** — é a checagem mais
importante deste repositório, porque o material baixado já continha tokens de
API reais (ver `seguranca.md`):

```bash
git status --short      # não deve aparecer transcricoes/, imagens/, quadros/
git ls-files            # só os .py, .md e os arquivos de configuração
```
