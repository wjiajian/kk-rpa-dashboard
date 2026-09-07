import Form from "@rjsf/antd";
import validator from "@rjsf/validator-ajv8";
import type { RJSFSchema } from "@rjsf/utils";
const schema: RJSFSchema = {
  type: "object",
  required: ["brand", "filename"],
  properties: {
    brand: {
      type: "string",
      title: "品牌范围",
      enum: ["全部品牌", "品牌 A", "品牌 B"],
      default: "全部品牌",
    },
    filename: {
      type: "string",
      title: "导出文件名",
      minLength: 1,
      pattern: "^[^/\\\\]+\\.xlsx$",
      default: "report.xlsx",
    },
  },
};
export function SchemaForm({
  data,
  onChange,
  readonly = false,
}: {
  data: { brand: string; filename: string };
  onChange?: (v: { brand: string; filename: string }) => void;
  readonly?: boolean;
}) {
  return (
    <Form
      schema={schema}
      validator={validator}
      formData={data}
      onChange={(e) => onChange?.(e.formData)}
      readonly={readonly}
      liveValidate
      showErrorList={false}
      uiSchema={{ "ui:submitButtonOptions": { norender: true } }}
    >
      <></>
    </Form>
  );
}
