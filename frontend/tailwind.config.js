/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg:      "#0a0a0a",
        surface: "#111111",
        border:  "#1e1e1e",
        green:   "#00ff88",
        blue:    "#00aaff",
        red:     "#ff4444",
        muted:   "#444444",
        text:    "#e0e0e0",
        textdim: "#888888",
        yellow:  "#ffaa00",
      },
      fontFamily: {
        mono: ["JetBrains Mono", "monospace"],
        sans: ["Inter", "sans-serif"],
      },
      keyframes: {
        "ping-ring": {
          "0%":   { transform: "scale(1)", opacity: "0.6" },
          "100%": { transform: "scale(1.8)", opacity: "0" },
        },
        blink: {
          "0%, 100%": { opacity: "1" },
          "50%":      { opacity: "0" },
        },
        scan: {
          "0%":   { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100%)" },
        },
      },
      animation: {
        "ping-ring": "ping-ring 1.2s ease-out infinite",
        blink:       "blink 1s step-end infinite",
        scan:        "scan 4s linear infinite",
      },
      boxShadow: {
        "glow-green": "0 0 20px rgba(0,255,136,0.25)",
        "glow-blue":  "0 0 20px rgba(0,170,255,0.25)",
      },
    },
  },
  plugins: [],
};
