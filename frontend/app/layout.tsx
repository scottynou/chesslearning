import type { Metadata, Viewport } from "next";
import Script from "next/script";
import "./globals.css";

export const metadata: Metadata = {
  title: "Chess Elo Coach",
  description: "Coach d'echecs personnalise : profil ELO, style, accuracy meter, bilan post-partie.",
  applicationName: "Chess Elo Coach",
  manifest: "./manifest.webmanifest",
  icons: {
    icon: [
      { url: "./favicon.svg", type: "image/svg+xml" },
      { url: "./favicon-32x32.png", sizes: "32x32", type: "image/png" },
      { url: "./favicon.ico", sizes: "any" }
    ],
    shortcut: "./favicon.ico",
    apple: [{ url: "./apple-touch-icon.png", sizes: "180x180", type: "image/png" }]
  },
  appleWebApp: {
    capable: true,
    title: "Chess Coach",
    statusBarStyle: "black-translucent"
  }
};

export const viewport: Viewport = {
  themeColor: "#0f172a",
  width: "device-width",
  initialScale: 1
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>{children}</body>
      <Script id="register-sw" strategy="afterInteractive">
        {`if ('serviceWorker' in navigator) {
            window.addEventListener('load', function () {
              navigator.serviceWorker.register('/sw.js').catch(function (e) {
                console.warn('SW register failed', e);
              });
            });
          }`}
      </Script>
    </html>
  );
}
