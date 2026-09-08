import { parameterError } from "./parameters";
import type { RJSFSchema } from "@rjsf/utils";
import type { Task } from "../mock/data";
export function assembleTask(task: Task, newPassword?: string) {
  return {
    input_bindings: task.parameters ? Object.fromEntries(Object.entries(task.parameters).map(([key, value]) => [key, value && typeof value === "object" && "kind" in value ? value : { kind: "literal", value }])) : {
      target_date: task.date,
      brand: { kind: "literal", value: task.brand },
      export_filename: { kind: "literal", value: task.filename },
    },
    ...(newPassword ? { credentials: { username: task.username, password: newPassword, expected_identity: task.expectedIdentity } } : {}),
  };
}
export function validateTask(task: Task, schema?: RJSFSchema) {
  if (!task.name.trim())
    return "请填写任务名称";
  if (schema) return parameterError(schema, task.parameters ?? {}, true) || null;
  if (!task.brand || !/^[^/\\]+\.xlsx$/.test(task.filename))
    return "请填写品牌和有效的 .xlsx 导出文件名";
  if (
    task.date.kind === "fixed" &&
    !/^\d{4}-\d{2}-\d{2}$/.test(task.date.value)
  )
    return "请选择固定业务日期";
  if (
    task.date.kind === "relative_date" &&
    !Number.isInteger(task.date.offset_days)
  )
    return "日期偏移必须为整数";
  return null;
}
