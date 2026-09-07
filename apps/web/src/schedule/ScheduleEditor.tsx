import { useState } from "react";
import { Alert, Input, InputNumber, Segmented, Space, Switch } from "antd";
import { makeCron, nextDates } from "./cron";
import { time } from "../mock/data";
export function ScheduleEditor({
  cron,
  enabled,
  onCron,
  onEnabled,
}: {
  cron: string;
  enabled: boolean;
  onCron: (v: string) => void;
  onEnabled: (v: boolean) => void;
}) {
  const [mode, setMode] = useState("高级");
  const [hour, setHour] = useState(8);
  const [minute, setMinute] = useState(0);
  const [day, setDay] = useState(1);
  let dates: string[] = [];
  let error = "";
  try {
    dates = nextDates(cron);
  } catch {
    error = "请输入有效的五段 Cron 表达式（分 时 日 月 星期）";
  }
  const change = (m: string, h: number, n: number, d: number) => {
    setMode(m);
    setHour(h);
    setMinute(n);
    setDay(d);
    if (m !== "高级") onCron(makeCron(m, h, n, d));
  };
  return (
    <div className="schedule">
      <Space>
        <Switch checked={enabled} onChange={onEnabled} />
        <strong>启用定时</strong>
        <span className="muted">已入队的运行不受影响</span>
      </Space>
      <Segmented
        block
        options={["每日", "每周", "每月", "高级"]}
        value={mode}
        onChange={(m) => change(m, hour, minute, day)}
      />
      {mode === "高级" ? (
        <Input
          aria-label="Cron 表达式"
          value={cron}
          onChange={(e) => onCron(e.target.value)}
          placeholder="0 8 * * *"
        />
      ) : (
        <Space wrap>
          {mode !== "每日" && (
            <>
              <span>{mode === "每周" ? "星期（0 为周日）" : "每月日期"}</span>
              <InputNumber
                aria-label="日期或星期"
                min={mode === "每周" ? 0 : 1}
                max={mode === "每周" ? 6 : 31}
                value={day}
                onChange={(d) => change(mode, hour, minute, d ?? 1)}
              />
            </>
          )}
          <InputNumber
            aria-label="小时"
            min={0}
            max={23}
            value={hour}
            onChange={(h) => change(mode, h ?? 8, minute, day)}
          />
          时
          <InputNumber
            aria-label="分钟"
            min={0}
            max={59}
            value={minute}
            onChange={(n) => change(mode, hour, n ?? 0, day)}
          />
          分
        </Space>
      )}
      {error ? (
        <Alert type="error" message={error} />
      ) : (
        <div className="cron-preview">
          <strong>
            接下来五次触发 <span className="muted">· Asia/Shanghai</span>
          </strong>
          {dates.map((d) => (
            <div key={d}>{time(d, "YYYY-MM-DD ddd HH:mm")}</div>
          ))}
          <small>
            实际触发以后端调度为准{!enabled ? "；当前定时已关闭" : ""}
          </small>
        </div>
      )}
    </div>
  );
}
