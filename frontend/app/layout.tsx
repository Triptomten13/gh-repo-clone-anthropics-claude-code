import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: `${process.env.NEXT_PUBLIC_COMPANY_NAME || "Demonkoncernen AB"} · Rocky Commerce Intelligence`,
  description: "Multi-agent market intelligence, opportunity discovery and commerce operations.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
