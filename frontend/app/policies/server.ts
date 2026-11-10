import { DEFAULT_API_BASE_URL } from "@homexo/shared";

// Only server pages import this helper; the browser always uses the public API base.
export async function initialPolicy<T>(path: string): Promise<T | null> {
  try {
    const base = process.env.API_INTERNAL_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_API_BASE_URL;
    const response = await fetch(`${base}/api/v1${path}`, { cache: "no-store", signal: AbortSignal.timeout(5000) });
    return response.ok ? await response.json() as T : null;
  } catch { return null; }
}
