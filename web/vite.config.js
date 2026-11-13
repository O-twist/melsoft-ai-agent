import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the dashboard runs on :5173 and forwards API calls to the Python server on :8000.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  // The 3D viewer (<model-viewer> with three.js) is about 950 kB. It is its own chunk, loaded only when a
  // practical lesson is shown, so the dashboard itself stays small.
  build: { chunkSizeWarningLimit: 1000 },
});
