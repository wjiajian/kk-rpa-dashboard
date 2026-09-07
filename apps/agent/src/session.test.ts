import assert from "node:assert/strict";
import { test } from "node:test";
import { createServer } from "node:http";
import { once } from "node:events";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import { streamSimple } from "@earendil-works/pi-ai/api/openai-responses";
import { makeSession, promptRecovery } from "./session.js";
import { sessionUsage } from "./usage.js";

test("actual pi SDK uses economy parameters, continues truncation and stops immediately after handoff", async () => {
  const requests: Record<string, any>[] = [];
  const server = createServer(async (request, response) => {
    let body = "";
    for await (const chunk of request) body += chunk;
    requests.push(JSON.parse(body));
    response.writeHead(200, { "Content-Type": "text/event-stream" });
    let sequence = 0;
    const send = (type: string, event: Record<string, unknown>) => response.write(`event: ${type}\ndata: ${JSON.stringify({ type, sequence_number: sequence++, ...event })}\n\n`);
    send("response.created", { response: { id: `response-${requests.length}`, status: "in_progress" } });
    const output: unknown[] = [];
    if (requests.length <= 3 || requests.length === 5) {
      const names = requests.length === 1 ? ["context", "observe"] : requests.length === 5 ? ["resume"] : ["observe"];
      for (const [index, name] of names.entries()) {
        const args = name === "resume" ? JSON.stringify({ from_step: "S006", summary: "已准备页面，提交续跑待原校验。" }) : "{}";
        const item = { type: "function_call", id: `fc_${name}_${requests.length}`, call_id: `call_${name}_${requests.length}`, name, arguments: args, status: "completed" };
        send("response.output_item.added", { output_index: index, item: { ...item, status: "in_progress", arguments: "" } });
        send("response.function_call_arguments.delta", { item_id: item.id, output_index: index, delta: args });
        send("response.output_item.done", { output_index: index, item });
        output.push(item);
      }
    } else {
      const part = { type: "output_text", text: "已读取现场截图。", annotations: [] };
      const item = { type: "message", id: "msg_result", role: "assistant", content: [part], status: "completed" };
      send("response.output_item.added", { output_index: 0, item: { ...item, content: [], status: "in_progress" } });
      send("response.content_part.added", { output_index: 0, item_id: item.id, content_index: 0, part: { ...part, text: "" } });
      send("response.output_text.delta", { output_index: 0, item_id: item.id, content_index: 0, delta: part.text });
      send("response.output_item.done", { output_index: 0, item });
      output.push(item);
    }
    const truncated = requests.length === 4;
    send(truncated ? "response.incomplete" : "response.completed", { response: { id: `response-${requests.length}`, status: truncated ? "incomplete" : "completed", output,
      ...(truncated ? { incomplete_details: { reason: "max_output_tokens" } } : {}),
      usage: { input_tokens: 10, output_tokens: 10, total_tokens: 20 } } });
    response.end();
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const port = (server.address() as { port: number }).port;
  const root = await mkdtemp(join(tmpdir(), "rpa-session-test-"));
  const id = randomUUID();
  const calls: string[] = [];
  let observations = 0;
  const invoke = async (_id: string, action: string) => {
    calls.push(action);
    return { status: "succeeded", result: action === "observe" ? { image: { mimeType: "image/png", data: "c2NyZWVuc2hvdA==" },
      url: "https://business.test", text: `observation-${++observations}`, nodes: [{ target: "button", tag: "button", locator: "xpath:/html/body/button" }] } : { source: { account_id: "original" } } };
  };
  const active = await makeSession(id, root, "offline-test-key", invoke);
  const { session } = active;
  session.agent.streamFunction = (model, context, options) => streamSimple({ ...model, api: "openai-responses", baseUrl: `http://127.0.0.1:${port}` }, context, { ...options, apiKey: "offline-test-key" });
  try {
    await promptRecovery(active, "读取上下文并观察当前页面。", new AbortController().signal);
    assert.deepEqual(calls, ["context", "observe", "observe", "observe", "resume"]);
    assert.equal(active.gate.finished, true);
    assert.equal(requests.length, 5);
    assert.ok(requests.every(request => request.reasoning.effort === "none" && request.max_output_tokens === 4096));
    const latestInput = JSON.stringify(requests[4].input);
    assert.ok(latestInput.includes("上一条模型响应达到输出上限"));
    assert.ok(!latestInput.includes("observation-1") && latestInput.includes("observation-2") && latestInput.includes("observation-3"));
    assert.equal(latestInput.match(/"type":"input_image"/g)?.length, 1);
    assert.ok(!latestInput.includes("xpath:/html/body/button"));
    assert.equal(sessionUsage(session.sessionManager).input, 50);
    assert.equal(sessionUsage(session.sessionManager).output, 50);
    assert.equal(requests[0].store, false);
    assert.equal(requests[1].previous_response_id, undefined);
    assert.ok(requests[1].input.some((item: any) => item.type === "function_call_output" && Array.isArray(item.output) && item.output.some((part: any) => part.type === "input_image")));
    assert.deepEqual(requests[0].tools.map((tool: any) => tool.name).sort(), ["act", "context", "credential", "give_up", "observe", "resume"]);
    const persistedMessages = session.sessionManager.getEntries().filter(entry => entry.type === "message").map(entry => entry.id);
    session.setThinkingLevel("low");
    session.dispose();
    const restored = await makeSession(id, root, "offline-test-key", invoke);
    assert.equal(restored.session.thinkingLevel, "off");
    assert.deepEqual(restored.session.sessionManager.getEntries().filter(entry => entry.type === "message").map(entry => entry.id), persistedMessages);
    assert.equal(sessionUsage(restored.session.sessionManager).input, 50);
    restored.session.dispose();
  } finally {
    session.dispose();
    server.closeAllConnections();
    await new Promise<void>(resolve => server.close(() => resolve()));
    await rm(root, { recursive: true, force: true });
  }
});
