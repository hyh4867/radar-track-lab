// Render the thumbnail still (2400x2400 PNG) and an 8 s seamless loop (1080x1080 MP4)
// from the web demo in headless Chrome. Needs: playwright-core (npm), Google Chrome, swiftc.
//
//   python3 -m http.server 8765 --bind 127.0.0.1 --directory web &
//   NODE_PATH=<dir with node_modules> node scripts/render_thumbnails.mjs <work_dir>
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(path.join(process.env.NODE_PATH || process.cwd(), "x.js"));
const { chromium } = require("playwright-core");
const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const work = path.resolve(process.argv[2] || "thumb_work");
const outDir = path.join(root, "results/thumbnails");
const base = process.env.DEMO_URL || "http://127.0.0.1:8765/";
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
fs.mkdirSync(work, { recursive: true });
fs.mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({ executablePath: CHROME, headless: true });

async function open(viewport, dpr, query) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: dpr });
  await page.goto(`${base}?thumb=1&${query}`);
  await page.waitForFunction(() => window.__ready === true, null, { timeout: 20000 });
  return page;
}
const grab = async (page) =>
  Buffer.from((await page.evaluate(() => document.getElementById("scope").toDataURL("image/png"))).split(",")[1], "base64");

// --- still: scenario "base", 2400 x 2400 ---------------------------------
const STILL_T = 150 * 4.8 / 2 + 1.25; // sim seconds after the slice start; beam at ~94 deg
{
  const page = await open({ width: 1200, height: 1200 }, 2, "scenario=base&labels=1&lite=0");
  await page.evaluate((t) => window.__renderAt(t), STILL_T);
  fs.writeFileSync(path.join(outDir, "scope_still_2400.png"), await grab(page));
  await page.close();
}

// --- loop: 8 s @ 30 fps = 240 frames covering exactly 4 revolutions (19.2 s sim) ----
// The last F frames cross-fade into the first ones so the clip loops without a jump.
const N = 240, F = 24, T = 4.8, REVS = 4, T0 = 30 * T;
const dt = (REVS * T) / N;
const frames = path.join(work, "frames");
fs.rmSync(frames, { recursive: true, force: true });
fs.mkdirSync(frames, { recursive: true });
{
  const page = await open({ width: 720, height: 720 }, 1.5, "scenario=base&labels=1&lite=0");
  for (let i = 0; i < N; i++) {
    let buf;
    if (i < N - F) {
      await page.evaluate((t) => window.__renderAt(t), T0 + (i + F) * dt);
      buf = await grab(page);
    } else {
      const j = i - (N - F), w = (j + 1) / F;
      await page.evaluate(({ ta, tb, w }) => {
        const c = document.getElementById("scope"), ctx = c.getContext("2d");
        window.__renderAt(ta);
        const off = document.createElement("canvas"); off.width = c.width; off.height = c.height;
        off.getContext("2d").drawImage(c, 0, 0);
        window.__renderAt(tb);
        ctx.globalAlpha = w; ctx.drawImage(off, 0, 0); ctx.globalAlpha = 1;
      }, { ta: T0 + j * dt, tb: T0 + (N + j) * dt, w });
      buf = await grab(page);
    }
    fs.writeFileSync(path.join(frames, `f${String(i).padStart(4, "0")}.png`), buf);
  }
  await page.close();
}
await browser.close();

const enc = path.join(work, "png2mp4");
execFileSync("swiftc", ["-O", path.join(here, "tools/png2mp4.swift"), "-o", enc], { stdio: "inherit" });
execFileSync(enc, [frames, path.join(outDir, "scope_loop_8s.mp4"), "30", "5000000"], { stdio: "inherit" });
console.log("done:", fs.readdirSync(outDir).join(", "));
