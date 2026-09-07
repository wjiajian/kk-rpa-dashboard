import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { ExecutionLog } from "./ExecutionLog";
import type { RunEvent } from "./api";

const event = (seq: number, kind: string, message: string, details?: Record<string, unknown>): RunEvent => ({ seq, at: seq, kind, message, details });

it.each([false, true])("将所有接管轮次合并为一条默认折叠日志，隐藏解析结果（成员=%s）", business => {
  const html = renderToStaticMarkup(<ExecutionLog business={business} events={[
    event(1, "progress", "程序执行"),
    event(2, "recovery_started", "已进入接管"),
    event(3, "agent_activity", "第 1 轮 · 观察页面：执行中", { nodes: ["private DOM"], locator: "css:private" }),
    event(4, "agent_summary", "第一轮结束"),
    event(5, "operation", "旧工具结果", { result: "private DOM" }),
    event(6, "agent_activity", "第 2 轮 · 下载报表：执行中"),
  ]} />);
  expect(html.match(/class="log-line"/g)).toHaveLength(2);
  expect(html.match(/Agent 执行情况/g)).toHaveLength(1);
  expect(html).toContain('<details class="agent-log">');
  expect(html).toContain('class="agent-log-body"');
  expect(html).toContain('aria-label="Agent 执行详情"');
  expect(html).toContain("第一轮结束");
  expect(html).toContain("第 2 轮 · 下载报表：执行中");
  expect(html).not.toContain("private DOM");
  expect(html).not.toContain("css:private");
  expect(html).not.toContain("旧工具结果");
  expect(html.indexOf("Agent 执行情况")).toBeLessThan(html.indexOf("程序执行"));
});

it("按最新事件排序并保留普通程序诊断", () => {
  const html = renderToStaticMarkup(<ExecutionLog business={false} events={[
    event(5, "agent_summary", "已提交续跑"),
    event(8, "attempt_finished", "最新程序结果", { status: "failed" }),
    event(1, "progress", "最早步骤"),
  ]} />);
  expect(html.indexOf("最新程序结果")).toBeLessThan(html.indexOf("Agent 执行情况"));
  expect(html.indexOf("Agent 执行情况")).toBeLessThan(html.indexOf("最早步骤"));
  expect(html).toContain("查看执行结果");
  expect(html).toContain("failed");
});
