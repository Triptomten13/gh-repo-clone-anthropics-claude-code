import type { Metadata, Viewport } from "next";
import "./globals.css";
import { PwaRegister } from "@/components/pwa";

export const metadata: Metadata = {
  title: `${process.env.NEXT_PUBLIC_COMPANY_NAME || "Demonkoncernen AB"} · Rocky Commerce Intelligence`,
  description: "Multi-agent market intelligence, opportunity discovery and commerce operations.",
  applicationName: "Demonkoncernen",
  icons: { icon: [{ url: "/icons/favicon-32.png", sizes: "32x32", type: "image/png" }, { url: "/icons/icon.svg", type: "image/svg+xml" }],
           apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180" }] },
  appleWebApp: { capable: true, title: "Demonkoncernen", statusBarStyle: "black-translucent" },
  formatDetection: { telephone: false },
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
      <body className="antialiased">{children}<PwaRegister /></body>
    </html>
  );
}
