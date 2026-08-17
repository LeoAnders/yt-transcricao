import { useCallback, useEffect, useRef, useState } from "react";
import { analisar as pedirAnalise, gerar as pedirGeracao, verTrabalho } from "../api.js";
import Passos from "./Passos.jsx";

export default function Gerar({ aoTerminar }) {
  const [url, setUrl] = useState("");
  const [quadros, setQuadros] = useState(true);
  const [achado, setAchado] = useState(null);
  const [erro, setErro] = useState("");
  const [linhas, setLinhas] = useState([]);
  const [rodando, setRodando] = useState(false);
  const caixaDoLog = useRef(null);
  const timer = useRef(null);

  useEffect(() => {
    if (caixaDoLog.current) caixaDoLog.current.scrollTop = caixaDoLog.current.scrollHeight;
  }, [linhas]);

  // sem isto, sair da tela com a geração em curso deixa o intervalo rodando
  useEffect(() => () => clearInterval(timer.current), []);

  const analisar = useCallback(async () => {
    setErro("");
    setAchado(null);
    try {
      setAchado(await pedirAnalise(url.trim()));
    } catch (e) {
      setErro(e.message);
    }
  }, [url]);

  const gerar = useCallback(async () => {
    setErro("");
    setLinhas([]);
    setRodando(true);
    try {
      const { id } = await pedirGeracao(url.trim(), quadros);
      // A geração leva minutos e roda numa thread do servidor; a página
      // pergunta o estado em vez de segurar a requisição até o timeout.
      timer.current = setInterval(async () => {
        try {
          const t = await verTrabalho(id);
          setLinhas(t.linhas || []);
          if (t.estado === "pronto" || t.estado === "erro") {
            clearInterval(timer.current);
            setRodando(false);
            if (t.erro) setErro(t.erro);
            aoTerminar();
          }
        } catch (e) {
          clearInterval(timer.current);
          setRodando(false);
          setErro(e.message);
        }
      }, 1200);
    } catch (e) {
      setErro(e.message);
      setRodando(false);
    }
  }, [url, quadros, aoTerminar]);

  return (
    <div className="tela">
      <header className="tela-header">
        <span className="eyebrow">Novo documento</span>
        <h2>Cola o link. Antes de gastar, mostra o que tem.</h2>
        <p className="lede">
          A análise é de graça: acontece antes de baixar qualquer coisa. Saber que
          são dezenove vídeos e não três muda o plano.
        </p>
      </header>

      <div className="card">
        <Passos atual={achado || rodando ? 1 : 0} />

        <div className="linha">
          <input
            className="campo"
            type="text"
            value={url}
            placeholder="https://outline.interno/doc/artigo-XXXX"
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && analisar()}
          />
          <button className="btn" onClick={analisar} disabled={!url.trim() || rodando}>
            Analisar
          </button>
          <label className="check">
            <input
              type="checkbox"
              checked={quadros}
              onChange={(e) => setQuadros(e.target.checked)}
            />
            ler a tela dos vídeos sem fala
          </label>
          <button className="btn pri" onClick={gerar} disabled={!achado || rodando}>
            {rodando ? "gerando…" : "Gerar documentação →"}
          </button>
        </div>

        {achado && (
          <>
            <div className="counts">
              <div className="hl">
                <b>{achado.videos.length}</b>
                <span>vídeos encontrados</span>
              </div>
              <div>
                <b>{quadros ? "sim" : "não"}</b>
                <span>ler a tela dos sem fala</span>
              </div>
            </div>
            <p className="lede" style={{ margin: "14px 0 0", fontSize: "15px" }}>
              Artigo: <strong>{achado.titulo}</strong>
            </p>
          </>
        )}

        {erro && (
          <p className="aviso stop" style={{ marginTop: "14px" }}>
            {erro}
          </p>
        )}

        {linhas.length > 0 && (
          <div className="log" ref={caixaDoLog}>
            {linhas.join("\n")}
          </div>
        )}
      </div>
    </div>
  );
}
