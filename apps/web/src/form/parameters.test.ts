import { getDefaultFormState } from "@rjsf/utils";
import validator from "@rjsf/validator-ajv8";
import { describe, expect, it } from "vitest";
import { inventorySchema, parameterFormBehavior, parameterDefaults, parameterError, reconcileSchema, reportSchema, taskParameters } from "./parameters";
import { tasks } from "../mock/data";
import { assembleTask } from "./submit";

describe("应用参数", () => {
  it("不同应用只使用自身声明的默认值，包括 false 和数字", () => {
    expect(parameterDefaults(inventorySchema)).toEqual({ warehouse: "总仓", batch_size: 100, full_sync: false });
    expect(taskParameters(tasks[1], reconcileSchema)).not.toHaveProperty("export_filename");
    expect(taskParameters(tasks[1], reconcileSchema)).toHaveProperty("tolerance", 0.01);
  });
  it("按声明校验必填、整数、范围和文件名", () => {
    expect(parameterError(inventorySchema, { warehouse: "", batch_size: 1.5 })).toBeTruthy();
    expect(parameterError(inventorySchema, { warehouse: "总仓", batch_size: 1001 })).toBeTruthy();
    expect(parameterError(inventorySchema, parameterDefaults(inventorySchema))).toBeUndefined();
    expect(parameterError(reportSchema, { brand: "全部品牌", export_filename: "../bad.xlsx", target_date: "2026-09-08" })).toBeTruthy();
  });
  it("保存相对日期绑定且不向无日期应用注入日期", () => {
    const values = taskParameters(tasks[0], reportSchema);
    expect(parameterError(reportSchema, values, true)).toBeUndefined();
    expect(parameterError(reportSchema, { ...values, target_date: { kind: "relative_date", offset_days: 1.5 } }, true)).toBeTruthy();
    const result = assembleTask({ ...tasks[2], parameters: parameterDefaults(inventorySchema) });
    expect(result.input_bindings).toEqual({ warehouse: { kind: "literal", value: "总仓" }, batch_size: { kind: "literal", value: 100 }, full_sync: { kind: "literal", value: false } });
  });
  it("允许明确声明为空参数的应用", () => {
    expect(parameterError({ type: "object", properties: {} }, {})).toBeUndefined();
  });
});

it("新建参数不填入声明的默认值，已有参数保持原值", () => {
  expect(getDefaultFormState(validator, inventorySchema, {}, inventorySchema, false, parameterFormBehavior)).toEqual({});
  const saved = { warehouse: "测试仓", batch_size: 25, full_sync: false };
  expect(getDefaultFormState(validator, inventorySchema, saved, inventorySchema, false, parameterFormBehavior)).toEqual(saved);
  expect(taskParameters({ ...tasks[0], parameters: {} }, reportSchema)).toEqual({});
});
