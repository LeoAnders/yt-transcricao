# Estilo de código

## Geral

- **Python 3.10+, só biblioteca padrão.** A proibição de `pip` é requisito de
  ambiente, não preferência — ver `CLAUDE.md`. Ao precisar de algo que
  "pediria uma lib", escrever na mão ou repensar o desenho.
- Aspas duplas, 4 espaços de indentação, anotações de tipo nas assinaturas
  públicas.
- Docstring de módulo explicando **por que o módulo existe**, não o que ele
  faz — o nome já diz o que faz.
- Comentários explicam o **porquê**, especialmente quando o código parece
  estranho. Todo contorno de ambiente (proxy, `&range=`, player *android vr*)
  precisa de comentário dizendo o que acontece se for removido, senão o
  próximo a mexer "simplifica" e quebra.

## Módulos puros

`descobrir.py` e `limpar.py` **não podem** importar `subprocess`, `winreg`,
nem chamar rede. Recebem texto/arquivo, devolvem estrutura. É o que permite
testá-los sem internet e sem `yt-dlp`.

Quando uma função nova precisar de rede, ela vai para `transcrever.py` ou
`imagens.py`, não para os puros.

## Servidor MCP

- **O `stdout` pertence ao protocolo.** Qualquer `print` de outro módulo
  precisa ir para `stderr` — no `mcp_server.py` isso é feito com
  `contextlib.redirect_stdout(sys.stderr)`.
- Todo `subprocess.run` chamado no caminho do MCP usa `capture_output=True`.
  Um `yt-dlp` escrevendo progresso no `stdout` herdado quebra a sessão inteira.
- Erro de ferramenta volta como `isError: true` com texto explicativo, nunca
  como exceção que mata o servidor.

## Nomes

- Funções e variáveis em pt-BR (`baixar_legendas`, `anexos_com_contexto`,
  `pendentes`), exceto termos técnicos naturais em inglês.
- Ferramentas do MCP em pt-BR (`obter_transcricao`, `extrair_quadros`) — quem
  as lê é um modelo que trabalha em português neste projeto.

## Verificação antes de commitar

Não há suíte automatizada. O mínimo, manual:

```bash
# 1. os módulos puros
python -c "import descobrir; print(len(descobrir.ids_em_texto('https://youtu.be/p3v0EAaR2SU')))"

# 2. o caminho completo num vídeo curto
python transcrever.py u2k8KF3d4-E --saida transcricoes/teste

# 2b. o caminho dos quadros. O --idioma zz força o vídeo a cair em "sem
#     legenda" sem precisar achar um vídeo mudo de verdade — é o que exercita
#     o download pelo Invoke-WebRequest, que é a parte frágil.
python transcrever.py u2k8KF3d4-E --idioma zz --sem-fallback --quadros \
    --saida transcricoes/teste-quadros --intervalo-quadros 10

# 3. o MCP responde ao handshake
Get-Content teste.jsonl | python mcp_server.py

# 4. nada de conteúdo extraído no git
git status --short
```

Mexeu no `mcp_server.py`? Rodar `claude mcp list` e confirmar `Connected`
antes de considerar pronto.
