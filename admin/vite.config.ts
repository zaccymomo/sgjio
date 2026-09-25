import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Requests to /api go to the FastAPI server, so the browser sees a single origin.
const apiProxy = { "/api": "http://localhost:8000" };

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5174, strictPort: true, proxy: apiProxy },
  preview: { port: 4174, strictPort: true, proxy: apiProxy },
});
