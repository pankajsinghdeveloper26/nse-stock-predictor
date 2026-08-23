import { defineConfig } from "astro/config";
import tailwind from "@astrojs/tailwind";

// https://astro.build/config
export default defineConfig({
  integrations: [
    tailwind({
      applyBaseStyles: false,
    }),
  ],
  server: {
    port: 4321,
    host: true,
  },
  vite: {
    server: {
      proxy: {
        // Lets the frontend call "/api/..." and have Astro's dev server
        // forward it to FastAPI, sidestepping CORS entirely in dev.
        "/api": {
          target: process.env.PUBLIC_API_BASE_URL || "http://localhost:8000",
          changeOrigin: true,
        },
      },
    },
  },
});
