import { test, expect } from "@playwright/test";
import { ReadCoordinator } from "../lib/read-coordinator";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(r => { resolve = r; });
  return { promise, resolve };
}

test("concurrent identical GETs use a stable key and isolate returned objects", async () => {
  const reads = new ReadCoordinator();
  const d = deferred<{ value: number }>();
  let calls = 0;
  const load = () => { calls++; return d.promise; };
  const a = reads.read("/matrix?offset=0&limit=20", load);
  const b = reads.read("/matrix?limit=20&offset=0", load);
  d.resolve({ value: 1 });
  const [one, two] = await Promise.all([a, b]);
  expect(calls).toBe(1); one.value = 2; expect(two.value).toBe(1);
  await reads.read("/matrix?limit=20&offset=0", load);
  expect(calls).toBe(2); // Results/GT are never retained after completion.
});

test("catalog TTL and mutation invalidation enforce fresh reads across workers", async () => {
  let clock = 0;
  const reads = new ReadCoordinator(10, () => clock);
  const paths: string[] = [];
  const load = async (path: string) => { paths.push(path); return [paths.length]; };
  expect(await reads.read("/pipelines", load)).toEqual([1]);
  expect(await reads.read("/pipelines", load)).toEqual([1]);
  clock = 11;
  expect(await reads.read("/pipelines", load)).toEqual([2]);
  reads.mutated("/pipelines/id/definition");
  await reads.read("/pipelines", load);
  expect(paths.at(-1)).toBe("/pipelines?fresh=true");
  await reads.read("/pipelines/models", load);
  expect(paths.at(-1)).toBe("/pipelines/models?fresh=true");
  await reads.read("/pipelines", load, true);
  expect(paths.at(-1)).toBe("/pipelines?fresh=true");
});

test("mutation detaches obsolete GETs and prevents stale catalog repopulation", async () => {
  const reads = new ReadCoordinator();
  const d = deferred<number[]>();
  const old = reads.read("/pipelines", () => d.promise);
  reads.mutated("/pipelines");
  expect(await reads.read("/pipelines", async () => [2])).toEqual([2]);
  d.resolve([1]); await old;
  expect(await reads.read("/pipelines", async () => [3])).toEqual([2]);
});

test("failed GETs are retried and independent cancellation bypasses shared work", async () => {
  const reads = new ReadCoordinator();
  let calls = 0;
  const fail = async () => { calls++; throw new Error("synthetic"); };
  await expect(reads.read("/pipelines", fail)).rejects.toThrow("synthetic");
  await expect(reads.read("/pipelines", fail)).rejects.toThrow("synthetic");
  expect(calls).toBe(2);
  const d = deferred<number>();
  const a = reads.read("/history", () => d.promise);
  expect(await reads.read("/history", async () => 2, true)).toBe(2);
  d.resolve(1); expect(await a).toBe(1);
});
