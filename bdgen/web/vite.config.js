import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    // Built assets land in bdgen/server/static so `python -m bdgen.server`
    // serves the frontend out of the box.
    outDir: path.resolve(__dirname, "..", "bdgen", "server", "static"),
    emptyOutDir: true,
  },
});
