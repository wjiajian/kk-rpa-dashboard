import type { Experimental_DefaultFormStateBehavior, RJSFSchema } from "@rjsf/utils";
import validator from "@rjsf/validator-ajv8";
import type { Task } from "../mock/data";

export const parameterFormBehavior: Experimental_DefaultFormStateBehavior = { emptyObjectFields: "skipDefaults", arrayMinItems: { populate: "never" } };
export type ParameterValues = Record<string, unknown>;
export const reportSchema: RJSFSchema = {
  type: "object", required: ["brand", "export_filename", "target_date"], additionalProperties: false,
  properties: {
    brand: { type: "string", title: "品牌范围", enum: ["全部品牌", "品牌 A", "品牌 B"], default: "全部品牌", description: "选择需要导出的品牌" },
    export_filename: { type: "string", title: "导出文件名", default: "report.xlsx", pattern: "^[^/\\\\]+\\.xlsx$", description: "Excel 文件名，例如 report.xlsx" },
    target_date: { type: "string", title: "业务日期", format: "date", description: "支持固定日期或相对执行日期" },
  },
};
export const reconcileSchema: RJSFSchema = {
  type: "object", required: ["region", "tolerance"], additionalProperties: false,
  properties: {
    region: { type: "string", title: "对账区域", enum: ["全部区域", "华东", "华南"], default: "全部区域", description: "本次需要核对的订单区域" },
    tolerance: { type: "number", title: "差额容差", minimum: 0, default: 0.01, description: "允许的金额差额，单位：元" },
    include_refunds: { type: "boolean", title: "包含退款订单", default: true, description: "是否同时核对退款记录" },
  },
};
export const inventorySchema: RJSFSchema = {
  type: "object", required: ["warehouse", "batch_size"], additionalProperties: false,
  properties: {
    warehouse: { type: "string", title: "仓库", minLength: 1, default: "总仓", description: "填写需要同步的仓库名称" },
    batch_size: { type: "integer", title: "每批数量", minimum: 1, maximum: 1000, default: 100, description: "每批同步的库存记录数（1–1000）" },
    full_sync: { type: "boolean", title: "全量同步", default: false, description: "关闭时仅同步变动数据" },
  },
};
export function parameterDefaults(schema?: RJSFSchema): ParameterValues {
  return Object.fromEntries(Object.entries(schema?.properties ?? {}).flatMap(([key, field]) =>
    field && typeof field === "object" && "default" in field && field.default !== undefined ? [[key, structuredClone(field.default)]] : []));
}
export function taskParameters(task: Task, schema: RJSFSchema): ParameterValues {
  if (task.parameters) return task.parameters;
  const legacy = { brand: task.brand, export_filename: task.filename, target_date: task.date };
  return { ...parameterDefaults(schema), ...Object.fromEntries(Object.entries(legacy).filter(([key]) => key in (schema.properties ?? {}))) };
}
export function cleanParameters(values: ParameterValues): ParameterValues {
  return Object.fromEntries(Object.entries(values).filter(([, value]) => value !== undefined));
}
export function parameterError(schema: RJSFSchema, values: ParameterValues, relativeDates = false): string | undefined {
  const normalized = cleanParameters(values);
  for (const [key, value] of Object.entries(values)) {
    const field = schema.properties?.[key];
    if (relativeDates && typeof field === "object" && field.format === "date" && value && typeof value === "object" && "kind" in value) {
      if (value.kind === "relative_date" && "offset_days" in value && Number.isInteger(value.offset_days)) normalized[key] = "2000-01-01";
      else if (value.kind === "fixed" && "value" in value) normalized[key] = value.value;
      else return `${field.title || key}：请填写有效的日期或整数偏移`;
    }
  }
  const errors = validator.validateFormData(normalized, schema).errors;
  if (errors.length) return `请检查参数：${errors.map(e => e.stack).join("；")}`;
}
