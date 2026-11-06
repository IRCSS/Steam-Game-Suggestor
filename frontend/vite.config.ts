/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The UI talks to the local FastAPI backend through a same-origin /api proxy in development.
const apiTarget = process.env.STEAM_STUDY_API_URL ?? "http://127.0.0.1:8765";
const port = Number(process.env.STEAM_STUDY_UI_PORT ?? 5173);

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port,
    strictPort: true,
    proxy: { "/api": { target: apiTarget, changeOrigin: false } },
  },
  preview: {
    host: "127.0.0.1",
    port,
    strictPort: true,
    proxy: { "/api": { target: apiTarget, changeOrigin: false } },
  },
  build: { sourcemap: true },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/tests/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
