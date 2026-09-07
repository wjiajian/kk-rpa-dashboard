import { Tag, Button, Empty } from "antd";
import { ArrowLeftOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
export function StatusTag({ status }: { status: string }) {
  const colors: Record<string, string> = {
    成功: "green",
    空闲: "green",
    失败: "red",
    运行中: "blue",
    启动中: "blue",
    排队中: "orange",
    "Agent 接管中": "purple",
    停止中: "orange",
    状态待确认: "orange",
  };
  return (
    <Tag bordered={false} color={colors[status] || "default"}>
      <span className="status-dot" />
      {status}
    </Tag>
  );
}
export function PageTitle({
  title,
  description,
  actions,
  back,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  back?: boolean;
}) {
  const navigate = useNavigate();
  return (
    <div className="page-title">
      <div>
        {back && (
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate(-1)}
          >
            返回
          </Button>
        )}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      <div className="page-actions">{actions}</div>
    </div>
  );
}
export function Panel({
  title,
  extra,
  children,
  className = "",
}: {
  title?: ReactNode;
  extra?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {title && (
        <div className="panel-head">
          <h2>{title}</h2>
          {extra}
        </div>
      )}
      {children}
    </section>
  );
}
export function NotFound() {
  return <Empty description="没有找到这条记录，请从列表重新选择" />;
}
