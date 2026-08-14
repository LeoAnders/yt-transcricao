import { inline } from "../markdown.js";

/* A pendência que bloqueia não é uma dúvida entre outras: ela ganha borda
 * própria, porque quem revisa precisa vê-la antes de decidir qualquer coisa. */
export default function Pendencias({ doc, aoResolver }) {
  if (!doc.pendencias.length) {
    return (
      <aside className="rail">
        <div className="rail-head">
          <strong>Conferir antes de usar</strong>
          <span className="tag ok">nenhuma</span>
        </div>
        <p className="vazio">Nada pendente. O documento está pronto para publicar.</p>
      </aside>
    );
  }

  return (
    <aside className="rail">
      <div className="rail-head">
        <strong>Conferir antes de usar</strong>
        <span className="tag warn">{doc.pendencias.length} aberta(s)</span>
      </div>

      {doc.pendencias.map((p, i) => (
        <div className={p.bloqueia ? "flag block" : "flag"} key={i}>
          <p dangerouslySetInnerHTML={{ __html: inline(p.texto) }} />
          <button className="btn mini pri" onClick={() => aoResolver(p.linha)}>
            Resolvida
          </button>
        </div>
      ))}
    </aside>
  );
}
