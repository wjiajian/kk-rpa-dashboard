import { defineTool } from "@earendil-works/pi-coding-agent";
import { Type, type TSchema } from "typebox";

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
      if (this.needsObservation && !["context", "observe", "give_up"].includes(action)) {
        throw new Error("必须先观察当前页面。");
      }
      try {
        const result = await invoke();
        if (action === "observe") this.needsObservation = false;
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
  const tool = (name: string, description: string, parameters: TSchema) => defineTool({
    name, label: description, description, parameters, executionMode: "sequential",
    async execute(id, params, signal) {
      return gate.run(name, async () => {
        signal?.throwIfAborted();
        const reply = await invoke(id, name, params as Record<string, unknown>, signal);
        if (reply.status !== "succeeded") throw new Error(JSON.stringify(reply.result));
        const { image, ...result } = reply.result;
        return { content: [
          { type: "text" as const, text: JSON.stringify(result) },
          ...(image ? [{ type: "image" as const, data: image.data, mimeType: image.mimeType }] : []),
        ], details: result };
      });
    },
  });
  return [
    tool("context", "读取本次恢复的原输入、成功输出、失败记录、步骤要求及正式元素；不读取任意文件。", object({})),
    tool("observe", "观察可见 DOM 和截图。返回的 target 可用于临时操作；iframe 使用 frame_target 继续观察。", object({
      target: optionalText, frame_target: optionalText, limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 500 })),
    })),
    tool("act", "操作原业务页面。target 仅接受正式元素 ID 或 observe 返回的 target；值必须遵循原输入与步骤要求。", object({
      operation: Type.Union(["navigate", "click", "new_tab", "input", "select", "read", "wait", "download"].map(v => Type.Literal(v))),
      target: optionalText, value: optionalText, filename: optionalText,
      seconds: Type.Optional(Type.Number({ minimum: 0.1, maximum: 15 })),
    })),
    tool("credential", "在最终输入处使用原账号凭据字段；返回值不包含明文。", object({ field: Type.String(), target: Type.String() })),
    tool("resume", "提交恢复点，可附失败步骤的真实结果及有 DOM 证据的定位器。交回原 verify/resume；接受请求不代表成功。", object({
      from_step: Type.String(), step_result: Type.Optional(Type.Record(Type.String(), Type.Unknown())),
      locator_overrides: Type.Optional(Type.Record(Type.String(), Type.Record(Type.String(), Type.Union([Type.String(), Type.Null()])))),
    })),
    tool("give_up", "无法恢复或需人工/开发处理时，记录具体原因、尝试、证据及后续事项，然后结束本次接管。", object({
      reason: Type.String({ minLength: 1 }), attempted: Type.Array(Type.String()),
      next_actions: Type.Array(Type.String()), evidence: Type.Array(Type.String()),
    })),
  ];
}
