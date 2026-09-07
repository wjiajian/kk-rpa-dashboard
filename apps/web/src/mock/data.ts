import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";
import timezone from "dayjs/plugin/timezone";
dayjs.extend(utc);
dayjs.extend(timezone);
export const time = (value: string, format = "MM-DD HH:mm:ss") =>
  dayjs(value).tz("Asia/Shanghai").format(format);
export const today = dayjs().tz("Asia/Shanghai").format("YYYY-MM-DD");
export type Status =
  | "排队中"
  | "启动中"
  | "运行中"
  | "停止中"
  | "Agent 接管中"
  | "成功"
  | "失败"
  | "已取消"
  | "已停止"
  | "状态待确认";
export type Binding =
  | { kind: "fixed"; value: string }
  | { kind: "relative_date"; offset_days: number };
export interface Application {
  id: string;
  name: string;
  description: string;
  version: string;
  source: string;
  valid: boolean;
  tags: string[];
  imported: string;
}
export interface Task {
  id: string;
  name: string;
  appId: string;
  version: string;
  robot: string;
  brand: string;
  filename: string;
  date: Binding;
  cron: string;
  enabled: boolean;
  configured: boolean;
}
export interface Run {
  id: string;
  taskId: string;
  name: string;
  appId: string;
  version: string;
  robot: string;
  params: Record<string, string>;
  status: Status;
  source: string;
  created: string;
  duration: string;
  progress: number;
  error?: string;
  rerunOf?: string;
}
export const applications: Application[] = [
  {
    id: "product-report",
    name: "商品明细报表",
    description: "自动采集商品销售明细，生成每日经营报表。",
    version: "1.3.0",
    source: "kk-rpa-monorepo",
    valid: true,
    tags: ["经营报表", "数据导出"],
    imported: today,
  },
  {
    id: "order-reconcile",
    name: "订单对账",
    description: "核对平台订单与结算数据，定位差异记录。",
    version: "2.1.0",
    source: "kk-rpa-monorepo",
    valid: true,
    tags: ["财务核对", "订单管理"],
    imported: today,
  },
  {
    id: "inventory-sync",
    name: "库存数据同步",
    description: "同步各门店库存快照，汇总库存变动。",
    version: "1.0.2",
    source: "上传包",
    valid: true,
    tags: ["数据同步", "库存管理"],
    imported: today,
  },
  {
    id: "invoice-export",
    name: "发票批量导出",
    description: "按账期整理开票记录并批量导出。",
    version: "0.8.0",
    source: "上传包",
    valid: false,
    tags: ["财务核对", "数据导出"],
    imported: today,
  },
];
export const robots = [
  {
    id: "RPA-01",
    name: "运营机器人 01",
    status: "运行中",
    location: "运营专用电脑",
    version: "商品明细报表 1.3.0",
  },
  {
    id: "RPA-02",
    name: "财务机器人 02",
    status: "运行中",
    location: "财务专用电脑",
    version: "订单对账 2.1.0",
  },
  {
    id: "RPA-03",
    name: "运营机器人 03",
    status: "空闲",
    location: "运营专用电脑",
    version: "库存数据同步 1.0.2",
  },
  {
    id: "RPA-04",
    name: "备用机器人 04",
    status: "离线",
    location: "备用电脑",
    version: "尚未部署",
  },
];
export const tasks: Task[] = Array.from({ length: 6 }, (_, i) => ({
  id: `task-${i + 1}`,
  name: [
    "商品日报 · 全部门店",
    "订单对账 · 华东区域",
    "库存同步 · 总仓",
    "商品日报 · 线上渠道",
    "订单对账 · 华南区域",
    "库存同步 · 门店仓",
  ][i],
  appId: applications[i % 3].id,
  version: applications[i % 3].version,
  robot: robots[i % 3].id,
  brand: "全部品牌",
  filename: "report.xlsx",
  date: { kind: "relative_date", offset_days: -1 },
  cron: `0 ${8 + i} * * *`,
  enabled: i !== 4,
  configured: true,
}));
const statuses: Status[] = [
  "运行中",
  "运行中",
  "排队中",
  "失败",
  "成功",
  "失败",
  "成功",
  "成功",
  "成功",
  "排队中",
  "成功",
  "失败",
];
export const runs: Run[] = statuses.map((status, i) => {
  const t = tasks[i % 6];
  return {
    id: `RUN-${today.replaceAll("-", "")}-${String(128 - i).padStart(4, "0")}`,
    taskId: t.id,
    name: t.name,
    appId: t.appId,
    version: t.version,
    robot: t.robot,
    params: {
      target_date: dayjs().subtract(1, "day").format("YYYY-MM-DD"),
      brand: t.brand,
      export_filename: t.filename,
    },
    status,
    source: i % 3 === 0 ? "手动" : "定时",
    created: `${today}T${String(10 - Math.floor(i / 6)).padStart(2, "0")}:${String(42 - (i % 6) * 7).padStart(2, "0")}:00+08:00`,
    duration: ["2分 18秒", "1分 06秒", "—", "42秒", "3分 12秒"][i % 5],
    progress:
      status === "成功"
        ? 100
        : status === "运行中"
          ? 60
          : status === "失败"
            ? i === 3
              ? 20
              : 60
            : 0,
    error:
      status === "失败"
        ? i === 3
          ? "登录检查失败，当前账号身份不符合任务要求"
          : "下载报表超时，请检查业务平台状态"
        : undefined,
  };
});
