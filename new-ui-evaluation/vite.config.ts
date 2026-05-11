import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5174,
    proxy: {
      "/api": "http://127.0.0.1:8091",
      "/healthz": "http://127.0.0.1:8091"
    }
  },
  preview: {
    host: "127.0.0.1",
    port: 4174
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/__tests__/setup.ts"]
  }
});
