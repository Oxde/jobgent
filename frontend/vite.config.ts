import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8781", "/packs": "http://127.0.0.1:8781" },
  },
  build: { outDir: "dist", emptyOutDir: true },
  test: { environment: "jsdom", globals: true },
});
