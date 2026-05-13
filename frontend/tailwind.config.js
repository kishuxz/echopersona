/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base:        "#080808",
        bg:          "#0a0a0a",
        surface:     "#111111",
        elevated:    "#1a1a1a",
        border:      "#222222",
        "border-hi": "#333333",
        green:       "#00ff88",
        blue:        "#0088ff",
        red:         "#ff4444",
        orange:      "#ff6b35",
        muted:       "#444444",
        text:        "#f0f0f0",
        textdim:     "#888888",
        textfaint:   "#333333",
        yellow:      "#ffaa00",
      },
      fontFamily: {
        mono: ["JetBrains Mono", "IBM Plex Mono", "monospace"],
        sans: ["Inter", "system-ui", "sans-serif"],
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
        "wave-bar": {
          "0%, 100%": { transform: "scaleY(0.3)" },
          "50%":      { transform: "scaleY(1)" },
        },
        "avatar-idle": {
          "0%, 100%": { boxShadow: "0 0 0 2px rgba(255,255,255,0.05)" },
          "50%":      { boxShadow: "0 0 0 2px rgba(255,255,255,0.1), 0 0 20px rgba(0,255,136,0.06)" },
        },
        "avatar-speaking": {
          "0%, 100%": { boxShadow: "0 0 0 3px rgba(0,255,136,0.5), 0 0 20px rgba(0,255,136,0.2)" },
          "50%":      { boxShadow: "0 0 0 3px rgba(0,255,136,0.9), 0 0 40px rgba(0,255,136,0.4)" },
        },
        "fade-in-up": {
          "0%":   { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "ping-ring":       "ping-ring 1.2s ease-out infinite",
        blink:             "blink 1s step-end infinite",
        scan:              "scan 4s linear infinite",
        "wave-bar":        "wave-bar 0.8s ease-in-out infinite",
        "avatar-idle":     "avatar-idle 3s ease-in-out infinite",
        "avatar-speaking": "avatar-speaking 0.9s ease-in-out infinite",
        "fade-in-up":      "fade-in-up 0.4s ease-out both",
      },
      boxShadow: {
        "glow-green": "0 0 20px rgba(0,255,136,0.25)",
        "glow-blue":  "0 0 20px rgba(0,136,255,0.25)",
        "glow-sm":    "0 0 12px rgba(0,255,136,0.15)",
        "card-hover": "0 8px 32px rgba(0,0,0,0.6), 0 0 0 1px rgba(0,255,136,0.12)",
      },
    },
  },
  plugins: [],
};
