import type { MetadataRoute } from "next";

// Installable app (Windows/macOS/Linux via Chrome/Edge, Android, iOS "Add to Home Screen"). Served at /manifest.webmanifest.
export default function manifest(): MetadataRoute.Manifest {
  const name = process.env.NEXT_PUBLIC_COMPANY_NAME || "G-SUS & Demonkoncernen AB";
  return {
    id: "/",
    name,
    short_name: "Demonkoncernen",
    description: "G-SUS intelligence, DAEMON CORE, agents and the Archive — the Demonkoncernen AB command center.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "any",
    background_color: "#0c0b11",
    theme_color: "#0c0b11",
    categories: ["business", "productivity"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
      { src: "/icons/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
    ],
    shortcuts: [
      { name: "G-sus Chamber", url: "/chamber", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
      { name: "Control Center", url: "/control", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
      { name: "The Archive", url: "/knowledge", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
    ],
  };
}
