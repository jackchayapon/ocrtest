/** Browser-memory only. User data is deduplicated in flight, never retained. */
export class ReadCoordinator {
  private pending = new Map<string, Promise<unknown>>();
  private values = new Map<string, { expires: number; value: unknown }>();
  private fresh = new Set<string>();
  private generation = 0;
  private readonly catalogs = new Set(["/pipelines", "/pipelines/models", "/categories", "/document-types"]);

  constructor(private readonly ttl = 10_000, private readonly now = () => performance.now()) {}

  key(path: string): string {
    const url = new URL(path, "http://read-key.invalid");
    url.searchParams.sort();
    return `${url.pathname}${url.search}`;
  }

  async read<T>(path: string, load: (path: string) => Promise<T>, isolated = false): Promise<T> {
    const key = this.key(path);
    const route = key.split("?")[0];
    const safe = this.catalogs.has(route);
    let fetchPath = key;
    if (safe && this.fresh.has(route)) {
      const url = new URL(key, "http://read-key.invalid");
      url.searchParams.set("fresh", "true");
      fetchPath = `${url.pathname}${url.search}`;
    }
    if (isolated) return load(fetchPath); // An AbortSignal must never cancel another subscriber.
    const cached = this.values.get(key);
    if (safe && cached && cached.expires > this.now()) return structuredClone(cached.value) as T;
    let pending = this.pending.get(key) as Promise<T> | undefined;
    if (!pending) {
      const generation = this.generation;
      pending = load(fetchPath).then(value => {
        if (safe && generation === this.generation) {
          this.values.set(key, { expires: this.now() + this.ttl, value: structuredClone(value) });
        }
        return value;
      });
      this.pending.set(key, pending);
      const cleanup = () => { if (this.pending.get(key) === pending) this.pending.delete(key); };
      pending.then(cleanup, cleanup);
    }
    return structuredClone(await pending);
  }

  mutated(path: string): void {
    // Also detach in-flight user reads, so a post-write read cannot join an old GET.
    this.generation++;
    this.pending.clear();
    const route = path.split("?")[0];
    const affected = route.startsWith("/pipelines") ? ["/pipelines", "/pipelines/models"]
      : route.startsWith("/document-types") ? ["/document-types"] : [];
    for (const key of affected) {
      this.fresh.add(key); // Subsequent cache misses bypass other workers' stale catalogs.
      for (const cached of this.values.keys()) if (cached.split("?")[0] === key) this.values.delete(cached);
    }
  }
}
