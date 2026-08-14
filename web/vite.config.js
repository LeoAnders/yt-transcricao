import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// O Python continua sendo o servidor de verdade: ele fala com o Outline, roda
// o `claude` e — o que importa — é quem recusa uma publicação. O Vite só serve
// a interface.
//
// Em desenvolvimento (`npm run dev`) a página roda em 5173 e as chamadas /api
// são encaminhadas para o console.py em 8765. Em produção (`npm run build`) a
// saída vai para `dist/`, que o próprio console.py serve — aí é uma origem só
// e não há proxy nenhum no caminho.
const API = "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // 127.0.0.1, nunca 0.0.0.0: sem autenticação, escutar na rede exporia
    // conteúdo interno para qualquer máquina do escritório.
    host: "127.0.0.1",
    proxy: {
      "/api": { target: API, changeOrigin: false },
      "/midia": { target: API, changeOrigin: false },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
