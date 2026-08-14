import { useState } from "react";

/* O botão desabilitado é cortesia com quem revisa, não a trava. A trava está
 * no publicar.py: interface se contorna, servidor não. Se esta barra deixar
 * passar, o servidor ainda recusa — e é o motivo dele que aparece aqui. */
export default function BarraPublicar({ doc, colecoes, aoPublicar }) {
  const [destino, setDestino] = useState("outline");
  const [colecao, setColecao] = useState(colecoes[0]?.id ?? "");
  const [rascunho, setRascunho] = useState(true);
  const [estado, setEstado] = useState(null);
  const [enviando, setEnviando] = useState(false);

  const bloqueado = doc.pendencias.some((p) => p.bloqueia);

  async function publicar() {
    setEnviando(true);
    setEstado(null);
    try {
      const r = await aoPublicar({ destino, colecao, rascunho });
      setEstado({
        tipo: "ok",
        texto: rascunho ? "rascunho criado" : "publicado",
        onde: r.onde,
      });
    } catch (e) {
      setEstado({ tipo: "stop", texto: e.message });
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="publishbar">
      <div className="linha">
        <select value={destino} onChange={(e) => setDestino(e.target.value)}>
          <option value="outline">Outline</option>
          <option value="obsidian">Obsidian</option>
        </select>

        {destino === "outline" && (
          <select value={colecao} onChange={(e) => setColecao(e.target.value)}>
            {colecoes.length === 0 && (
              <option value="">sem coleções — inicie com --outline</option>
            )}
            {colecoes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nome}
              </option>
            ))}
          </select>
        )}

        <label className="check">
          <input
            type="checkbox"
            checked={rascunho}
            onChange={(e) => setRascunho(e.target.checked)}
          />
          como rascunho
        </label>
      </div>

      <div className="linha">
        {estado ? (
          <span className={`aviso ${estado.tipo}`}>{estado.texto}</span>
        ) : (
          <span className={`aviso ${bloqueado ? "stop" : "neutro"}`}>
            {bloqueado
              ? "bloqueado por pendência de credencial"
              : doc.interno
                ? "material interno"
                : "material de divulgação"}
          </span>
        )}
        <button className="btn pri" onClick={publicar} disabled={bloqueado || enviando}>
          {enviando ? "publicando…" : "Publicar"}
        </button>
      </div>

      {estado?.onde && (
        <a className="link" href={estado.onde} target="_blank" rel="noopener noreferrer">
          {estado.onde}
        </a>
      )}
    </div>
  );
}
