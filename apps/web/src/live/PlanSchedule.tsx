import { useEffect, useState } from "react";
import { Alert, Input, InputNumber, Segmented, Space, Switch } from "antd";
import { makeCron } from "../schedule/cron";
import { api } from "./api";

export function PlanSchedule({ cron, enabled, onCron, onEnabled }: {
  cron: string; enabled: boolean; onCron: (value: string) => void; onEnabled: (value: boolean) => void;
}) {
  const [mode, setMode] = useState("高级");
  const [hour, setHour] = useState<number | null>(null);
  const [minute, setMinute] = useState<number | null>(null);
  const [day, setDay] = useState<number | null>(null);
  const [preview, setPreview] = useState<{ cron: string; dates?: number[]; error?: string }>();
  useEffect(() => {
    let active = true;
    if (!cron.trim()) { setPreview(undefined); return; }
    const timer = setTimeout(() => {
      void api<{ dates: number[] }>("/schedules/preview", { cron }).then(value => {
        if (active) setPreview({ cron, dates: value.dates });
      }).catch(error => { if (active) setPreview({ cron, error: error.message }); });
    }, 300);
    return () => { active = false; clearTimeout(timer); };
  }, [cron]);
  const change = (m: string, h: number | null, n: number | null, d: number | null) => {
    setMode(m); setHour(h); setMinute(n); setDay(d);
    if (m !== "高级") onCron(h !== null && n !== null && (m === "每日" || d !== null) ? makeCron(m, h, n, d ?? 1) : "");
  };
  return <div className="schedule"><Space><Switch checked={enabled} onChange={onEnabled} /><strong>启用定时</strong><span className="muted">已入队的运行不受影响</span></Space>
    <Segmented block options={["每日", "每周", "每月", "高级"]} value={mode} onChange={m => change(m, null, null, null)} />
    {mode === "高级" ? <Input aria-label="Cron 表达式" placeholder="分 时 日 月 星期" value={cron} onChange={e => onCron(e.target.value)} /> : <Space wrap>
      {mode !== "每日" && <InputNumber aria-label="日期或星期" placeholder={mode === "每周" ? "星期，0 为周日" : "每月日期"} min={mode === "每周" ? 0 : 1} max={mode === "每周" ? 6 : 31} value={day} onChange={v => change(mode, hour, minute, v)} />}
      <InputNumber aria-label="小时" placeholder="时" min={0} max={23} value={hour} onChange={v => change(mode, v, minute, day)} />
      <InputNumber aria-label="分钟" placeholder="分" min={0} max={59} value={minute} onChange={v => change(mode, hour, v, day)} />
    </Space>}
    {preview?.cron === cron && (preview.error ? <Alert type="error" message={preview.error} /> : <div className="cron-preview"><strong>接下来五次触发 · Asia/Shanghai</strong>{preview.dates?.map(at => <div key={at}>{new Date(at * 1000).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false })}</div>)}</div>)}
    <p className="muted">停机期间错过的计划不补跑。{!enabled && "当前仅可手动触发。"}</p>
  </div>;
}
