import nextVitals from "eslint-config-next/core-web-vitals";

const config = [
  ...nextVitals,
  {
    rules: {
      "react-hooks/set-state-in-effect": "off"
    }
  },
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "next-env.d.ts",
      "vitest.config.ts"
    ]
  }
];

export default config;
