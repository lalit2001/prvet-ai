import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        panel: "var(--panel)",
        "panel-2": "var(--panel-2)",
        border: "var(--border)",
        "border-strong": "var(--border-strong)",
        "text-1": "var(--text)",
        "text-2": "var(--text-2)",
        "text-3": "var(--text-3)",
        accent: "var(--accent)",
      },
    },
  },
  plugins: [],
} satisfies Config;
