/* As estatísticas vêm do /api/documentos que a App já carregou — nenhuma
 * chamada nova só para a Home existir. */
export default function Home({ docs, aoMudarTela }) {
  const total = docs.length;
  const bloqueados = docs.filter((d) => d.bloqueado).length;
  const pendentes = docs.filter((d) => !d.bloqueado && d.pendencias > 0).length;
  const prontos = total - bloqueados - pendentes;

  return (
    <div className="tela">
      <header className="tela-header">
        <span className="eyebrow">Docly</span>
        <h1>Bem-vindo. O que vamos transformar hoje?</h1>
        <p className="lede">
          Cola um link de artigo, deixa a IA assistir os vídeos e revisa o que
          sai antes de publicar.
        </p>
      </header>

      <div className="action-cards">
        <button className="card-action" onClick={() => aoMudarTela("gerar")}>
          <h3>Gerar novo documento</h3>
          <p>Cola o link de um artigo com vídeos e imagens; a análise mostra o que tem antes de gastar.</p>
          <span className="seta">Começar →</span>
        </button>

        <button className="card-action" onClick={() => aoMudarTela("documentos")}>
          <h3>Ver documentos</h3>
          <p>Revisa o que já foi gerado, resolve pendências e publica no Outline ou Obsidian.</p>
          <span className="seta">Abrir →</span>
        </button>
      </div>

      <div className="stats">
        <div>
          <b>{total}</b>
          <span>documento(s) gerado(s)</span>
        </div>
        <div className="ok">
          <b>{prontos}</b>
          <span>pronto(s) para publicar</span>
        </div>
        <div className="warn">
          <b>{pendentes}</b>
          <span>com pendência</span>
        </div>
        <div className="stop">
          <b>{bloqueados}</b>
          <span>bloqueado(s) por credencial</span>
        </div>
      </div>
    </div>
  );
}
