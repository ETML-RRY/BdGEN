/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

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
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.js"],
    include: ["src/**/*.{test,spec}.{js,jsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html", "lcov"],
      exclude: [
        "**/*.config.js",
        "**/*.{test,spec}.{js,jsx}",
        "src/test/**",
        "src/main.jsx",
        "**/dist/**",
      ],
    },
  },
});
