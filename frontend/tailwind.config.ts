import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Base surfaces
        background: "#0A0A0A",
        surface: "#141414",
        "surface-secondary": "#191919",
        // Primary text
        "text-primary": "#EDEDED",
        "text-muted": "#A1A1A1",
        // Status semantic colors (named for meaning, not decoration)
        supported: {
          DEFAULT: "#10b981", // emerald-500
          subtle: "#022c22",  // emerald-950
        },
        partial: {
          DEFAULT: "#0ea5e9", // sky-500
          subtle: "#082f49",  // sky-950
        },
        contradicted: {
          DEFAULT: "#f43f5e", // rose-500
          subtle: "#4c0519",  // rose-950
        },
        unknown: {
          DEFAULT: "#f59e0b", // amber-500
          subtle: "#451a03",  // amber-950
        },
        // Score / primary accent
        accent: {
          DEFAULT: "#7c3aed", // violet-700
          light: "#a78bfa",   // violet-400
          subtle: "#2e1065",  // violet-950
        },
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "-apple-system", '"Segoe UI"', "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", '"SF Mono"', "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;