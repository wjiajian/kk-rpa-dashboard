import { CronExpressionParser } from "cron-parser";
export function makeCron(
  mode: string,
  hour: number,
  minute: number,
  day: number,
) {
  return `${minute} ${hour} ${mode === "每月" ? day : "*"} * ${mode === "每周" ? day : "*"}`;
}
export function nextDates(cron: string, currentDate: Date = new Date()) {
  if (cron.trim().split(/\s+/).length !== 5)
    throw new Error("请输入五段 Cron：分 时 日 月 星期");
  return CronExpressionParser.parse(cron, { tz: "Asia/Shanghai", currentDate })
    .take(5)
    .map((x) => x.toDate().toISOString());
}
