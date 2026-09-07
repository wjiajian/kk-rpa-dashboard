import assert from "node:assert/strict";
import { test } from "node:test";
import { compactObservation, trimRecoveryHistory } from "./context.js";
import { recoveryTools, ToolGate } from "./tools.js";

test("compact observation keeps actionable targets and full locators remain available on demand", async () => {
  const result = { text: "业务页面", nodes: [{ tag: "button", target: "observed_one", locator: "xpath:/html/body/button[1]",
    frame_locator: "css:#report", text: "下载", attributes: { id: "download", class: "", name: null, disabled: false } }] };
  const compact = compactObservation(result);
  assert.equal(compact.nodes[0].target, "observed_one");
  assert.equal(compact.nodes[0].locator, undefined);
  assert.deepEqual(compact.nodes[0].attributes, { id: "download", disabled: false });
  assert.equal(compactObservation(result, true).nodes[0].locator, result.nodes[0].locator);
  const observe = recoveryTools(async () => ({ status: "succeeded", result }), new ToolGate()).find(tool => tool.name === "observe")!;
  const reply = await observe.execute("id", {});
  assert.deepEqual(reply.details, result);
  assert.ok(!JSON.stringify(reply.content).includes("xpath:/html"));
  assert.equal(result.nodes[0].attributes.name, null);
});

test("long text is marked as a preview instead of silently presented as exact", () => {
  const compact = compactObservation({ text: "x".repeat(3000), nodes: [{ target: "one", tag: "div", text: "x".repeat(500) }] });
  assert.equal(compact.text.length, 2000);
  assert.equal(compact.text_truncated, true);
  assert.equal(compact.nodes[0].text.length, 160);
  assert.equal(compact.nodes[0].text_truncated, true);
});

test("history preserves calls and errors, keeps two observations and one image without changing saved data", () => {
  const tool = (name: string, id: string, isError = false) => ({ role: "toolResult", toolName: name, toolCallId: id, isError,
    content: [{ type: "text", text: id }, ...(name === "observe" && !isError ? [{ type: "image", mimeType: "image/png", data: id }] : [])] });
  const messages = [tool("context", "context-old"), tool("observe", "one"),
    { role: "assistant", content: [{ type: "toolCall", id: "act-one", name: "act", arguments: { operation: "click", target: "one" } }] },
    tool("act", "act-one", true), tool("observe", "two"), tool("context", "context-new"), tool("observe", "three")];
  const snapshot = JSON.stringify(messages);
  const filtered = trimRecoveryHistory(messages as Parameters<typeof trimRecoveryHistory>[0]);
  assert.equal(filtered.length, messages.length);
  assert.equal(JSON.stringify(messages), snapshot);
  assert.equal(JSON.stringify(filtered).match(/"type":"image"/g)?.length, 1);
  const outputs = filtered.filter(m => m.role === "toolResult");
  assert.deepEqual(outputs.map(m => m.toolCallId), ["context-old", "one", "act-one", "two", "context-new", "three"]);
  assert.deepEqual(outputs[2], messages[3]);
  assert.equal(outputs[3].content[0].type === "text" && outputs[3].content[0].text, "two");
  assert.equal(outputs[5].content[0].type === "text" && outputs[5].content[0].text, "three");
  assert.ok(outputs[1].content[0].type === "text" && outputs[1].content[0].text.includes("历史页面观察"));
});
