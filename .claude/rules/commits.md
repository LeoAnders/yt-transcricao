# Padrão de commits

- Convenção **Conventional Commits em pt-BR** (mesma do resto dos projetos
  do autor).
- **Mensagem única**, uma linha, sem corpo e **sem coautor** — não adicionar
  `Co-Authored-By`.
- **Segmentar por assunto lógico.** Nunca um commit gigante com tudo
  misturado: uma coisa por commit, mesmo que sejam quatro commits seguidos.
- Descrição curta, minúsculas, no imperativo.

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
