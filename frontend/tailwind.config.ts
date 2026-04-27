import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  theme: {
    extend: {
      colors: {
        ink: "#161616",
        panel: "#ffffff",
        line: "#ded8cc",
        sage: "#7c9173",
        clay: "#b96745",
        night: "#27313f"
      },
      boxShadow: {
        soft: "0 18px 60px rgba(22, 22, 22, 0.10)"
      }
    }
  },
  plugins: []
};

export default config;
