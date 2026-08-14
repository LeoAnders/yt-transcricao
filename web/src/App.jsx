import { useCallback, useEffect, useState } from "react";
import { listarColecoes, listarDocumentos } from "./api.js";
import Gerar from "./componentes/Gerar.jsx";
import Nav from "./componentes/Nav.jsx";
import Revisar from "./componentes/Revisar.jsx";

export default function App() {
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
      <Nav />
      <main className="wrap">
        <Gerar aoTerminar={recarregar} />
        <Revisar docs={docs} colecoes={colecoes} recarregar={recarregar} />
      </main>
    </>
  );
}
