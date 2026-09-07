import assert from "node:assert/strict";
import { test } from "node:test";
import { createServer } from "node:http";
import { once } from "node:events";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import { streamSimple } from "@earendil-works/pi-ai/api/openai-responses";
import { makeSession } from "./session.js";

test("actual pi SDK streams tools, sends screenshot on next request and restores the run session", async () => {
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
    if (requests.length === 1) {
      for (const [index, name] of ["context", "observe"].entries()) {
        const item = { type: "function_call", id: `fc_${name}`, call_id: `call_${name}`, name, arguments: "{}", status: "completed" };
        send("response.output_item.added", { output_index: index, item: { ...item, status: "in_progress", arguments: "" } });
        send("response.function_call_arguments.delta", { item_id: item.id, output_index: index, delta: "{}" });
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
    send("response.completed", { response: { id: `response-${requests.length}`, status: "completed", output,
      usage: { input_tokens: 10, output_tokens: 10, total_tokens: 20 } } });
    response.end();
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const port = (server.address() as { port: number }).port;
  const root = await mkdtemp(join(tmpdir(), "rpa-session-test-"));
  const id = randomUUID();
  const calls: string[] = [];
  const invoke = async (_id: string, action: string) => {
    calls.push(action);
    return { status: "succeeded", result: action === "observe" ? { image: { mimeType: "image/png", data: "c2NyZWVuc2hvdA==" }, url: "https://business.test" } : { source: { account_id: "original" } } };
  };
  const { session } = await makeSession(id, root, "offline-test-key", invoke);
  session.agent.streamFunction = (model, context, options) => streamSimple({ ...model, api: "openai-responses", baseUrl: `http://127.0.0.1:${port}` }, context, { ...options, apiKey: "offline-test-key" });
  try {
    await session.prompt("读取上下文并观察当前页面。");
    assert.deepEqual(calls, ["context", "observe"]);
    assert.equal(requests.length, 2);
    assert.equal(requests[0].store, false);
    assert.equal(requests[1].previous_response_id, undefined);
    assert.ok(requests[1].input.some((item: any) => item.type === "function_call_output" && Array.isArray(item.output) && item.output.some((part: any) => part.type === "input_image")));
    assert.deepEqual(requests[0].tools.map((tool: any) => tool.name).sort(), ["act", "context", "credential", "give_up", "observe", "resume"]);
    const count = session.messages.length;
    session.dispose();
    const restored = await makeSession(id, root, "offline-test-key", invoke);
    assert.equal(restored.session.messages.length, count);
    restored.session.dispose();
  } finally {
    session.dispose();
    server.closeAllConnections();
    await new Promise<void>(resolve => server.close(() => resolve()));
    await rm(root, { recursive: true, force: true });
  }
});
