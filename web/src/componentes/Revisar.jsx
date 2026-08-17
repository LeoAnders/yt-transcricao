import { useCallback, useEffect, useState } from "react";
import { lerDocumento, publicar as pedirPublicacao, resolver as pedirResolucao } from "../api.js";
import { paraHtml } from "../markdown.js";
import BarraPublicar from "./BarraPublicar.jsx";
import Etiqueta from "./Etiqueta.jsx";
import Pendencias from "./Pendencias.jsx";

export default function Revisar({ docs, colecoes, recarregar }) {
  const [arquivo, setArquivo] = useState(null);
  const [doc, setDoc] = useState(null);
  const [erro, setErro] = useState("");

  const abrir = useCallback(async (alvo) => {
    setErro("");
    setArquivo(alvo);
    try {
      setDoc(await lerDocumento(alvo));
    } catch (e) {
      setErro(e.message);
      setDoc(null);
    }
  }, []);

  // com a lista carregada e nada aberto, abre o primeiro
  useEffect(() => {
    if (!arquivo && docs.length) abrir(docs[0].arquivo);
  }, [docs, arquivo, abrir]);

  async function resolver(linha) {
    await pedirResolucao(arquivo, linha);
    await abrir(arquivo);
    recarregar();
  }

  async function publicar(corpo) {
    const r = await pedirPublicacao({ arquivo, ...corpo });
    recarregar();
    return r;
  }

  return (
    <div className="tela largo">
      <header className="tela-header">
        <span className="eyebrow">Revisar e publicar</span>
        <h2>Publicar é o último passo, não o primeiro</h2>
        <p className="lede">
          O que sai da máquina é proposta. Enquanto houver pendência que bloqueia,
          o botão fica desabilitado — e quem recusa é o servidor, não esta página.
        </p>
      </header>

      <div className="split">
        <div>
          <div className="linha" style={{ marginBottom: "10px" }}>
            <button className="btn mini" onClick={recarregar}>
              Recarregar
            </button>
            <span className="fine">{docs.length} documento(s)</span>
          </div>

          <div className="lista">
            {docs.length === 0 && <p className="vazio">Nada gerado ainda.</p>}
            {docs.map((d) => (
              <button
                key={d.arquivo}
                className={d.arquivo === arquivo ? "item on" : "item"}
                onClick={() => abrir(d.arquivo)}
              >
                <strong>{d.titulo}</strong>
                <small>
                  {d.artigo_de} · {d.palavras} palavras
                </small>
                <Etiqueta doc={d} />
              </button>
            ))}
          </div>
        </div>

        {erro && <p className="aviso stop">{erro}</p>}

        {doc ? (
          <div className="card doc-card">
            <div className="doc">
              <article className="corpo">
                <p className="titulo">{doc.titulo}</p>
                <p className="meta">
                  {doc.corpo.split(/\s+/).length} palavras · {doc.pendencias.length} pendência(s)
                </p>
                <div dangerouslySetInnerHTML={{ __html: paraHtml(doc.corpo) }} />
              </article>

              <Pendencias doc={doc} aoResolver={resolver} />
            </div>

            <BarraPublicar doc={doc} colecoes={colecoes} aoPublicar={publicar} />
          </div>
        ) : (
          !erro && <p className="vazio">Escolha um documento à esquerda.</p>
        )}
      </div>
    </div>
  );
}
