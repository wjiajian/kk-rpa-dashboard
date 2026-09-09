import type { RJSFSchema } from "@rjsf/utils";
export async function api<T>(path: string, body?: unknown, method = body === undefined ? "GET" : "POST"): Promise<T> {
  const response = await fetch(`/api${path}`, { credentials: "same-origin",
    method, ...(body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : `请求失败 (${response.status})`);
  }
  return response.json();
}
export const statuses: Record<string, string> = { queued: "排队中", starting: "启动中", running: "运行中",
  recovering: "Agent 接管中", stopping: "停止中", uncertain: "状态待确认", succeeded: "成功", failed: "失败", stopped: "已停止", cancelled: "已取消" };
export const terminal = (status: string) => ["succeeded", "failed", "stopped", "cancelled"].includes(status);
export const date = (at?: number) => at ? new Date(at * 1000).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false }) : "—";
export interface RunRecord {
  id: string; name: string; status: string; created: number; ended?: number; seq: number;
  phase?: string; robot_id?: string; remaining_seconds?: number; recovery_used?: number; stop_reason?: string;
  rerun_of?: string; snapshot?: { app_id: string; version: string; inputs: Record<string, unknown>; download_dir?: string };
  recovery_rounds?: { number: number; started: number; summary?: string }[];
  attempts?: { id: string; local_run_id: string; status: string; result?: Record<string, unknown> }[];
  conclusion?: { reason: string; attempted: string[]; next_actions: string[]; evidence: string[] };
  evidence?: { id: string; url: string }[];
  token_usage?: { input: number; output: number; cache_read: number; cache_write: number; total: number; requests: number; unreported_responses: number };
}
export interface RunEvent { seq: number; kind: string; message: string; at: number; details?: Record<string, unknown> }
export interface RobotRecord { id: string; name: string; active_run?: string; online: boolean; revoked: boolean; capabilities?: string[]; deployment_job?: string; deployments: { app_id: string; version: string; release_id?: string; commit?: string; input_schema?: RJSFSchema; form_schema?: RJSFSchema; schema_status?: "valid" | "missing" | "invalid"; schema_error?: string }[] }

export interface TaskRecord {
  id: string; name: string; robot_id: string; app_id: string; version: string; revision: number;
  release_id?: string; commit?: string;
  input_bindings: Record<string, { kind: "literal"; value: unknown } | { kind: "relative_date"; offset_days: number }>;
  download_dir?: string | null; schedule: { enabled: boolean; cron: string; timezone: "Asia/Shanghai" };
  next_run_at?: number; last_run_id?: string; last_error?: string;
  credentials_configured: { username: boolean; password: boolean };
}
