import { readdir } from "node:fs/promises";
import { join } from "node:path";
import { SessionManager } from "@earendil-works/pi-coding-agent";

export function sessionUsage(manager: Pick<SessionManager, "getEntries" | "getSessionId">) {
  const entries = manager.getEntries();
  const result = { session_id: manager.getSessionId(), revision: entries.length,
    input: 0, output: 0, cache_read: 0, cache_write: 0, requests: 0, unreported_responses: 0 };
  for (const entry of entries) {
    const message = entry.type === "message" ? entry.message : undefined;
    const summary = entry.type === "compaction" || entry.type === "branch_summary" ? entry : undefined;
    if (message?.role !== "assistant" && !summary?.usage) continue;
    const usage = message?.role === "assistant" ? message.usage : summary?.usage;
    result.requests++;
    if (!usage || !(usage.input + usage.output + usage.cacheRead + usage.cacheWrite)) {
      result.unreported_responses++;
      continue;
    }
    result.input += usage.input;
    result.output += usage.output; // Includes reasoning tokens; do not add them again.
    result.cache_read += usage.cacheRead;
    result.cache_write += usage.cacheWrite;
  }
  return result;
}

export async function restoreUsage(root: string, report: (runId: string, usage: ReturnType<typeof sessionUsage>) => Promise<unknown>) {
  const directories = await readdir(root, { withFileTypes: true }).catch(error => {
    if (error.code === "ENOENT") return [];
    throw error;
  });
  for (const directory of directories) {
    if (!directory.isDirectory() || !/^[a-f0-9-]{36}$/.test(directory.name)) continue;
    const path = join(root, directory.name);
    for (const session of await SessionManager.list(path, path)) {
      await report(directory.name, sessionUsage(SessionManager.open(session.path, path)));
    }
  }
}
