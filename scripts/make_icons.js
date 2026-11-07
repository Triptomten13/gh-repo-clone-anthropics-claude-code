// Renders frontend/public/icons/icon.svg to the PNG sizes browsers and phones ask for (PWA, iOS home screen, favicon).
//   node scripts/make_icons.js        (needs Playwright's Chromium; re-run after changing icon.svg)
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const dir = path.join(__dirname, "..", "frontend", "public", "icons");
const svg = fs.readFileSync(path.join(dir, "icon.svg"), "utf8");
const sizes = { "icon-192.png": 192, "icon-512.png": 512, "maskable-512.png": 512, "apple-touch-icon.png": 180, "favicon-32.png": 32 };

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ deviceScaleFactor: 1 });
  for (const [name, px] of Object.entries(sizes)) {
    await page.setViewportSize({ width: px, height: px });
    await page.setContent(`<html><body style="margin:0;background:#0c0b11">${svg.replace("<svg ", `<svg width="${px}" height="${px}" `)}</body></html>`);
    await page.screenshot({ path: path.join(dir, name), clip: { x: 0, y: 0, width: px, height: px } });
    console.log(name, px);
  }
  await browser.close();
})();
