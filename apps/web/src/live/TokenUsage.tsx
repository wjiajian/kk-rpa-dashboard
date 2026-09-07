import type { RunRecord } from "./api";

export function TokenUsage({ usage }: { usage: RunRecord["token_usage"] }) {
  if (!usage) return <span>尚未记录</span>;
  const number = (value: number) => value.toLocaleString("zh-CN");
  return <div>
    <span>{number(usage.total)} tokens</span>
    <div className="small">输入 {number(usage.input + usage.cache_read + usage.cache_write)} · 输出 {number(usage.output)} · 缓存命中 {number(usage.cache_read)}</div>
    {usage.unreported_responses > 0 && <div className="small">部分响应未返回用量，以上为已记录值</div>}
  </div>;
}
