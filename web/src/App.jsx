import { useCallback, useEffect, useState } from "react";
import { listarColecoes, listarDocumentos } from "./api.js";
import Gerar from "./componentes/Gerar.jsx";
import Home from "./componentes/Home.jsx";
import Revisar from "./componentes/Revisar.jsx";
import Sidebar from "./componentes/Sidebar.jsx";

export default function App() {
  const [tela, setTela] = useState("home");
  const [docs, setDocs] = useState([]);
  const [colecoes, setColecoes] = useState([]);

  const recarregar = useCallback(async () => {
    try {
      setDocs(await listarDocumentos());
    } catch {
      setDocs([]);
    }
  }, []);

  useEffect(() => {
    recarregar();
    // sem --outline o servidor devolve lista vazia; a barra de publicar avisa
    listarColecoes().then(setColecoes).catch(() => setColecoes([]));
  }, [recarregar]);

  return (
    <>
      <Sidebar tela={tela} aoMudarTela={setTela} />
      <main className="shell">
        {tela === "home" && <Home docs={docs} aoMudarTela={setTela} />}
        {tela === "gerar" && <Gerar aoTerminar={recarregar} />}
        {tela === "documentos" && (
          <Revisar docs={docs} colecoes={colecoes} recarregar={recarregar} />
        )}
      </main>
    </>
  );
}
