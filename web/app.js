/* Console do Docly em React, sem empacotador.
 *
 * `htm` dá a sintaxe de marcação por template literal — praticamente JSX, mas
 * interpretado pelo próprio navegador. É o que permite React aqui sem `npm` e
 * sem Babel: ver o comentário em BIBLIOTECAS, no console.py.
 *
 * Este arquivo não decide nada sobre publicação. Quem recusa é o publicar.py,
 * no servidor — a tela só mostra o motivo. */

"use strict";

const html = htm.bind(React.createElement);
const { useState, useEffect, useCallback, useRef } = React;

// --------------------------------------------------------------------------
// utilidades
// --------------------------------------------------------------------------

async function api(rota, opcoes) {
  const resposta = await fetch(rota, opcoes);
  const dados = await resposta.json();
  if (!resposta.ok) throw new Error(dados.erro || `falhou (${resposta.status})`);
  return dados;
}

const enviar = (rota, corpo) => api(rota, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(corpo),
});

function escapar(texto) {
  return String(texto).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}

/* Markdown suficiente para o que o redigir.py produz: cabeçalho, lista
 * numerada, lista simples, negrito e código inline. Não é um renderizador
 * geral e não deve virar um — o documento de verdade é o arquivo .md.
 *
 * Tudo é escapado ANTES de virar marcação, e é por isso que o resultado pode
 * ir para dangerouslySetInnerHTML: o texto vem de um modelo, e modelo escreve
 * o que estava na tela. */
function paraHtml(texto) {
  const saida = [];
  let lista = null;
  const fechar = () => { if (lista) { saida.push(`</${lista}>`); lista = null; } };

  for (const bruta of escapar(texto).split("\n")) {
    const linha = bruta
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/_\(([^)]+)\)_/g, "<small>($1)</small>");

    if (/^#{2,}\s/.test(linha)) { fechar(); saida.push(`<h2>${linha.replace(/^#+\s/, "")}</h2>`); continue; }
    if (/^#\s/.test(linha)) { fechar(); saida.push(`<h1>${linha.slice(2)}</h1>`); continue; }

    const numerado = linha.match(/^\s*\d+\.\s+(.*)$/);
    if (numerado) {
      if (lista !== "ol") { fechar(); saida.push("<ol>"); lista = "ol"; }
      saida.push(`<li>${numerado[1]}</li>`);
      continue;
    }
    const marcado = linha.match(/^\s*[-*]\s+(.*)$/);
    if (marcado) {
      if (lista !== "ul") { fechar(); saida.push("<ul>"); lista = "ul"; }
      saida.push(`<li>${marcado[1]}</li>`);
      continue;
    }
    fechar();
    if (linha.trim()) saida.push(`<p>${linha}</p>`);
  }
  fechar();
  return saida.join("\n");
}

const inline = (t) => escapar(t)
  .replace(/`([^`]+)`/g, "<code>$1</code>")
  .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
  .replace(/_\(([^)]+)\)_/g, "<small>($1)</small>");

// --------------------------------------------------------------------------
// peças
// --------------------------------------------------------------------------

const Glifo = () => html`<span className="glyph"></span>`;

function Nav() {
  return html`
    <div className="navshell">
      <nav className="nav">
        <span className="logo"><${Glifo} />Docly</span>
        <span className="meio">
          <a href="#gerar">Gerar</a>
          <a href="#revisar">Revisar</a>
        </span>
        <span className="fine">console local · 127.0.0.1</span>
      </nav>
    </div>`;
}

function Passos({ atual }) {
  const nomes = ["Descobrir", "Gerar", "Revisar", "Publicar"];
  return html`
    <div className="steps">
      ${nomes.map((nome, i) => html`
        <${React.Fragment} key=${nome}>
          <span className=${i === atual ? "on" : ""}><b>${i + 1}</b> ${nome}</span>
          ${i < nomes.length - 1 ? html`<i>›</i>` : null}
        <//>`)}
    </div>`;
}

function Etiqueta({ doc }) {
  if (doc.bloqueado) return html`<span className="tag stop">bloqueado</span>`;
  if (doc.pendencias) return html`<span className="tag warn">${doc.pendencias} pendência(s)</span>`;
  return html`<span className="tag ok">pronto</span>`;
}

// --------------------------------------------------------------------------
// gerar
// --------------------------------------------------------------------------

function Gerar({ aoTerminar }) {
  const [url, setUrl] = useState("");
  const [quadros, setQuadros] = useState(true);
  const [achado, setAchado] = useState(null);
  const [erro, setErro] = useState("");
  const [linhas, setLinhas] = useState([]);
  const [rodando, setRodando] = useState(false);
  const fimDoLog = useRef(null);

  useEffect(() => { if (fimDoLog.current) fimDoLog.current.scrollTop = fimDoLog.current.scrollHeight; }, [linhas]);

  const analisar = useCallback(async () => {
    setErro(""); setAchado(null);
    try {
      setAchado(await enviar("/api/analisar", { url: url.trim() }));
    } catch (e) { setErro(e.message); }
  }, [url]);

  const gerar = useCallback(async () => {
    setErro(""); setLinhas([]); setRodando(true);
    try {
      const { id } = await enviar("/api/gerar", { url: url.trim(), quadros });
      // A geração leva minutos e roda numa thread do servidor; a página
      // pergunta o estado em vez de segurar a requisição até o timeout.
      const timer = setInterval(async () => {
        try {
          const t = await api(`/api/trabalho?id=${id}`);
          setLinhas(t.linhas || []);
          if (t.estado === "pronto" || t.estado === "erro") {
            clearInterval(timer);
            setRodando(false);
            if (t.erro) setErro(t.erro);
            aoTerminar();
          }
        } catch (e) { clearInterval(timer); setRodando(false); setErro(e.message); }
      }, 1200);
    } catch (e) { setErro(e.message); setRodando(false); }
  }, [url, quadros, aoTerminar]);

  const passo = rodando ? 1 : achado ? 1 : 0;

  return html`
    <section id="gerar">
      <span className="pill">Novo documento</span>
      <h2>Cola o link. Antes de gastar, mostra o que tem.</h2>
      <p className="lede">A análise é de graça: acontece antes de baixar
        qualquer coisa. Saber que são dezenove vídeos e não três muda o plano.</p>

      <div className="app">
        <div className="titlebar">
          <span className="lights"><i /><i /><i /></span>
          <span className="caminho">docly · novo documento</span>
        </div>
        <div className="pane">
          <${Passos} atual=${passo} />

          <div className="linha">
            <input className="campo" type="text" value=${url} placeholder="https://outline.interno/doc/artigo-XXXX"
                   onChange=${(e) => setUrl(e.target.value)}
                   onKeyDown=${(e) => { if (e.key === "Enter") analisar(); }} />
            <button className="btn" onClick=${analisar} disabled=${!url.trim() || rodando}>Analisar</button>
            <label className="check">
              <input type="checkbox" checked=${quadros} onChange=${(e) => setQuadros(e.target.checked)} />
              ler a tela dos vídeos sem fala
            </label>
            <button className="btn pri" onClick=${gerar} disabled=${!achado || rodando}>
              ${rodando ? "gerando…" : "Gerar documentação"} ${!rodando && achado ? "→" : ""}
            </button>
          </div>

          ${achado && html`
            <div className="counts">
              <div className="hl"><b>${achado.videos.length}</b><span>vídeos encontrados</span></div>
              <div><b>${quadros ? "sim" : "não"}</b><span>ler a tela dos sem fala</span></div>
            </div>
            <p className="lede" style=${{ margin: "14px 0 0", fontSize: "15px" }}>
              Artigo: <strong>${achado.titulo}</strong>
            </p>`}

          ${erro && html`<p className="aviso stop" style=${{ marginTop: "14px" }}>${erro}</p>`}
          ${linhas.length > 0 && html`<div className="log" ref=${fimDoLog}>${linhas.join("\n")}</div>`}
        </div>
      </div>
    </section>`;
}

// --------------------------------------------------------------------------
// revisar
// --------------------------------------------------------------------------

function Pendencias({ doc, aoResolver }) {
  if (!doc.pendencias.length) {
    return html`
      <aside className="rail">
        <div className="rail-head"><strong>Conferir antes de usar</strong>
          <span className="tag ok">nenhuma</span></div>
        <p className="vazio">Nada pendente. O documento está pronto para publicar.</p>
      </aside>`;
  }

  return html`
    <aside className="rail">
      <div className="rail-head">
        <strong>Conferir antes de usar</strong>
        <span className="tag warn">${doc.pendencias.length} aberta(s)</span>
      </div>
      ${doc.pendencias.map((p, i) => html`
        <div className=${"flag" + (p.bloqueia ? " block" : "")} key=${i}>
          <p dangerouslySetInnerHTML=${{ __html: inline(p.texto) }} />
          <button className="btn mini pri" onClick=${() => aoResolver(p.linha)}>Resolvida</button>
        </div>`)}
    </aside>`;
}

function BarraPublicar({ doc, colecoes, aoPublicar }) {
  const [destino, setDestino] = useState("outline");
  const [colecao, setColecao] = useState(colecoes[0] ? colecoes[0].id : "");
  const [rascunho, setRascunho] = useState(true);
  const [estado, setEstado] = useState(null);   // {tipo, texto, onde}
  const [enviando, setEnviando] = useState(false);

  const bloqueado = doc.pendencias.some((p) => p.bloqueia);

  const publicar = async () => {
    setEnviando(true); setEstado(null);
    try {
      const r = await aoPublicar({ destino, colecao, rascunho });
      setEstado({ tipo: "ok", texto: rascunho ? "rascunho criado" : "publicado", onde: r.onde });
    } catch (e) {
      setEstado({ tipo: "stop", texto: e.message });
    } finally { setEnviando(false); }
  };

  return html`
    <div className="publishbar">
      <div className="linha">
        <select value=${destino} onChange=${(e) => setDestino(e.target.value)}>
          <option value="outline">Outline</option>
          <option value="obsidian">Obsidian</option>
        </select>
        ${destino === "outline" && html`
          <select value=${colecao} onChange=${(e) => setColecao(e.target.value)}>
            ${colecoes.length === 0 && html`<option value="">sem coleções — inicie com --outline</option>`}
            ${colecoes.map((c) => html`<option key=${c.id} value=${c.id}>${c.nome}</option>`)}
          </select>`}
        <label className="check">
          <input type="checkbox" checked=${rascunho} onChange=${(e) => setRascunho(e.target.checked)} />
          como rascunho
        </label>
      </div>

      <div className="linha">
        ${estado
          ? html`<span className=${"aviso " + estado.tipo}>${estado.texto}</span>`
          : html`<span className=${"aviso " + (bloqueado ? "stop" : "neutro")}>
              ${bloqueado ? "bloqueado por pendência de credencial"
                          : doc.interno ? "material interno" : "material de divulgação"}
            </span>`}
        <button className="btn pri" onClick=${publicar} disabled=${bloqueado || enviando}>
          ${enviando ? "publicando…" : "Publicar"}
        </button>
      </div>

      ${estado && estado.onde && html`
        <a className="link" href=${estado.onde} target="_blank" rel="noopener">${estado.onde}</a>`}
    </div>`;
}

function Revisar({ docs, colecoes, recarregar }) {
  const [arquivo, setArquivo] = useState(null);
  const [doc, setDoc] = useState(null);

  const abrir = useCallback(async (alvo) => {
    setArquivo(alvo);
    setDoc(await api(`/api/documento?arquivo=${encodeURIComponent(alvo)}`));
  }, []);

  // quando a lista muda e nada está aberto, abre o primeiro
  useEffect(() => {
    if (!arquivo && docs.length) abrir(docs[0].arquivo);
  }, [docs, arquivo, abrir]);

  const resolver = async (linha) => {
    await enviar("/api/resolver", { arquivo, linha });
    await abrir(arquivo);
    recarregar();
  };

  const publicar = async ({ destino, colecao, rascunho }) => {
    const r = await enviar("/api/publicar", { arquivo, destino, colecao, rascunho });
    recarregar();
    return r;
  };

  return html`
    <section id="revisar">
      <span className="pill quiet">Revisar e publicar</span>
      <h2>Publicar é o último passo, não o primeiro</h2>
      <p className="lede">O que sai da máquina é proposta. Enquanto houver
        pendência que bloqueia, o botão fica desabilitado — e quem recusa é o
        servidor, não esta página.</p>

      <div className="split">
        <div>
          <div className="linha" style=${{ marginBottom: "10px" }}>
            <button className="btn mini" onClick=${recarregar}>Recarregar</button>
            <span className="fine">${docs.length} documento(s)</span>
          </div>
          <div className="lista">
            ${docs.length === 0 && html`<p className="vazio">Nada gerado ainda.</p>`}
            ${docs.map((d) => html`
              <button key=${d.arquivo} className=${"item" + (d.arquivo === arquivo ? " on" : "")}
                      onClick=${() => abrir(d.arquivo)}>
                <strong>${d.titulo}</strong>
                <small>${d.artigo_de} · ${d.palavras} palavras</small>
                <${Etiqueta} doc=${d} />
              </button>`)}
          </div>
        </div>

        ${doc ? html`
          <div className="app">
            <div className="titlebar">
              <span className="lights"><i /><i /><i /></span>
              <span className="caminho">docly · revisão · ${arquivo}</span>
            </div>
            <div className="doc">
              <article className="corpo">
                <p className="titulo">${doc.titulo}</p>
                <p className="meta">${doc.corpo.split(/\s+/).length} palavras · ${doc.pendencias.length} pendência(s)</p>
                <div dangerouslySetInnerHTML=${{ __html: paraHtml(doc.corpo) }} />
              </article>
              <${Pendencias} doc=${doc} aoResolver=${resolver} />
            </div>
            <${BarraPublicar} doc=${doc} colecoes=${colecoes} aoPublicar=${publicar} />
          </div>`
        : html`<p className="vazio">Escolha um documento à esquerda.</p>`}
      </div>
    </section>`;
}

// --------------------------------------------------------------------------
// aplicação
// --------------------------------------------------------------------------

function App() {
  const [docs, setDocs] = useState([]);
  const [colecoes, setColecoes] = useState([]);

  const recarregar = useCallback(async () => {
    try { setDocs(await api("/api/documentos")); } catch { setDocs([]); }
  }, []);

  useEffect(() => {
    recarregar();
    api("/api/colecoes").then(setColecoes).catch(() => setColecoes([]));
  }, [recarregar]);

  return html`
    <${React.Fragment}>
      <${Nav} />
      <main className="wrap">
        <${Gerar} aoTerminar=${recarregar} />
        <${Revisar} docs=${docs} colecoes=${colecoes} recarregar=${recarregar} />
      </main>
    <//>`;
}

ReactDOM.createRoot(document.getElementById("raiz")).render(html`<${App} />`);
