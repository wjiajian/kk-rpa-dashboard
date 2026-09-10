import { useState } from "react";
import { Alert, Button, Input, Select, Space, Table, Tag } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { PageTitle, Panel } from "../components/shared";
import { date, type AuditRecord, type PageResult } from "./api";
import { useResource } from "./useResource";

const actionLabels: Record<string, string> = {
  "robot.create": "创建机器人", "robot.revoke": "停用机器人", "robot.rotate": "更新机器人凭据",
  "run.create": "发起临时运行", "run.rerun": "重新运行", "run.stop": "停止运行",
  "task.create": "创建计划", "task.update": "修改计划", "task.schedule": "修改定时",
  "task.trigger": "立即运行计划", "source.create": "创建代码来源",
  "release.import": "导入版本", "release.confirm": "确认发布版本",
  "release.install": "安装版本", "release.uninstall": "卸载版本",
};

const actionOptions = Object.entries(actionLabels).map(([value, label]) => ({ value, label }));
const targetLabels: Record<string, string> = {
  robot: "机器人", run: "运行", task: "计划", release: "版本",
  application_source: "代码来源", application_import: "版本导入",
};
const detailLabels: Record<string, string> = {
  name: "名称", robot_id: "机器人", app_id: "应用", version: "版本", release_id: "发布版本",
  run_id: "运行", new_run_id: "新运行", source_id: "代码来源", ref: "Git 引用", app_ids: "应用",
  job_id: "部署作业", enabled: "启用定时",
};

function details(value: Record<string, unknown>) {
  const entries = Object.entries(value).filter(([, item]) => item !== null && item !== undefined && item !== "");
  return entries.length ? entries.map(([key, item]) => `${detailLabels[key] || key}: ${Array.isArray(item) ? item.join("、") : String(item)}`).join("；") : "—";
}

export default function AuditLog() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [search, setSearch] = useState("");
  const [action, setAction] = useState<string>();
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (search.trim()) query.set("q", search.trim());
  if (action) query.set("action", action);
  const { data, error, refresh } = useResource<PageResult<AuditRecord>>(`/audit-logs?${query}`, 10000);
  return <><PageTitle title="操作审计" description="记录管理员在控制台执行的关键操作，不保存密码和 Token。"
    actions={<Button icon={<ReloadOutlined />} onClick={refresh}>刷新</Button>} />
    {error && <Alert type="error" showIcon message={error} className="mb" />}
    <Panel><div className="filter-bar"><Input aria-label="操作人或对象编号" placeholder="搜索操作人或对象编号" value={search}
      onChange={event => { setSearch(event.target.value); setPage(1); }} allowClear />
      <Select aria-label="操作类型" placeholder="全部操作" value={action} allowClear options={actionOptions}
        onChange={value => { setAction(value); setPage(1); }} /></div>
      <Table rowKey="id" loading={!data && !error} dataSource={data?.items} scroll={{ x: 1050 }} pagination={{
        current: page, pageSize, total: data?.total || 0, showSizeChanger: true,
        showTotal: total => `共 ${total} 条`, onChange: (next, size) => { setPage(next); setPageSize(size); },
      }} columns={[
        { title: "操作时间", dataIndex: "created", width: 190, render: date },
        { title: "操作人", render: (_, row) => <><strong>{row.actor_name}</strong><div className="muted small mono">{row.actor_open_id}</div></> },
        { title: "操作", dataIndex: "action", render: value => actionLabels[value] || value },
        { title: "对象", render: (_, row) => <><span>{targetLabels[row.target_type] || row.target_type}</span><div className="muted small mono">{row.target_id}</div></> },
        { title: "结果", render: () => <Tag color="green">已接受</Tag> },
        { title: "说明", dataIndex: "details", ellipsis: true, render: details },
      ]} />
    </Panel>
  </>;
}
