import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// In development, /api calls go to the FastAPI server on port 8000.
// For a deployed build, set VITE_API_URL to the API's public address.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000", "/docs": "http://127.0.0.1:8000", "/openapi.json": "http://127.0.0.1:8000" },
    // Polling makes hot reload reliable in synced folders (OneDrive/Dropbox) where file events get missed.
    watch: { usePolling: true, interval: 200 },
  },
});
