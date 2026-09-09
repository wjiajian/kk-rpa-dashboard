import { useRef, useState } from "react";
import { Alert, Button, Space, Spin, Table, Tag } from "antd";
import { Link, useParams } from "react-router-dom";
import { PageTitle, Panel } from "../components/shared";
import { api, date, type TaskRecord } from "./api";
import { useResource } from "./useResource";
import NewTask from "./NewTask";

export function TaskPlans() {
  const { data, error, refresh } = useResource<TaskRecord[]>("/tasks");
  const [operationError, setOperationError] = useState("");
  const [busy, setBusy] = useState<string>();
  const requests = useRef(new Map<string, string>());
  const act = async (task: TaskRecord, run: boolean) => {
    if (busy) return;
    setBusy(task.id); setOperationError("");
    try {
      if (run) {
        const request_id = requests.current.get(task.id) || crypto.randomUUID();
        requests.current.set(task.id, request_id);
        await api(`/tasks/${task.id}/runs`, { request_id });
        requests.current.delete(task.id);
      } else await api(`/tasks/${task.id}/schedule`, { ...task.schedule, enabled: !task.schedule.enabled, revision: task.revision }, "PUT");
      refresh();
    } catch (error) { setOperationError((error as Error).message); }
    finally { setBusy(undefined); }
  };
  return <><PageTitle title="任务管理" description="保存可复用计划；每次触发产生独立运行。" actions={<Space><Link to="/runs/new"><Button>临时运行</Button></Link><Link to="/tasks/new"><Button type="primary">新建计划</Button></Link></Space>} />
    {(error || operationError) && <Alert className="mb" type="error" message={error || operationError} />}
    <Panel><Table rowKey="id" loading={!data && !error} dataSource={data} scroll={{ x: 1000 }} columns={[
      { title: "计划名称", render: (_, task: TaskRecord) => <Link to={`/tasks/${task.id}`}>{task.name}</Link> },
      { title: "应用版本", render: (_, task: TaskRecord) => <>{task.app_id}<div className="muted">{task.version}{task.commit ? ` · ${task.commit.slice(0, 8)}` : task.release_id ? ` · ${task.release_id}` : ""}</div></> },
      { title: "机器人", dataIndex: "robot_id" },
      { title: "定时", render: (_, task: TaskRecord) => <><Tag color={task.schedule.enabled ? "blue" : "default"}>{task.schedule.enabled ? "已启用" : "未启用"}</Tag>{task.last_error && <div className="muted">{task.last_error}</div>}</> },
      { title: "下次触发（上海）", dataIndex: "next_run_at", render: date },
      { title: "最近运行", render: (_, task: TaskRecord) => task.last_run_id ? <Link to={`/runs/${task.last_run_id}`}>查看运行</Link> : "—" },
      { title: "操作", render: (_, task: TaskRecord) => <Space><Button disabled={!!busy} loading={busy === task.id} onClick={() => void act(task, true)}>立即运行</Button><Button disabled={!!busy} onClick={() => void act(task, false)}>{task.schedule.enabled ? "暂停定时" : "启用定时"}</Button></Space> },
    ]} /></Panel></>;
}

export function EditPlan() {
  const { id } = useParams();
  const { data, error } = useResource<TaskRecord>(`/tasks/${id}`, 60000);
  return error ? <Alert type="error" message={error} /> : !data ? <Spin /> : <NewTask key={data.id} plan task={data} />;
}
