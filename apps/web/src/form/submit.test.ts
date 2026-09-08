import { it, expect } from "vitest";
import { assembleTask, validateTask } from "./submit";
import { tasks } from "../mock/data";
it("沿用凭据时省略字段，日期绑定保留原结构", () => {
  const result = assembleTask(tasks[0]);
  expect(result).not.toHaveProperty("credentials");
  expect(result.input_bindings.target_date).toEqual({
    kind: "relative_date",
    offset_days: -1,
  });
  expect(result.input_bindings.brand).toEqual({
    kind: "literal",
    value: "全部品牌",
  });
});
it("只装配显式新密码", () => {
  expect(assembleTask({ ...tasks[0], username: "test-user", expectedIdentity: "test-shop" }, "test-only").credentials).toEqual({
    username: "test-user",
    password: "test-only",
    expected_identity: "test-shop",
  });
});
it("业务必填项、文件名和日期偏移校验", () => {
  expect(validateTask(tasks[0])).toBeNull();
  expect(validateTask({ ...tasks[0], filename: "../bad.xlsx" })).toBeTruthy();
  expect(validateTask({ ...tasks[0], name: " " })).toBeTruthy();
  expect(
    validateTask({
      ...tasks[0],
      date: { kind: "relative_date", offset_days: 1.2 },
    }),
  ).toBeTruthy();
});
