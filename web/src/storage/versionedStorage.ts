type VersionedPayload<T extends object> = T & { v: number };

export function readVersionedStorage<T extends object>(
  key: string,
  version: number,
  defaults: T,
): T {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return defaults;
    const parsed = JSON.parse(raw) as Partial<VersionedPayload<T>> | null;
    if (!parsed || parsed.v !== version) return defaults;
    const { v: _version, ...payload } = parsed;
    return payload as T;
  } catch {
    return defaults;
  }
}

export function writeVersionedStorage<T extends object>(
  key: string,
  version: number,
  payload: T,
): void {
  try {
    window.localStorage.setItem(key, JSON.stringify({ v: version, ...payload }));
  } catch {
    // Storage can be unavailable in private windows or after site-data resets.
  }
}
