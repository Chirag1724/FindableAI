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
        background: "#090D16",
        surface: "#111827",
        surfaceLight: "#1F2937",
        border: "#374151",
        brandCyan: "#00F5FF",
        brandIndigo: "#6366F1",
        brandPurple: "#A855F7",
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "cyber-grid": "linear-gradient(to right, #1f293715 1px, transparent 1px), linear-gradient(to bottom, #1f293715 1px, transparent 1px)",
      },
    },
  },
  plugins: [],
};

export default config;
