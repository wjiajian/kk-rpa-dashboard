import { useState } from "react";
import { DatePicker, InputNumber, Segmented, Space } from "antd";
import dayjs from "dayjs";
import type { Binding } from "../mock/data";
export const defaultDate: Binding = { kind: "relative_date", offset_days: -1 };
export function DateBindingField({
  value,
  onChange,
}: {
  value?: Binding;
  onChange: (v: Binding | undefined) => void;
}) {
  const [mode, setMode] = useState<Binding["kind"]>(value?.kind || "fixed");
  return (
    <div>
      <Segmented
        value={value?.kind || mode}
        options={[
          { label: "相对日期", value: "relative_date" },
          { label: "固定日期", value: "fixed" },
        ]}
        onChange={(v) => { setMode(v as Binding["kind"]); onChange(undefined); }}
      />
      <div className="field-gap">
        {(value?.kind || mode) === "fixed" ? (
          <DatePicker
            aria-label="固定业务日期"
            value={value?.kind === "fixed" && value.value ? dayjs(value.value) : null}
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
              placeholder="请输入偏移天数"
              value={value?.kind === "relative_date" ? value.offset_days : null}
              onChange={(n) =>
                onChange(n === null ? undefined : { kind: "relative_date", offset_days: n })
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
