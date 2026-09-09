import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

export function useResource<T>(path: string | null, interval = 3000) {
  const [result, setResult] = useState<{ path: string; data: T }>();
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision(v => v + 1), []);
  useEffect(() => {
    let active = true;
    setError("");
    if (!path) return;
    const read = () => api<T>(path).then(data => {
      if (active) { setResult({ path, data }); setError(""); }
    }).catch(error => { if (active) setError(error.message); });
    void read();
    const timer = setInterval(read, interval);
    return () => { active = false; clearInterval(timer); };
  }, [path, interval, revision]);
  return { data: result?.path === path ? result.data : undefined, error, refresh };
}
