import { defineConfig } from "astro/config"
import react from "@astrojs/react"
import tailwindcss from "@tailwindcss/vite"

export default defineConfig({
  integrations: [react()],
  vite: {
    plugins: [tailwindcss()],
    server: {
      proxy: {
        // Lets the frontend call "/api/..." (see src/lib/api.ts) and have
        // Astro's dev server forward it to the FastAPI backend, sidestepping
        // CORS entirely in dev. Override the target with PUBLIC_API_BASE_URL
        // if the backend isn't on localhost:8000.
        "/api": {
          target: process.env.PUBLIC_API_BASE_URL || "http://localhost:8000",
          changeOrigin: true,
        },
      },
    },
  },
  server: {
    host: true,
    port: Number(process.env.DEV_PORT ?? 3000),
  },
})
