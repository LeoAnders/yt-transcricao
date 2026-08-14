export function Glifo() {
  return <span className="glyph" />;
}

export default function Nav() {
  return (
    <div className="navshell">
      <nav className="nav">
        <span className="logo">
          <Glifo />
          Docly
        </span>
        <span className="meio">
          <a href="#gerar">Gerar</a>
          <a href="#revisar">Revisar</a>
        </span>
        <span className="fine">console local · 127.0.0.1</span>
      </nav>
    </div>
  );
}
