/* O estado do documento aparece em forma além de número: quem varre a lista
 * precisa ver o que exige atenção sem ler. */
export default function Etiqueta({ doc }) {
  if (doc.bloqueado) return <span className="tag stop">bloqueado</span>;
  if (doc.pendencias) return <span className="tag warn">{doc.pendencias} pendência(s)</span>;
  return <span className="tag ok">pronto</span>;
}
