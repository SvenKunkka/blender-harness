import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The Blender Harness API server listens on 127.0.0.1:9876.
// /api and /media are proxied there so the SPA can use same-origin URLs.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:9876",
        changeOrigin: true,
      },
      "/media": {
        target: "http://127.0.0.1:9876",
        changeOrigin: true,
      },
    },
  },
});
