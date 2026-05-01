import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Chess Learning",
  description: "Fast chess move coach powered by Stockfish.",
  applicationName: "Chess Learning",
  manifest: "./site.webmanifest",
  icons: {
    icon: [
      { url: "./favicon.svg", type: "image/svg+xml" },
      { url: "./favicon-32x32.png", sizes: "32x32", type: "image/png" },
      { url: "./favicon.ico", sizes: "any" }
    ],
    shortcut: "./favicon.ico",
    apple: [{ url: "./apple-touch-icon.png", sizes: "180x180", type: "image/png" }]
  }
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
