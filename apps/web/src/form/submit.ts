import type { Task } from "../mock/data";
export function assembleTask(task: Task, newPassword?: string) {
  return {
    input_bindings: {
      target_date: task.date,
      brand: { kind: "literal", value: task.brand },
      export_filename: { kind: "literal", value: task.filename },
    },
    ...(newPassword ? { credentials: { password: newPassword } } : {}),
  };
}
export function validateTask(task: Task) {
  if (!task.name.trim() || !task.account.trim())
    return "请填写任务名称和账号别名";
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
