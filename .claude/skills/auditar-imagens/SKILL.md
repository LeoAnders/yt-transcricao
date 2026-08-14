---
name: auditar-imagens
description: Use para varrer print de tela da documentação em busca de credencial ou dado sensível exposto — gatilhos como "tem token vazado nas imagens?", "audita as imagens da doc", "varre a documentação por senha", "essas prints têm dado sensível?". Baixa as imagens dos artigos, lê cada uma e reporta achados sem reproduzir o valor.
---

# Auditar imagens da documentação por vazamento

Print de tela de sistema vaza credencial com frequência muito maior do que as
pessoas supõem. Quem grava está demonstrando o funcionamento, não pensando em
segurança — e a imagem fica publicada por anos.

**Isto não é hipótese.** Na primeira varredura deste projeto, **um único
artigo** rendeu dois tokens de API reais e legíveis. Num deles, o autor tarjou
de amarelo o código do item da resposta e deixou o JWT do header à vista.

## Como varrer

```bash
python imagens.py <url-do-artigo>
```

Depois **leia cada imagem baixada**. É a IA que lê — não há OCR nem serviço
externo envolvido (ver `.claude/rules/seguranca.md`).

Para vídeo, `quadros.py` e leia os quadros. Vídeo vaza igual: uma gravação
deste acervo exibe nome de usuário num prompt de autenticação.

## O que procurar

- **Token / JWT** — sequência começando com `eyJ`, em campo de token, header
  `Authorization`, URL ou variável de ambiente
- **Senha** — inclusive campo mascarado com o texto ainda visível na barra de
  status ou no histórico do terminal
- **String de conexão** — usuário, host, porta, namespace
- **Dado de cliente** — CNPJ, razão social, nome de pessoa, e-mail, telefone
- **Identidade interna** — usuário de rede, caminho de máquina, IP
- **Chave de API de terceiro** — em tela de configuração ou integração

## Como reportar

**Nunca reproduza o valor**, nem parcialmente, nem "só o começo para
identificar". Reportar:

1. **onde** — artigo, arquivo da imagem, e o instante quando for vídeo
2. **o que** — a natureza ("JWT completo no header `Authorization`")
3. **contexto de risco** — base de teste ou produção, se houver pista
4. **ação** — revogar a credencial e corrigir a mídia

Exemplo:

```markdown
## ⚠️ Credencial exposta

**Artigo "Executar uma API" — imagem 01.png**
JWT completo e legível no campo `API Token` do Cadastro de Usuário.
Usuário 16, empresa "EMPRESA MODELO IND. COM. 2 LTDA" (sugere base de teste).
Ação: revogar o token e recortar a imagem.
```

Colocar o achado **no topo** da resposta, antes de qualquer outro assunto.
Credencial exposta é mais urgente que o que quer que estivesse sendo pedido.

Se a mesma credencial aparecer em várias imagens, reportar uma vez com a
lista de ocorrências — não repetir o alerta.
