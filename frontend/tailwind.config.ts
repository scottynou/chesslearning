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
        void: "#0d1117",
        ink: "#202632",
        panel: "#fffaf0",
        line: "#ded8cc",
        cream: "#f4ecdc",
        gold: "#e7b96a",
        sage: "#728a68",
        clay: "#b96745",
        night: "#17202d"
      },
      boxShadow: {
        soft: "0 22px 70px rgba(13, 17, 23, 0.12)",
        strong: "0 34px 120px rgba(13, 17, 23, 0.22)"
      }
    }
  },
  plugins: []
};

export default config;
