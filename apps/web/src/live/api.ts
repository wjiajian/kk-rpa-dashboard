export const LIVE = import.meta.env.VITE_RUNTIME === "live";
export async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, { credentials: "same-origin",
    ...(body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
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
export const date = (at?: number) => at ? new Date(at * 1000).toLocaleString("zh-CN", { hour12: false }) : "—";
export interface RunRecord {
  id: string; name: string; status: string; created: number; ended?: number; seq: number;
  phase?: string; robot_id?: string; remaining_seconds?: number; recovery_used?: number; stop_reason?: string;
  rerun_of?: string; snapshot?: { app_id: string; version: string; account_id: string; inputs: Record<string, unknown>; download_dir?: string };
  attempts?: { id: string; local_run_id: string; status: string; result?: Record<string, unknown> }[];
  conclusion?: { reason: string; attempted: string[]; next_actions: string[]; evidence: string[] };
  evidence?: { id: string; url: string }[];
}
export interface RunEvent { seq: number; kind: string; message: string; at: number; details?: Record<string, unknown> }
export interface RobotRecord { id: string; name: string; active_run?: string; online: boolean; revoked: boolean; deployments: { app_id: string; version: string }[] }
