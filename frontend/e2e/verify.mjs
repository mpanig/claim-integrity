// End-to-end check of every screen, plus screenshots for docs/screenshots.
//
// Needs the backend (seeded) and the frontend running. Then:
//   node e2e/verify.mjs
// Env: BASE_URL (default http://localhost:3000), OUT_DIR (default ../docs/screenshots),
//      BROWSER_CHANNEL (e.g. "chrome" or "msedge" to use an installed browser instead of
//      `npx playwright install chromium`).
// Exits 1 if any page fails to load, shows an error, or logs a console error.

import { mkdir } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const OUT = resolve(process.env.OUT_DIR ?? join(dirname(fileURLToPath(import.meta.url)), "../../docs/screenshots"));
await mkdir(OUT, { recursive: true });

const skus = await (await fetch(`${BASE}/api/skus`)).json();
const cerave = skus.find((s) => s.brand_name === "CeraVe");
const aveeno = skus.find((s) => s.brand_name === "Aveeno");
if (!cerave || !aveeno) throw new Error("Seed the pilot first: uv run python -m app.seed --demo-history");

const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || undefined });
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 2,
  colorScheme: "light",
});
const page = await context.newPage();
const problems = [];
let current = "";
page.on("console", (m) => m.type() === "error" && problems.push(`${current}: console error: ${m.text()}`));
page.on("pageerror", (e) => problems.push(`${current}: page error: ${e.message}`));

async function settle() {
  await page.waitForLoadState("networkidle");
  await page.waitForFunction(() => !document.querySelector('[aria-busy="true"]'), null, { timeout: 20_000 });
  await page.waitForTimeout(900); // let chart animations finish
}

async function visit(path, shot, { fullPage = true } = {}) {
  current = path;
  const res = await page.goto(`${BASE}${path}`);
  if (!res || !res.ok()) problems.push(`${path}: HTTP ${res?.status()}`);
  await settle();
  const body = await page.locator("main").innerText();
  if (/Something went wrong|Can't reach the Claim Integrity service|Page not found/.test(body))
    problems.push(`${path}: error state shown`);
  if (shot) await page.screenshot({ path: join(OUT, shot), fullPage });
  console.log(`ok  ${path}${shot ? `  -> ${shot}` : ""}`);
}

await visit("/", "01-overview.png");
await visit("/products", "02-products.png");
await visit(`/products/${aveeno.id}`, "03-product-matrix.png");

// Conflict detail, then Accept -> Mark fixed on CeraVe's outdated ingredient list.
await visit(`/products/${cerave.id}`);
current = "conflict panel";
await page.getByRole("button", { name: /Outdated info on retailer: open details/ }).click();
const panel = page.getByRole("dialog");
await panel.getByText("Approved by the brand").waitFor();
await settle();
await page.screenshot({ path: join(OUT, "04-conflict-detail.png") });
console.log("ok  conflict panel  -> 04-conflict-detail.png");

const accept = panel.getByRole("button", { name: "Accept (create fix task)" });
if (await accept.count()) {
  await accept.click();
  await panel.getByText("Accepted · to fix").first().waitFor();
  await panel.getByRole("button", { name: "Mark fixed" }).click();
  await panel.getByText("Fixed · awaiting check").first().waitFor();
  const conflictId = new URL(page.url()).searchParams.get("conflict");
  const after = await (await fetch(`${BASE}/api/conflicts/${conflictId}`)).json();
  if (after.status !== "fixed") problems.push(`accept -> fixed: status is ${after.status}`);
  else console.log(`ok  accept -> fixed on conflict ${conflictId}`);
} else {
  console.log("skip accept -> fixed: conflict already decided (reseed to rerun this step)");
}
await page.keyboard.press("Escape");

await visit("/board", "05-fix-board.png");
await visit("/conflicts", "06-conflicts.png");
await visit("/competitors", "07-competitors.png");
await visit("/aeo", "08-aeo-overview.png");
await visit("/aeo/answers?view=compare", "08b-ai-compare.png");
await visit("/aeo/prompts/plan");
current = "ai plan estimate";
await page.getByRole("button", { name: "Estimate" }).click();
await page.getByText(/answers in this plan/).waitFor();
await page.screenshot({ path: join(OUT, "08c-ai-plan.png"), fullPage: true });
console.log("ok  ai plan estimate  -> 08c-ai-plan.png");
await visit("/aeo/prompts");
await visit("/aeo/coverage", "08d-ai-coverage.png");
await visit("/aeo/citations", "08g-aeo-citations.png");
await visit("/aeo/content", "08e-aeo-content.png");
await visit("/aeo/crawlers", "08h-aeo-crawlers.png");
await visit("/audit"); // old route redirects
await visit("/recommendations", "09-recommendations.png");
await visit("/alerts", "10-alerts.png");
await visit("/reports", "11-reports.png");
await visit(`/products/${cerave.id}/truth`, "12-truth-sheet.png");
await visit("/settings", "13-settings.png");
await visit("/search?q=paraben", "14-search.png");
await visit("/truth-sheets");
await visit("/products/new");
await visit(`/?brand=${cerave.brand_id}&range=4w`);

// Dark mode and tablet width.
await page.emulateMedia({ colorScheme: "dark" });
await visit("/", "15-overview-dark.png");
await page.emulateMedia({ colorScheme: "light" });
await page.setViewportSize({ width: 820, height: 1180 });
await visit("/", "16-overview-tablet.png");
await visit(`/products/${aveeno.id}`);

await browser.close();
if (problems.length) {
  console.error(`\n${problems.length} problem(s):\n${problems.join("\n")}`);
  process.exit(1);
}
console.log(`\nAll screens loaded with no console errors. Screenshots in ${OUT}`);
