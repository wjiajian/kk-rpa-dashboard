import assert from "node:assert/strict";
import { test } from "node:test";
import { promptRecovery, type makeSession } from "./session.js";

test("output limit continues the same takeover until handoff, without executing partial calls", async () => {
  const prompts: string[] = [];
  const gate = { finished: false };
  const messages: unknown[] = [];
  const active = { gate, session: { sessionManager: { getEntries: () => messages.map(message => ({ type: "message", message })) }, prompt: async (prompt: string) => {
    prompts.push(prompt);
    if (prompts.length === 1) messages.push({ role: "assistant", stopReason: "length", content: [] });
    else gate.finished = true;
  } } } as unknown as Awaited<ReturnType<typeof makeSession>>;
  await promptRecovery(active, "第 2 轮", new AbortController().signal);
  assert.equal(prompts.length, 2);
  assert.ok(prompts[1].includes("不要重发已执行操作"));
  assert.ok(gate.finished);
});

test("cancellation and ordinary model failures do not trigger another prompt", async () => {
  for (const reason of ["stop", "error", "aborted", "length"]) {
    const abort = new AbortController();
    let calls = 0;
    const active = { gate: { finished: false }, session: {
      sessionManager: { getEntries: () => [{ type: "message", message: { role: "assistant", stopReason: reason } }] },
      prompt: async () => { calls++; if (reason === "length") abort.abort(); },
    } } as unknown as Awaited<ReturnType<typeof makeSession>>;
    await promptRecovery(active, "处理现场", abort.signal);
    assert.equal(calls, 1);
  }
});

test("three consecutive truncated responses terminate with a specific reason", async () => {
  let calls = 0;
  const active = { gate: { finished: false }, session: {
    sessionManager: { getEntries: () => [{ type: "message", message: { role: "assistant", stopReason: "length" } }] },
    prompt: async () => { calls++; },
  } } as unknown as Awaited<ReturnType<typeof makeSession>>;
  await assert.rejects(promptRecovery(active, "处理现场", new AbortController().signal), /repeated_response_truncation/);
  assert.equal(calls, 3);
});
