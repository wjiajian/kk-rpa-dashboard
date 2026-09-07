import { describe, it, expect } from "vitest";
import { makeCron, nextDates } from "./cron";
describe("定时计划", () => {
  it("生成日周月五段表达式", () => {
    expect(makeCron("每日", 8, 0, 1)).toBe("0 8 * * *");
    expect(makeCron("每周", 8, 0, 1)).toBe("0 8 * * 1");
    expect(makeCron("每月", 8, 0, 1)).toBe("0 8 1 * *");
  });
  it("以上海时区计算未来五次触发", () => {
    const dates = nextDates("0 8 * * *", new Date("2026-09-07T01:00:00Z"));
    expect(dates).toHaveLength(5);
    expect(dates[0]).toBe("2026-09-08T00:00:00.000Z");
    expect(dates[4]).toBe("2026-09-12T00:00:00.000Z");
  });
  it("拒绝六段表达式及非法时间", () => {
    expect(() => nextDates("0 0 8 * * *")).toThrow();
    expect(() => nextDates("0 25 * * *")).toThrow();
  });
});
