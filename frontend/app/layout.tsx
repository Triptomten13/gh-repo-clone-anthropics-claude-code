import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: `${process.env.NEXT_PUBLIC_COMPANY_NAME || "Demonkoncernen AB"} · Rocky Commerce Intelligence`,
  description: "Multi-agent market intelligence, opportunity discovery and commerce operations.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover", // edge-to-edge on notched phones; the shell pads with env(safe-area-inset-*)
  themeColor: "#0c0b11",
  colorScheme: "dark",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
