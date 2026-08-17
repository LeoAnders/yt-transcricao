const ICONES = {
  home: (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M4 11.5 12 4l8 7.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6 10v9h5v-6h2v6h5v-9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  gerar: (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="12" r="8.2" />
      <path d="M12 8.4v7.2M8.4 12h7.2" strokeLinecap="round" />
    </svg>
  ),
  documentos: (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M7 3.5h7l4 4V20a.5.5 0 0 1-.5.5h-11A.5.5 0 0 1 6 20V4a.5.5 0 0 1 .5-.5Z" strokeLinejoin="round" />
      <path d="M9 12h6M9 15.5h6" strokeLinecap="round" />
    </svg>
  ),
};

const ITENS = [
  { id: "home", nome: "Home" },
  { id: "gerar", nome: "Gerar" },
  { id: "documentos", nome: "Documentos" },
];

/* O glifo é o único elemento decorativo da marca: um play-button numa
 * moldura, porque o conteúdo que ele carrega vem de vídeo. */
export function Glifo() {
  return <span className="glyph" />;
}

export default function Sidebar({ tela, aoMudarTela }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <Glifo />
        Docly
      </div>

      <nav className="sidebar-nav">
        {ITENS.map((item) => (
          <button
            key={item.id}
            className={item.id === tela ? "nav-item on" : "nav-item"}
            onClick={() => aoMudarTela(item.id)}
          >
            {ICONES[item.id]}
            {item.nome}
          </button>
        ))}
      </nav>

      <div className="sidebar-foot">console local · 127.0.0.1</div>
    </aside>
  );
}
