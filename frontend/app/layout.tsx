import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Chess Elo Coach",
  description: "Mobile-first chess training with Stockfish and pedagogical explanations."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
