import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "YatraFlux AI",
  description: "Predictive Railway Intelligence & Delay Management Platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen font-sans text-slate-100 antialiased">
        {children}
      </body>
    </html>
  );
}
