/* Acesso ao console.py. Este arquivo não decide nada: quem recusa uma
 * publicação é o servidor, e o que chega aqui é só a resposta. */

export async function api(rota, opcoes) {
  const resposta = await fetch(rota, opcoes);
  const dados = await resposta.json();
  if (!resposta.ok) throw new Error(dados.erro || `falhou (${resposta.status})`);
  return dados;
}

export const enviar = (rota, corpo) =>
  api(rota, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corpo),
  });

export const listarDocumentos = () => api("/api/documentos");
export const listarColecoes = () => api("/api/colecoes");
export const lerDocumento = (arquivo) =>
  api(`/api/documento?arquivo=${encodeURIComponent(arquivo)}`);
export const verTrabalho = (id) => api(`/api/trabalho?id=${id}`);

export const analisar = (url) => enviar("/api/analisar", { url });
export const gerar = (url, quadros) => enviar("/api/gerar", { url, quadros });
export const resolver = (arquivo, linha) => enviar("/api/resolver", { arquivo, linha });
export const publicar = (corpo) => enviar("/api/publicar", corpo);
