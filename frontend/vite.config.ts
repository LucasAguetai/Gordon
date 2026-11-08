import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// L'API est proxifiée plutôt qu'appelée en cross-origin. Deux bénéfices :
// le cookie de session devient first-party (pas de souci de SameSite), et
// l'origine WebAuthn est la même que celle de la page — ce que la spécification
// exige de toute façon.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8787",
        changeOrigin: false,
        // Indispensable : sans ça le proxy met le flux SSE en tampon et la
        // réponse de l'agent arrive d'un seul bloc à la fin.
        configure: (proxy) => {
          proxy.on("proxyRes", (proxyRes) => {
            proxyRes.headers["cache-control"] = "no-cache, no-transform";
          });
        },
      },
    },
  },
});
