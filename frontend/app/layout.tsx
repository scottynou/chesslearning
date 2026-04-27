import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Chess Learning",
  description: "Plan-first chess training with Stockfish and pedagogical explanations."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
