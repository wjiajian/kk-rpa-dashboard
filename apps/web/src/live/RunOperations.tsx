import { useEffect, useState } from "react";
import { Alert, App, Button, Descriptions, Empty, Image, Input, Modal, Space, Spin, Table, Tag } from "antd";
import { Link, useNavigate, useParams } from "react-router-dom";
import { PageTitle, Panel, StatusTag } from "../components/shared";
import { api, date, statuses, terminal, type RobotRecord, type RunEvent, type RunRecord } from "./api";
import { ExecutionLog } from "./ExecutionLog";
import { TokenUsage } from "./TokenUsage";

import { useResource } from "./useResource";
export function LiveDetail({ business }: { business: boolean }) {
  const { id } = useParams();
  const prefix = business ? "/business" : "";
  const { data: run, error } = useResource<RunRecord>(`${prefix}/runs/${id}`);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [streamError, setStreamError] = useState(false);
  const { message } = App.useApp();
  const navigate = useNavigate();
  useEffect(() => {
    setEvents([]);
    const stream = new EventSource(`/api${prefix}/runs/${id}/events`);
    stream.onopen = () => setStreamError(false);
    stream.onerror = () => setStreamError(true);
    stream.onmessage = event => {
      const incoming: RunEvent = JSON.parse(event.data);
      setEvents(old => old.some(e => e.seq === incoming.seq) ? old : [...old, incoming].sort((a, b) => b.at - a.at || b.seq - a.seq));
    };
    return () => stream.close();
  }, [id, prefix]);
  if (!run) return error ? <Alert type="error" message={error} /> : <Spin />;
  const manage = async (kind: "stop" | "rerun") => {
    try {
      const result = await api<{ id?: string }>(`/runs/${id}/${kind}`, {});
      if (kind === "rerun" && result.id) navigate(`/runs/${result.id}`);
      else void message.info("停止请求已记录，等待执行端确认。");
    } catch (error) { void message.error((error as Error).message); }
  };
  return <><PageTitle back title={run.name} description={run.id} actions={<Space><StatusTag status={statuses[run.status]} />{!business && (terminal(run.status) ? <Button onClick={() => void manage("rerun")}>从头重跑</Button> : <Button danger disabled={run.status === "stopping"} onClick={() => void manage("stop")}>{run.status === "queued" ? "取消排队" : "请求停止"}</Button>)}</Space>} />
    {(error || streamError) && <Alert type="warning" showIcon message={error || "事件连接中断，正在补读；当前显示最后收到的状态。"} />}
    {["uncertain", "stopping"].includes(run.status) && <Alert type="warning" showIcon message={run.status === "uncertain" ? "状态待确认，机器人继续由本次运行占用。" : "已请求协作停止，等待当前动作结束及执行端确认。"} />}
    {!business && <Panel title="运行与接管"><Descriptions className="panel-padding" column={2} items={[
      { key: "release", label: "应用 / 版本", children: `${run.snapshot?.app_id} · ${run.snapshot?.version}` },
      { key: "phase", label: "当前阶段", children: ({ queued: "排队", starting: "准备程序", program: "程序执行", failed: "失败现场", opening: "打开恢复上下文", recovery: "Agent 处理现场", submitting: "等待续跑确认", finishing: "确认收尾", ended: "已结束" } as Record<string, string>)[run.phase ?? ""] },
      { key: "budget", label: "本次运行接管剩余", children: run.remaining_seconds === undefined ? "—" : `${Math.ceil(run.remaining_seconds)} 秒 / 900 秒` },
      { key: "rounds", label: "接管轮数", children: `${run.recovery_rounds?.length ?? 0} / 3 轮` },
      { key: "tokens", label: "Agent Token 用量", children: <TokenUsage usage={run.token_usage} /> },
      { key: "inputs", label: "原业务参数", children: <code>{JSON.stringify(run.snapshot?.inputs)}</code> },
    ]} /></Panel>}
    {run.conclusion && <Panel title="接管结论"><div className="panel-padding"><p>{run.conclusion.reason}</p><p>已尝试：{run.conclusion.attempted.join("；") || "无"}</p><p>后续处理：{run.conclusion.next_actions.join("；") || "无"}</p></div></Panel>}
    <div className="detail-grid"><div><ExecutionLog events={events} business={business} /></div><div>
      {!business && <Panel title="执行尝试"><Table rowKey="id" pagination={false} dataSource={run.attempts} columns={[
        { title: "尝试", render: (_, attempt, index) => <div>第 {index + 1} 次<div className="small mono">{attempt.local_run_id}</div></div> },
        { title: "结果", dataIndex: "status", render: status => <StatusTag status={statuses[status] ?? status} /> },
      ]} /></Panel>}
      <Panel title="现场证据" extra={<Tag>仅保留最新截图</Tag>}><div className="panel-padding">{run.evidence?.[0] ? <Image key={run.evidence[0].id} src={run.evidence[0].url} alt="执行端最新现场截图" /> : <Empty description="尚未收到可用截图" />}</div></Panel>
    </div></div>
  </>;
}

export function LiveRobots() {
  const { data, error } = useResource<RobotRecord[]>("/robots");
  const [name, setName] = useState("");
  const [credential, setCredential] = useState("");
  const { message } = App.useApp();
  const call = async (path: string, body: unknown) => {
    try { const result = await api<{ credential?: string }>(path, body); if (result.credential) setCredential(result.credential); else void message.info("已记录，活跃运行将协作停止。"); }
    catch (error) { void message.error((error as Error).message); }
  };
  return <><PageTitle title="机器人" description="Windows 执行端主动连接；每台机器人同时执行一个运行。" />
    {error && <Alert type="error" message={error} />}
    <Panel><div className="panel-padding"><Space><Input aria-label="机器人名称" placeholder="机器人名称" value={name} onChange={e => setName(e.target.value)} /><Button disabled={!name.trim()} onClick={() => void call("/robots", { name })}>创建机器人</Button></Space></div>
      <Table rowKey="id" dataSource={data} columns={[
        { title: "机器人", dataIndex: "name" }, { title: "连接", render: (_, r) => r.revoked ? "凭据已撤销" : r.online ? "在线" : "离线" },
        { title: "当前占用", render: (_, r) => r.active_run ? <Link to={`/runs/${r.active_run}`}>查看运行</Link> : "无" },
        { title: "已部署版本", render: (_, r) => r.deployments.map(d => <div key={`${d.app_id}@${d.version}`}>{d.app_id} · {d.version}</div>) },
        { title: "凭据", render: (_, r) => <Space><Button onClick={() => void call(`/robots/${r.id}/rotate`, {})}>更换</Button><Button danger disabled={r.revoked} onClick={() => void call(`/robots/${r.id}/revoke`, {})}>撤销</Button></Space> },
      ]} />
    </Panel><Modal open={!!credential} title="机器人连接凭据" onCancel={() => setCredential("")} footer={<Button onClick={() => setCredential("")}>已保存</Button>}><p>仅本次显示。请保存到该机器人的私有环境变量中。</p><Input.TextArea readOnly value={credential} autoSize /></Modal>
  </>;
}
