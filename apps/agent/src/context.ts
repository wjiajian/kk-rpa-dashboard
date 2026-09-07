import type { AgentSession } from "@earendil-works/pi-coding-agent";

export function compactObservation(result: Record<string, unknown>, includeLocators = false) {
  if (!Array.isArray(result.nodes)) return result;
  const limit = includeLocators ? 500 : 160;
  return { ...result,
    text: typeof result.text === "string" ? result.text.slice(0, 2000) : result.text,
    ...(typeof result.text === "string" && result.text.length > 2000 ? { text_truncated: true } : {}),
    nodes: result.nodes.map(node => ({
      target: node.target, tag: node.tag,
      ...(node.text ? { text: node.text.slice(0, limit), ...(node.text.length > limit ? { text_truncated: true } : {}) } : {}),
      ...(node.attributes ? { attributes: Object.fromEntries(Object.entries(node.attributes).filter(([, value]) => value !== null && value !== "")) } : {}),
      ...(includeLocators ? { locator: node.locator, frame_locator: node.frame_locator } : {}),
    })),
    locator_hint: "操作使用 target；修正定位器前 observe(target=目标, include_locators=true)。精确文本使用 act(read)。",
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
    if (message.toolName !== "observe" || message.isError) return message;
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
