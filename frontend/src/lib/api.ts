/** Backend access. Server components use `serverGet` (direct to FastAPI);
 * client components use `api` (same-origin /api, rewritten by next.config.ts). */

type Params = Record<string, string | number | boolean | null | undefined | (string | number)[]>;

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export function qs(params?: Params): string {
  if (!params) return "";
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => sp.append(key, String(v)));
    else sp.set(key, String(value));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

async function parse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = res.statusText || `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      // keep statusText
    }
    throw new ApiError(res.status, message);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function serverGet<T>(path: string, params?: Params): Promise<T> {
  const base = process.env.API_URL ?? "http://127.0.0.1:8000";
  const res = await fetch(`${base}${path}${qs(params)}`, { cache: "no-store" });
  return parse<T>(res);
}

export async function api<T>(
  path: string,
  opts: { method?: string; body?: unknown; params?: Params } = {},
): Promise<T> {
  const res = await fetch(`/api${path}${qs(opts.params)}`, {
    method: opts.method ?? "GET",
    headers: opts.body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  return parse<T>(res);
}
