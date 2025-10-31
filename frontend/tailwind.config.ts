import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#f97316",
          dark: "#ea580c",
        },
        accent: "#0ea5e9",
      },
    },
  },
  plugins: [],
};

export default config;
