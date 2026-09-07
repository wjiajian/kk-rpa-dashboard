import { createServer } from "node:http";
import { rm } from "node:fs/promises";
import { join } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";
import { makeSession } from "./session.js";
import type { Reply } from "./tools.js";

const backend = process.env.BACKEND_URL ?? "http://backend:8000";
const token = process.env.AGENT_INTERNAL_TOKEN;
const key = process.env.DEEPSEEK_API_KEY;
const root = process.env.PI_SESSION_DIR ?? "/data/sessions";
if (!token || !key) throw new Error("AGENT_INTERNAL_TOKEN and DEEPSEEK_API_KEY are required");
const jobs = new Map<string, AbortController>();

async function api(path: string, body?: unknown, signal?: AbortSignal) {
  const response = await fetch(backend + path, { method: body === undefined ? "GET" : "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(20000)]) : AbortSignal.timeout(20000),
  });
  if (!response.ok) throw new Error(`控制端拒绝请求 (${response.status})`);
  return response.json();
}

type Job = { console_run_id: string; execution_attempt_id: string; lease: string; remaining_seconds: number };
async function run(job: Job, abort: AbortController) {
  const path = `/internal/runs/${job.console_run_id}`;
  let activeSession: Awaited<ReturnType<typeof makeSession>> | undefined;
  const timer = setTimeout(() => abort.abort(), Math.max(0, job.remaining_seconds * 1000));
  const monitor = (async () => {
    while (!abort.signal.aborted) {
      await sleep(3000, undefined, { signal: abort.signal });
      const state = await api(`${path}/heartbeat`, { lease: job.lease }, abort.signal);
      if (!state.active || state.remaining_seconds <= 0) abort.abort();
    }
  })().catch(() => abort.abort());
  try {
    activeSession = await makeSession(job.console_run_id, root, key!, async (id, action, params, signal) => {
      const requestId = `${job.execution_attempt_id}:${id}`;
      const payload = { lease: job.lease, execution_attempt_id: job.execution_attempt_id, request_id: requestId, action, params };
      // The request is never retried on an uncertain POST. The next lease reconciles executor results.
      await api(`${path}/operations`, payload, signal);
      if (action === "resume" || action === "give_up") {
        return { status: "succeeded", result: { accepted: true, request_id: requestId, awaiting_executor: true } };
      }
      while (true) {
        const response: Reply = await api(`${path}/operations/${encodeURIComponent(requestId)}`, undefined, signal);
        if (!["accepted", "running"].includes(response.status)) return response;
        await sleep(300, undefined, { signal });
      }
    });
    abort.signal.addEventListener("abort", () => { void activeSession?.session.abort(); }, { once: true });
    abort.signal.throwIfAborted();
    await activeSession.session.prompt(`处理控制台运行 ${job.console_run_id} 的当前失败尝试 ${job.execution_attempt_id}。先读取最新 context 和 observe；历史工具调用不可重发。`);
    if (!activeSession.gate.finished && !abort.signal.aborted) {
      await api(`${path}/agent-failed`, { lease: job.lease });
    }
  } catch {
    // Cancellation never claims the robot stopped. Backend/executor confirm it.
    if (!abort.signal.aborted) await api(`${path}/agent-failed`, { lease: job.lease }).catch(() => undefined);
  } finally {
    abort.abort();
    clearTimeout(timer);
    await monitor;
    await activeSession?.session.abort();
    activeSession?.session.dispose();
  }
}

const server = createServer((request, response) => {
  response.writeHead(request.url === "/health" ? 200 : 404, { "Content-Type": "application/json" });
  response.end(JSON.stringify({ active: jobs.size }));
}).listen(3001, "0.0.0.0");

let shuttingDown = false;
for (const event of ["SIGINT", "SIGTERM"] as const) process.on(event, () => {
  shuttingDown = true;
  for (const controller of jobs.values()) controller.abort();
  server.close();
});

while (!shuttingDown) {
  try {
    const work: { runs: string[]; expired: string[] } = await api("/internal/agent/work");
    for (const id of work.expired) {
      if (jobs.has(id) || !/^[a-f0-9-]{36}$/.test(id)) continue;
      await rm(join(root, id), { recursive: true, force: true });
      await api(`/internal/runs/${id}/purge`, {});
    }
    for (const id of work.runs) {
      if (jobs.has(id)) continue;
      const job: Job = await api(`/internal/runs/${id}/claim`, {}).catch(() => null);
      if (!job) continue;
      const abort = new AbortController();
      jobs.set(id, abort);
      void run(job, abort).finally(() => jobs.delete(id));
    }
  } catch { /* Service reconnection does not restart any robot operation. */ }
  await sleep(1000);
}
