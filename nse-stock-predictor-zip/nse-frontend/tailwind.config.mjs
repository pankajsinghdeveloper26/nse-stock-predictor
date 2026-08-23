/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./src/**/*.{astro,html,js,jsx,ts,tsx,md,mdx}"],
  theme: {
    extend: {
      colors: {
        void: "#0A0D12",
        "void-light": "#F5F3EC",
        panel: "#11151C",
        "panel-raised": "#161B24",
        "panel-light": "#FFFFFF",
        "panel-light-raised": "#F0EDE3",
        hair: "#232935",
        "hair-light": "#DDD8C8",
        ink: "#E7EAF0",
        "ink-muted": "#7C8699",
        "ink-light": "#1A1D23",
        "ink-light-muted": "#6B6455",
        bull: "#21D97A",
        bear: "#FF5C72",
        hold: "#F5B942",
        signal: "#5B8CFF",
      },
      fontFamily: {
        mono: ["'IBM Plex Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
        sans: ["'Inter'", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(91,140,255,0.25), 0 0 24px rgba(91,140,255,0.15)",
        "glow-bull": "0 0 0 1px rgba(33,217,122,0.3), 0 0 20px rgba(33,217,122,0.18)",
        "glow-bear": "0 0 0 1px rgba(255,92,114,0.3), 0 0 20px rgba(255,92,114,0.18)",
      },
      animation: {
        marquee: "marquee 38s linear infinite",
        "pulse-dot": "pulse-dot 1.8s ease-in-out infinite",
      },
      keyframes: {
        marquee: {
          "0%": { transform: "translateX(0%)" },
          "100%": { transform: "translateX(-50%)" },
        },
        "pulse-dot": {
          "0%, 100%": { opacity: 1, transform: "scale(1)" },
          "50%": { opacity: 0.4, transform: "scale(0.75)" },
        },
      },
    },
  },
  plugins: [],
};
