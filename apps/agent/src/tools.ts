import { defineTool } from "@earendil-works/pi-coding-agent";
import { Type, type TSchema } from "typebox";
import { compactObservation } from "./context.js";

export type Reply = { status: string; result: Record<string, unknown> & { image?: { data: string; mimeType: string } } };
export type Invoke = (id: string, action: string, params: Record<string, unknown>, signal?: AbortSignal) => Promise<Reply>;

/** Browser order and failure fences are enforced even if a provider batches calls. */
export class ToolGate {
  private tail: Promise<unknown> = Promise.resolve();
  failedTurn = false;
  needsObservation = true;
  finished = false;
  nextTurn() { this.failedTurn = false; }
  run<T>(action: string, invoke: () => Promise<T>): Promise<T> {
    const next = this.tail.then(async () => {
      if (this.finished || this.failedTurn) throw new Error("本轮剩余操作已停止；请在下一轮重新观察。");
      if (this.needsObservation && !["context", "query", "observe", "give_up"].includes(action)) {
        throw new Error("必须先观察当前页面。");
      }
      try {
        const result = await invoke();
        if (["observe", "query"].includes(action) && !this.failedTurn) this.needsObservation = false;
        if (["resume", "give_up"].includes(action)) this.finished = true;
        return result;
      } catch (error) {
        this.failedTurn = true;
        this.needsObservation = true;
        throw error;
      }
    });
    this.tail = next.catch(() => undefined);
    return next;
  }
}

const optionalText = Type.Optional(Type.String({ maxLength: 4000 }));
const object = (properties: Record<string, TSchema>) => Type.Object(properties, { additionalProperties: false });
export function recoveryTools(invoke: Invoke, gate: ToolGate) {
  const attempts = new Map<string, number>();
  const references = new Map<string, unknown>();
  const stable = (value: unknown): unknown => {
    if (typeof value === "string") return references.get(value) ?? value;
    if (Array.isArray(value)) return value.map(stable);
    if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b))
      .filter(([key]) => !["target", "scope", "timings_ms", "evidence_id", "image", "collection_order", "issued", "performed"].includes(key))
      .map(([key, item]) => [key, stable(item)]));
    return value;
  };
  const tool = (name: string, description: string, parameters: TSchema) => defineTool({
    name, label: description, description, parameters, executionMode: "sequential",
    async execute(id, params, signal) {
      return gate.run(name, async () => {
        signal?.throwIfAborted();
        const started = performance.now();
        const reply = await invoke(id, name, params as Record<string, unknown>, signal);
        const { image, ...result } = reply.result;
        result.timings_ms = { ...(result.timings_ms as Record<string, number> ?? {}), operation_roundtrip: performance.now() - started };
        for (const node of Array.isArray(result.nodes) ? result.nodes : []) {
          if (node && typeof node.target === "string") references.set(node.target, { identity: stable(node), scope_identity: references.get(node.scope) ?? node.scope });
        }
        const normalizedParams = Object.fromEntries(Object.entries(params as Record<string, unknown>)
          .map(([key, value]) => [key, stable(value)]));
        const signature = JSON.stringify([name, normalizedParams, stable(result)]);
        const count = (attempts.get(signature) ?? 0) + 1;
        attempts.set(signature, count);
        if (count > 1) result.repetition = { count, hint: "同一查询/对象、参数和事实重复；尚无新证据，请调整策略或 give_up。动作已发出不代表业务恢复。" };
        if (reply.status !== "succeeded") throw new Error(JSON.stringify(result));
        if (result.error || result.observation_error) {
          // DOM failures still carry a screenshot. Return the evidence while
          // fencing the batch; throwing here would discard the image.
          gate.failedTurn = true;
          gate.needsObservation = true;
        }
        const visible = ["observe", "query"].includes(name) ? compactObservation(result, Boolean((params as Record<string, unknown>).include_locators)) : result;
        return { content: [
          { type: "text" as const, text: JSON.stringify(visible) },
          ...(image ? [{ type: "image" as const, data: image.data, mimeType: image.mimeType }] : []),
        ], details: result };
      });
    },
  });
  const fields = Type.Optional(Type.Array(Type.String({ maxLength: 100 }), { maxItems: 20 }));
  const scopePath = Type.Array(object({ kind: Type.Union([Type.Literal("frame"), Type.Literal("shadow")]), locator: Type.String() }), { maxItems: 16 });
  return [
    tool("context", "默认读取失败步骤的完整契约、元素及原参数。step 指定其他步骤；full=true 读取全文和完整诊断。", object({
      step: optionalText, full: Type.Optional(Type.Boolean()),
    })),
    tool("query", "在指定 scope（默认 page）即时查询。locator 用 css:选择器 或 xpath:表达式；也接受 DrissionPage 原生定位和以 /、./、../ 开头的 XPath。返回完整匹配数和分页；多匹配须消歧。relation 支持父子、相邻、遮挡、视觉坐标和 frame/shadow 入口；document 不带 locator 时仅返回所属文档 scope 和 queried=false，不表示页面为空；带 locator 时在该文档实际查询。DOM 读取报错不等于没有 DOM，应结合截图和 observation_location 判断。", object({
      scope: optionalText, locator: optionalText,
      relation: Type.Optional(Type.Union(["descendants", "parent", "children", "next", "prev", "over", "offset", "frame", "shadow", "document"].map(v => Type.Literal(v)))),
      limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 500 })), offset: Type.Optional(Type.Integer({ minimum: 0 })),
      x: Type.Optional(Type.Number()), y: Type.Optional(Type.Number()),
    })),
    tool("observe", "按字段读取活引用或正式元素 ID。fields: value/text/attrs/alive/displayed/enabled/clickable/checked/covered/rect/attr:名称。value 与 text 不同。无 target 时枚举当前 scope 的控件；默认首次截图，此后按需。include_locators 导出完整作用域定位。", object({
      target: optionalText, scope: optionalText, fields,
      limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 500 })), offset: Type.Optional(Type.Integer({ minimum: 0 })),
      screenshot: Type.Optional(Type.Boolean()), include_locators: Type.Optional(Type.Boolean()),
    })),
    tool("act", "使用活引用或正式 ID 操作并等待、回读。target 不接受定位表达式。expect 可用 target 或 scope+query 等待新元素；property 支持读取字段、exists、url_changed、new_tab。返回 issued、condition_met、phase、actual/state；这些不是业务成功，仍须原 verify。错误后先查询/观察，重试前回读。select 只操作原生 select。", object({
      operation: Type.Union(["navigate", "click", "new_tab", "input", "select", "check", "hover", "scroll", "key", "read", "wait", "download"].map(v => Type.Literal(v))),
      target: optionalText, value: optionalText, filename: optionalText, read: fields,
      seconds: Type.Optional(Type.Number({ minimum: 0.1, maximum: 15 })),
      by_js: Type.Optional(Type.Boolean()), checked: Type.Optional(Type.Boolean()),
      direction: Type.Optional(Type.Union(["up", "down", "left", "right"].map(v => Type.Literal(v)))),
      pixels: Type.Optional(Type.Integer({ minimum: 1, maximum: 10000 })),
      expect: Type.Optional(object({ target: optionalText, scope: optionalText, query: optionalText,
        property: Type.String(), equals: Type.Optional(Type.Union([Type.String(), Type.Boolean(), Type.Number(), Type.Null()])) })),
    })),
    tool("credential", "在最终输入处使用原账号凭据字段；返回值不包含明文。", object({ field: Type.String(), target: Type.String() })),
    tool("resume", "提交恢复点，可附失败步骤的真实结果及有 DOM 证据的定位器。交回原 verify/resume；接受请求不代表成功。", object({
      summary: Type.String({ minLength: 1, maxLength: 4000, description: "本轮最终总结：观察结论、已做的动作、提交的步骤及等待原程序校验。" }),
      from_step: Type.String(), step_result: Type.Optional(Type.Record(Type.String(), Type.Unknown())),
      locator_overrides: Type.Optional(Type.Record(Type.String(), Type.Record(Type.String(), Type.Union([Type.String(), Type.Null(), scopePath])))),
    })),
    tool("give_up", "无法恢复或需人工/开发处理时，记录具体原因、尝试、证据及后续事项，然后结束本次接管。", object({
      summary: Type.String({ minLength: 1, maxLength: 4000, description: "本轮最终总结：已尝试事项、无法恢复的原因及后续处理。" }),
      reason: Type.String({ minLength: 1 }), attempted: Type.Array(Type.String()),
      next_actions: Type.Array(Type.String()), evidence: Type.Array(Type.String()),
    })),
  ];
}
