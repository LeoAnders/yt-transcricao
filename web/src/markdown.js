/* Markdown suficiente para o que o redigir.py produz: cabeçalho, lista
 * numerada, lista simples, negrito e código inline. Não é um renderizador
 * geral e não deve virar um — o documento de verdade é o arquivo .md.
 *
 * Tudo é escapado ANTES de virar marcação, e é isso que permite entregar o
 * resultado a dangerouslySetInnerHTML: o texto vem de um modelo lendo tela de
 * sistema, então tratar como hostil é o padrão, não o exagero. */

export function escapar(texto) {
  return String(texto).replace(
    /[&<>"]/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c],
  );
}

const enfeitar = (linha) =>
  linha
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/_\(([^)]+)\)_/g, "<small>($1)</small>");

export function inline(texto) {
  return enfeitar(escapar(texto));
}

export function paraHtml(texto) {
  const saida = [];
  let lista = null;
  const fechar = () => {
    if (lista) {
      saida.push(`</${lista}>`);
      lista = null;
    }
  };

  for (const bruta of escapar(texto).split("\n")) {
    const linha = enfeitar(bruta);

    if (/^#{2,}\s/.test(linha)) {
      fechar();
      saida.push(`<h2>${linha.replace(/^#+\s/, "")}</h2>`);
      continue;
    }
    if (/^#\s/.test(linha)) {
      fechar();
      saida.push(`<h1>${linha.slice(2)}</h1>`);
      continue;
    }

    const numerado = linha.match(/^\s*\d+\.\s+(.*)$/);
    if (numerado) {
      if (lista !== "ol") {
        fechar();
        saida.push("<ol>");
        lista = "ol";
      }
      saida.push(`<li>${numerado[1]}</li>`);
      continue;
    }

    const marcado = linha.match(/^\s*[-*]\s+(.*)$/);
    if (marcado) {
      if (lista !== "ul") {
        fechar();
        saida.push("<ul>");
        lista = "ul";
      }
      saida.push(`<li>${marcado[1]}</li>`);
      continue;
    }

    fechar();
    if (linha.trim()) saida.push(`<p>${linha}</p>`);
  }

  fechar();
  return saida.join("\n");
}
