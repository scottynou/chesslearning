import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Chess Learning",
  description: "Plan-first chess training with Stockfish and pedagogical explanations.",
  icons: {
    icon: "./favicon.svg",
    shortcut: "./favicon.svg",
    apple: "./favicon.svg"
  }
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
