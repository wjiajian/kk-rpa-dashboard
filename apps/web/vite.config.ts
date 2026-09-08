import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: { proxy: { "/api": loadEnv(mode, process.cwd(), "RPA_").RPA_API_TARGET || "http://127.0.0.1:8088" } },
}));
