import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Rocky · Commerce Intelligence HQ",
  description: "Multi-agent market intelligence, opportunity discovery and commerce operations.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
