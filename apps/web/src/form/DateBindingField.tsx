import { DatePicker, InputNumber, Segmented, Space } from "antd";
import dayjs from "dayjs";
import type { Binding } from "../mock/data";
export const defaultDate: Binding = { kind: "relative_date", offset_days: -1 };
export function DateBindingField({
  value = defaultDate,
  onChange,
}: {
  value?: Binding;
  onChange: (v: Binding) => void;
}) {
  return (
    <div>
      <Segmented
        value={value.kind}
        options={[
          { label: "相对日期", value: "relative_date" },
          { label: "固定日期", value: "fixed" },
        ]}
        onChange={(v) =>
          onChange(v === "fixed" ? { kind: "fixed", value: "" } : defaultDate)
        }
      />
      <div className="field-gap">
        {value.kind === "fixed" ? (
          <DatePicker
            aria-label="固定业务日期"
            value={value.value ? dayjs(value.value) : null}
            onChange={(d) =>
              onChange({ kind: "fixed", value: d?.format("YYYY-MM-DD") || "" })
            }
          />
        ) : (
          <Space>
            今天
            <InputNumber
              aria-label="日期偏移天数"
              precision={0}
              value={value.offset_days}
              onChange={(n) =>
                onChange({ kind: "relative_date", offset_days: n ?? 0 })
              }
            />
            天
          </Space>
        )}
      </div>
      <small className="muted">生成运行时解析为实际日期</small>
    </div>
  );
}
