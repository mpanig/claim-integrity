// Truth-area check: visits truth sheet list, editors, product pages and matrices, recording every
// console error, page error and failed request. Read-only (never saves).
// Usage: node e2e/truth-check.mjs [sku ids...]   (BASE_URL, BROWSER_CHANNEL as in verify.mjs)
import { chromium } from "playwright";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const ids = process.argv.slice(2).map(Number);
const skus = await (await fetch(`${BASE}/api/skus`)).json();
const pilot = skus.filter((s) => s.truth_status === "approved").map((s) => s.id);
const brands = await (await fetch(`${BASE}/api/brands`)).json();

const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || undefined });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const problems = [];
let current = "";
page.on("console", (m) => m.type() === "error" && problems.push(`${current}: console: ${m.text().slice(0, 300)}`));
page.on("pageerror", (e) => problems.push(`${current}: pageerror: ${e.message.slice(0, 300)}`));
page.on("response", (r) => r.status() >= 400 && problems.push(`${current}: HTTP ${r.status()} ${r.url().slice(0, 160)}`));

async function visit(path, check) {
  current = path;
  const res = await page.goto(`${BASE}${path}`, { timeout: 60_000 });
  if (!res || !res.ok()) problems.push(`${path}: HTTP ${res?.status()}`);
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => problems.push(`${path}: never idle`));
  const body = await page.locator("main").innerText().catch(() => "");
  if (/Something went wrong|Can't reach|Page not found|Application error|Unhandled/i.test(body)) problems.push(`${path}: error state shown: ${body.slice(0, 200)}`);
  if (check) await check(body);
  console.log(`ok  ${path}`);
}

await visit("/truth-sheets");
for (const b of brands) await visit(`/truth-sheets?brand=${b.id}`);
for (const id of [...pilot, ...ids]) {
  await visit(`/products/${id}`, async (body) => {
    const s = skus.find((x) => x.id === id);
    if (s?.truth_status === "inferred" && !/Add a truth sheet/.test(body)) problems.push(`/products/${id}: inferred but no "Add a truth sheet" panel`);
  });
  await visit(`/products/${id}/truth?prefill=inferred`, async () => {
    // Touch the form like a reviewer would: edit nothing, check the approve button state and the fields.
    const btn = page.getByRole("button", { name: /Approve truth sheet|Save truth sheet/ });
    if (!(await btn.count())) problems.push(`/products/${id}/truth: no save/approve button`);
    for (const f of ["ingredients", "free_from", "claims", "seals"]) {
      const v = await page.locator(`#${f}`).inputValue().catch(() => null);
      if (v === null) problems.push(`/products/${id}/truth: field ${f} missing`);
      else if (/\[object Object\]|undefined|NaN/.test(v)) problems.push(`/products/${id}/truth: field ${f} shows "${v.slice(0, 80)}"`);
    }
    const txt = await page.locator("main").innerText();
    const bad = txt.match(/(\d{3,})% of page weight|NaN%|undefined/g);
    if (bad) problems.push(`/products/${id}/truth: odd text ${bad.join(", ")}`);
  });
}
await browser.close();
console.log(problems.length ? `\n${problems.length} problems:\n${problems.join("\n")}` : "\nNo problems found.");
