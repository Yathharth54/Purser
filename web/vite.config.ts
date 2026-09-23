import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api to the FastAPI backend on :8000. Target 127.0.0.1
// explicitly rather than "localhost" -- on this machine "localhost" can
// resolve to ::1 first and land on an unrelated service also bound to port
// 8000 on IPv6, while the Purser API listens on IPv4 127.0.0.1 only.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
