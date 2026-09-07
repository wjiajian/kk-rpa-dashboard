import { useState } from "react";
import { App, Button, Modal, Select } from "antd";
import type { Application } from "../mock/data";
import { useStore } from "../mock/store";

export function ApplicationTagEditor({
  application,
}: {
  application: Application;
}) {
  const { apps, setApps } = useStore();
  const { message } = App.useApp();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const options = [...new Set(apps.flatMap((app) => app.tags))].map((tag) => ({
    label: tag,
    value: tag,
  }));
  const save = () => {
    const tags = [
      ...new Set([...draft, input].map((tag) => tag.trim()).filter(Boolean)),
    ];
    setApps((old) =>
      old.map((app) => (app.id === application.id ? { ...app, tags } : app)),
    );
    setOpen(false);
    message.success("标签已保存");
  };
  return (
    <>
      <Button
        type="link"
        size="small"
        onClick={() => {
          setDraft([...application.tags]);
          setInput("");
          setOpen(true);
        }}
      >
        编辑标签
      </Button>
      <Modal
        title={`编辑标签 · ${application.name}`}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={save}
        okText="保存标签"
        cancelText="取消"
      >
        <p className="muted">
          选择已有标签，或输入新标签后按回车。点击标签上的 ×
          可移除，支持清空全部标签。
        </p>
        <Select<string[]>
          mode="tags"
          aria-label="应用标签"
          style={{ width: "100%" }}
          placeholder="选择或输入标签"
          value={draft}
          onChange={(value) => {
            setDraft(value);
            setInput("");
          }}
          searchValue={input}
          onSearch={setInput}
          options={options}
          allowClear
          onClear={() => {
            setDraft([]);
            setInput("");
          }}
        />
        <p className="muted small" style={{ marginTop: 16 }}>
          当前为演示数据，刷新页面后恢复初始标签。
        </p>
      </Modal>
    </>
  );
}
