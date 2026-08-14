import { Fragment } from "react";

const NOMES = ["Descobrir", "Gerar", "Revisar", "Publicar"];

/* Os quatro passos são uma sequência de verdade — descobrir vem antes de
 * gerar, revisar antes de publicar —, então numerá-los diz algo sobre o
 * conteúdo em vez de só decorar. */
export default function Passos({ atual }) {
  return (
    <div className="steps">
      {NOMES.map((nome, i) => (
        <Fragment key={nome}>
          <span className={i === atual ? "on" : ""}>
            <b>{i + 1}</b> {nome}
          </span>
          {i < NOMES.length - 1 && <i>›</i>}
        </Fragment>
      ))}
    </div>
  );
}
