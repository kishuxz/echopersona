/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base:        "#FAFAF9",
        bg:          "#FAFAF9",
        surface:     "#FFFFFF",
        elevated:    "#F5F5F4",
        cream:       "#F0EDE8",
        border:      "#E4E4E7",
        "border-hi": "#D4D4D8",
        accent:      "#18181B",
        green:       "#16A34A",
        blue:        "#2563EB",
        red:         "#DC2626",
        orange:      "#F97316",
        muted:       "#A1A1AA",
        text:        "#18181B",
        textdim:     "#52525B",
        textfaint:   "#A1A1AA",
        yellow:      "#D97706",
      },
      fontFamily: {
        fraunces: ["Fraunces", "Georgia", "serif"],
        "dm-sans": ["DM Sans", "system-ui", "sans-serif"],
        "dm-mono": ["DM Mono", "monospace"],
        mono: ["DM Mono", "monospace"],
        sans: ["DM Sans", "system-ui", "sans-serif"],
      },
      keyframes: {
        "ping-ring": {
          "0%":   { transform: "scale(1)", opacity: "0.5" },
          "100%": { transform: "scale(1.8)", opacity: "0" },
        },
        blink: {
          "0%, 100%": { opacity: "1" },
          "50%":      { opacity: "0" },
        },
        "wave-bar": {
          "0%, 100%": { transform: "scaleY(0.3)" },
          "50%":      { transform: "scaleY(1)" },
        },
        "avatar-idle": {
          "0%, 100%": { borderColor: "rgba(228,228,231,1)" },
          "50%":      { borderColor: "rgba(212,212,216,1)" },
        },
        "avatar-speaking": {
          "0%, 100%": { borderColor: "rgba(22,163,74,0.4)" },
          "50%":      { borderColor: "rgba(22,163,74,1)" },
        },
        "fade-in": {
          "0%":   { opacity: "0" },
          "100%": { opacity: "1" },
        },
      },
      animation: {
        "ping-ring":       "ping-ring 1.2s ease-out infinite",
        blink:             "blink 1s step-end infinite",
        "wave-bar":        "wave-bar 0.8s ease-in-out infinite",
        "avatar-idle":     "avatar-idle 3s ease-in-out infinite",
        "avatar-speaking": "avatar-speaking 0.9s ease-in-out infinite",
        "fade-in":         "fade-in 0.2s ease-out both",
      },
      boxShadow: {
        "card":      "0 1px 2px rgba(0,0,0,0.05)",
        "card-hover":"0 4px 12px rgba(0,0,0,0.08)",
        "panel":     "0 10px 25px rgba(0,0,0,0.08)",
      },
    },
  },
  plugins: [],
};
