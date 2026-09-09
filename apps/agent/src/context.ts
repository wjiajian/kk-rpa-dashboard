import type { AgentSession } from "@earendil-works/pi-coding-agent";

export function compactObservation(result: Record<string, unknown>, includeLocators = false) {
  if (!Array.isArray(result.nodes)) return result;
  const limit = includeLocators ? 500 : 160;
  const compactNode = (node: Record<string, any>) => ({
    ...Object.fromEntries(Object.entries(node).filter(([key]) => !["locator", "frame_locator", "scope_path", "text", "attributes"].includes(key))),
    ...(node.text ? { text: node.text.slice(0, limit), ...(node.text.length > limit ? { text_truncated: true } : {}) } : {}),
    ...(node.attributes ? { attributes: Object.fromEntries(Object.entries(node.attributes).filter(([, value]) => value !== null && value !== "")) } : {}),
    ...(includeLocators ? { locator: node.locator, frame_locator: node.frame_locator } : {}),
  });
  return { ...result,
    text: typeof result.text === "string" ? result.text.slice(0, 2000) : result.text,
    ...(typeof result.text === "string" && result.text.length > 2000 ? { text_truncated: true } : {}),
    nodes: result.nodes.map(compactNode),
    ...(Array.isArray(result.frames) ? { frames: result.frames.map(compactNode) } : {}),
    locator_hint: "target 使用正式 ID 或活引用；定位表达式放 query.locator。用 query(relation=document) 获取所属作用域，用 frame/shadow 导航入口。分页查询不能据截断判断不存在。",
  };
}

type History = Parameters<NonNullable<AgentSession["agent"]["transformContext"]>>[0];

export function trimRecoveryHistory(messages: History): History {
  let observations = 0;
  let imageKept = false;
  let contextKept = false;
  return [...messages].reverse().map(message => {
    if (message.role !== "toolResult") return message;
    if (message.toolName === "context" && !message.isError) {
      if (contextKept) return { ...message, content: [{ type: "text" as const, text: "已由后续 context 更新；可按步骤重新读取契约。" }] };
      contextKept = true;
    }
    if (!["observe", "query"].includes(message.toolName) || message.isError) return message;
    observations++;
    if (observations > 2) return { ...message, content: [{ type: "text" as const, text: "历史页面观察已省略；以最近观察为准，必要时重新观察。" }] };
    const content = message.content.filter(part => {
      if (part.type !== "image") return true;
      if (imageKept) return false;
      imageKept = true;
      return true;
    });
    return { ...message, content };
  }).reverse();
}
