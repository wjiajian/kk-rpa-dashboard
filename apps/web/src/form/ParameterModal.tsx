import { useState } from "react";
import { Alert, Empty, Modal, Select } from "antd";
import Form from "@rjsf/antd";
import validator from "@rjsf/validator-ajv8";
import type { RJSFSchema } from "@rjsf/utils";
import { DateBindingField } from "./DateBindingField";
import type { Binding } from "../mock/data";
import { parameterError, parameterFormBehavior, type ParameterValues } from "./parameters";

const typeNames: Record<string, string> = { string: "字符串", integer: "整数", number: "数字", boolean: "布尔值", array: "列表", object: "对象" };
export function ParameterModal({ schema, values, onSave, onCancel, relativeDates = false }: {
  schema: RJSFSchema; values: ParameterValues; onSave: (v: ParameterValues) => void; onCancel: () => void; relativeDates?: boolean;
}) {
  const [draft, setDraft] = useState<ParameterValues>(() => structuredClone(values));
  const [error, setError] = useState<string>();
  return <Modal open width={960} title="参数配置" className="parameter-modal" okText="确定" cancelText="取消" onCancel={onCancel} onOk={() => {
    const problem = parameterError(schema, draft, relativeDates);
    setError(problem);
    if (!problem) onSave(draft);
  }}>
    <Alert type="warning" showIcon message="此处填写的参数仅用于本次任务配置，不改变应用内的默认参数。" />
    <h3>输入参数</h3>
    {error && <Alert type="error" showIcon message={error} className="mb" />}
    {!Object.keys(schema.properties ?? {}).length ? <Empty description="该应用无需填写输入参数" /> : <div className="parameter-table-scroll"><table className="parameter-table">
      <thead><tr><th>参数名称</th><th>参数类型</th><th>参数值</th><th>描述</th></tr></thead>
      <tbody>{Object.entries(schema.properties ?? {}).map(([key, definition]) => {
        const field: RJSFSchema = typeof definition === "object" ? definition : {};
        const isDate = relativeDates && field.format === "date";
        return <tr key={key}><td><label htmlFor={`parameter-${key}_${key}`}><strong>{field.title || key}</strong></label>{schema.required?.includes(key) && <span className="required-mark"> *</span>}<small>{key}</small></td>
          <td>{field.format === "date" ? "日期" : typeNames[String(field.type)] || "参数"}</td>
          <td>{isDate ? <DateBindingField value={draft[key] as Binding | undefined} onChange={value => setDraft({ ...draft, [key]: value })} /> : field.type === "boolean" ? <Select id={`parameter-${key}_${key}`} aria-label={field.title || key} style={{ width: "100%" }} placeholder="请选择" allowClear value={draft[key] === undefined ? undefined : draft[key] ? "yes" : "no"} options={[{ label: "是", value: "yes" }, { label: "否", value: "no" }]} onChange={value => setDraft({ ...draft, [key]: value === undefined ? undefined : value === "yes" })} /> : <Form
            idPrefix={`parameter-${key}`} schema={{ ...schema, required: schema.required?.includes(key) ? [key] : [], properties: { [key]: { ...field, title: "", description: "" } } }}
            experimental_defaultFormStateBehavior={parameterFormBehavior}
            validator={validator} formData={{ [key]: draft[key] }} onChange={event => setDraft(old => ({ ...old, [key]: event.formData?.[key] }))}
            showErrorList={false} liveValidate={!!error} uiSchema={{ [key]: { "ui:title": field.title || key, "ui:label": false, "ui:placeholder": field.enum ? "请选择" : "请输入", ...(field.writeOnly ? { "ui:widget": "password" } : {}) } }}><></></Form>}</td>
          <td>{field.description || "—"}</td></tr>;
      })}</tbody>
    </table></div>}
  </Modal>;
}
