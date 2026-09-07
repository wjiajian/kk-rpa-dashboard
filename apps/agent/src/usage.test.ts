import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtemp, mkdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import { SessionManager } from "@earendil-works/pi-coding-agent";
import type { AssistantMessage } from "@earendil-works/pi-ai";
import { restoreUsage, sessionUsage } from "./usage.js";

test("usage includes compacted history, cache and summary calls, and can restore old runs", async () => {
  const root = await mkdtemp(join(tmpdir(), "rpa-usage-"));
  const runId = randomUUID();
  const directory = join(root, runId);
  await mkdir(directory);
  try {
    const manager = SessionManager.create(directory, directory);
    const usage = { input: 10, output: 20, cacheRead: 30, cacheWrite: 0, totalTokens: 60,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } };
    const message: AssistantMessage = { role: "assistant", content: [], api: "openai-responses", provider: "fixture", model: "fixture",
      usage, stopReason: "stop", timestamp: 1 };
    const first = manager.appendMessage(message);
    manager.appendCompaction("summary", first, 100, undefined, false, usage);
    manager.appendMessage({ ...message, stopReason: "aborted", usage: { ...usage, input: 0, output: 0, cacheRead: 0, totalTokens: 0 } });
    const report = sessionUsage(manager);
    assert.equal(report.input, 20);
    assert.equal(report.output, 40);
    assert.equal(report.cache_read, 60);
    assert.equal(report.requests, 3);
    assert.equal(report.unreported_responses, 1);
    const restored: unknown[] = [];
    await restoreUsage(root, async (id, current) => { assert.equal(id, runId); restored.push(current); });
    assert.deepEqual(restored, [report]);
  } finally { await rm(root, { recursive: true, force: true }); }
});
