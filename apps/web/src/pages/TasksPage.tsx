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
import { nextDates } from "../schedule/cron";
import { PageTitle, Panel } from "../components/shared";
export function useTrigger() {
  const { setRuns } = useStore();
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
          account: task.account,
          params: {
            target_date:
              task.date.kind === "fixed"
                ? task.date.value
                : "待执行端解析（演示）",
            brand: task.brand,
            export_filename: task.filename,
          },
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
  return (
    <>
      <PageTitle
        title="任务管理"
        description="为应用配置业务参数、执行机器人和定时计划。"
        actions={
          <Link to="/tasks/new">
            <Button type="primary" icon={<PlusOutlined />}>
              创建任务
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
          <span className="muted">共 {tasks.length} 个任务</span>
        </div>
        <Table
          rowKey="id"
          scroll={{ x: 1050 }}
          dataSource={tasks.filter(
            (t) => t.name.includes(search) && (!app || t.appId === app),
          )}
          pagination={{ pageSize: 8, showTotal: (n) => `共 ${n} 项` }}
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
            { title: "机器人", dataIndex: "robot" },
            {
              title: "定时计划",
              dataIndex: "cron",
              render: (c) => <code>{c}</code>,
            },
            {
              title: "下次触发",
              render: (_, t) =>
                t.enabled ? time(nextDates(t.cron)[0], "MM-DD HH:mm") : "—",
            },
            {
              title: "定时启用",
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
              render: (_, t) => (
                <Space>
                  <Link to={`/tasks/${t.id}/edit`}>编辑</Link>
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
    </>
  );
}
