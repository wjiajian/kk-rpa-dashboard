import { useState } from "react";
import { App, Button, Input, Select, Space, Switch, Table } from "antd";
import {
  PlusOutlined,
  SearchOutlined,
  PlayCircleOutlined,
} from "@ant-design/icons";
import { Link, useNavigate } from "react-router-dom";
import { useStore } from "../mock/store";
import { type Task, type Run, time } from "../mock/data";
import { taskParameters } from "../form/parameters";
import { robots } from "../mock/data";
import { nextDates } from "../schedule/cron";
import { PageTitle, Panel } from "../components/shared";
export function useTrigger() {
  const { setRuns, apps } = useStore();
  const { modal, message } = App.useApp();
  const navigate = useNavigate();
  return (task: Task) =>
    modal.confirm({
      title: `立即运行「${task.name}」？`,
      content: "使用最新保存的任务配置创建一条模拟运行，真实机器人不会执行。",
      okText: "立即运行",
      onOk: () => {
        const id = `RUN-${crypto.randomUUID().slice(0, 8)}`;
        const run: Run = {
          id,
          taskId: task.id,
          name: task.name,
          appId: task.appId,
          version: task.version,
          robot: task.robot,
          params: Object.fromEntries(Object.entries(apps.find(a => a.id === task.appId)?.inputSchema ? taskParameters(task, apps.find(a => a.id === task.appId)!.inputSchema!) : {}).map(([key, value]) => [key,
            value && typeof value === "object" && "kind" in value ? (value.kind === "fixed" && "value" in value ? String(value.value) : "待执行端解析（演示）") : typeof value === "object" ? JSON.stringify(value) : String(value ?? "")
          ])),
          status: "排队中",
          source: "手动",
          created: new Date().toISOString(),
          duration: "—",
          progress: 0,
        };
        setRuns((old) => [run, ...old]);
        message.success("模拟运行已加入队列");
        navigate(`/runs/${id}`);
      },
    });
}
export default function TasksPage() {
  const { tasks, apps, saveTask } = useStore();
  const trigger = useTrigger();
  const [search, setSearch] = useState("");
  const [app, setApp] = useState<string>();
  const [enabled, setEnabled] = useState<boolean>();
  const [robot, setRobot] = useState<string>();
  return (
    <div className="task-plans">
      <PageTitle
        title="常规任务计划"
        description="管理应用的执行参数与定时安排。"
        actions={
          <Link to="/tasks/new">
            <Button type="primary" icon={<PlusOutlined />}>
              新建常规任务
            </Button>
          </Link>
        }
      />
      <Panel>
        <div className="filter-bar">
          <Input
            prefix={<SearchOutlined />}
            placeholder="搜索任务名称"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            allowClear
          />
          <Select
            placeholder="全部应用"
            allowClear
            value={app}
            onChange={setApp}
            options={apps.map((a) => ({ label: a.name, value: a.id }))}
          />
          <Select aria-label="启用状态" placeholder="全部状态" allowClear value={enabled} onChange={setEnabled} options={[{ label: "已启用", value: true }, { label: "未启用", value: false }]} />
          <Select aria-label="执行机器人" placeholder="全部机器人" allowClear value={robot} onChange={setRobot} options={robots.map(r => ({ label: r.name, value: r.id }))} />
        </div>
        <Table
          rowKey="id"
          scroll={{ x: 1050 }}
          dataSource={tasks.filter(
            (t) => t.name.includes(search) && (!app || t.appId === app) && (enabled === undefined || t.enabled === enabled) && (!robot || t.robot === robot),
          )}
          pagination={{ defaultPageSize: 10, showSizeChanger: true, showTotal: (n) => `共 ${n} 条` }}
          columns={[
            {
              title: "任务名称",
              render: (_, t) => (
                <Link to={`/tasks/${t.id}/edit`}>
                  <strong>{t.name}</strong>
                  <div className="muted mono small">{t.id}</div>
                </Link>
              ),
            },
            {
              title: "应用 / 版本",
              render: (_, t) => (
                <>
                  {apps.find((a) => a.id === t.appId)?.name}
                  <div className="muted small">v{t.version}</div>
                </>
              ),
            },
            { title: "执行机器人", render: (_, t) => robots.find(r => r.id === t.robot)?.name || t.robot },
            {
              title: "触发方式",
              render: (_, t) => t.enabled ? "计划触发" : "手动触发",
            },
            {
              title: "执行时间",
              render: (_, t) =>
                t.enabled ? time(nextDates(t.cron)[0], "YYYY-MM-DD HH:mm:ss") : "—",
            },
            {
              title: "启用状态",
              render: (_, t) => (
                <Switch
                  aria-label={`${t.name}定时启用`}
                  checked={t.enabled}
                  onChange={(v) => saveTask({ ...t, enabled: v })}
                />
              ),
            },
            {
              title: "操作",
              fixed: "right",
              width: 235,
              render: (_, t) => (
                <Space>
                  <Link to={`/tasks/${t.id}/edit`}>编辑</Link><Link to={`/runs?task=${t.id}`}>记录</Link>
                  <Button
                    type="link"
                    icon={<PlayCircleOutlined />}
                    onClick={() => trigger(t)}
                  >
                    立即运行
                  </Button>
                </Space>
              ),
            },
          ]}
        />
      </Panel>
    </div>
  );
}
