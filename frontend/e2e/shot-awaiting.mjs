// One screenshot of the "key found, no real answers yet" state.
// Run only while an engine key is set and that engine has no real answers.
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const OUT = resolve(process.env.OUT_DIR ?? join(dirname(fileURLToPath(import.meta.url)), "../../docs/screenshots"));
const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || undefined });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, colorScheme: "light" });
await page.goto(`${BASE}/ai-visibility`);
await page.getByText(/The pilot plan for .* answers/).waitFor({ timeout: 60000 });
await page.screenshot({ path: join(OUT, "08f-ai-key-awaiting.png") });
await browser.close();
console.log("saved 08f-ai-key-awaiting.png");
