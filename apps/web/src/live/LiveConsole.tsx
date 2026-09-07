import { useEffect, useState } from "react";
import { Alert, App, Button, Descriptions, Empty, Form, Image, Input, Modal, Select, Space, Spin, Table, Tag } from "antd";
import { Link, Navigate, NavLink, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { PageTitle, Panel, StatusTag } from "../components/shared";
import { api, date, statuses, terminal, type RobotRecord, type RunEvent, type RunRecord } from "./api";
import { ExecutionLog } from "./ExecutionLog";

function useResource<T>(path: string, interval = 3000) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const refresh = () => api<T>(path).then(value => { if (active) { setData(value); setError(""); } }).catch(error => { if (active) setError(error.message); });
    void refresh();
    const timer = setInterval(refresh, interval);
    return () => { active = false; clearInterval(timer); };
  }, [path, interval]);
  return { data, error };
}

export default function LiveConsole() {
  const { data: user, error } = useResource<{ name: string; admin: boolean }>("/me", 60000);
  if (error) return <div className="panel-padding"><PageTitle title="KK RPA 控制台" description={error} /><Button type="primary" href="/api/auth/feishu/login">企业飞书登录</Button></div>;
  if (!user) return <Spin fullscreen />;
  const prefix = user.admin ? "" : "/business";
  return <div className="shell">
    <aside className="sidebar"><Link to={`${prefix}/runs`} className="brand"><div><strong>KK RPA</strong><span>自动化控制台</span></div></Link>
      <nav><NavLink className="nav-item" to={`${prefix}/runs`}>运行记录</NavLink>{user.admin && <NavLink className="nav-item" to="/robots">机器人</NavLink>}</nav>
      <div className="sidebar-bottom"><div className="demo-note"><strong>执行环境</strong><p>运行状态来自执行端</p></div></div>
    </aside>
    <div className="main-shell"><header className="topbar"><span>失败接管控制台</span><Space><Tag>实时连接</Tag>{user.name} · {user.admin ? "管理员" : "只读成员"}</Space></header>
      <main><Routes>
        <Route path={`${prefix}/runs`} element={<LiveRuns business={!user.admin} />} />
        <Route path={`${prefix}/runs/:id`} element={<LiveDetail business={!user.admin} />} />
        {user.admin && <Route path="/robots" element={<LiveRobots />} />}
        <Route path="*" element={<Navigate replace to={`${prefix}/runs`} />} />
      </Routes></main>
    </div>
  </div>;
}

function LiveRuns({ business }: { business: boolean }) {
  const prefix = business ? "/business" : "";
  const { data, error } = useResource<RunRecord[]>(`${prefix}/runs`);
  const [creating, setCreating] = useState(false);
  return <><PageTitle title="运行记录" description="接管与续跑保留在原运行中。" actions={!business && <Button type="primary" onClick={() => setCreating(true)}>发起运行</Button>} />
    {error && <Alert type="error" message={error} />}
    <Panel><Table rowKey="id" dataSource={data} loading={!data && !error} columns={[
      { title: "运行", dataIndex: "name", render: (name, run) => <Link to={`${prefix}/runs/${run.id}`}>{name}</Link> },
      { title: "状态", dataIndex: "status", render: status => <StatusTag status={statuses[status] ?? status} /> },
      { title: "创建时间", dataIndex: "created", render: date },
      { title: "结束时间", dataIndex: "ended", render: date },
    ]} /></Panel>{!business && creating && <NewRun open={creating} close={() => setCreating(false)} />}</>;
}

function NewRun({ open, close }: { open: boolean; close: () => void }) {
  const { data: robots } = useResource<RobotRecord[]>("/robots", 10000);
  const [form] = Form.useForm();
  const robotId = Form.useWatch("robot_id", form);
  const robot = robots?.find(r => r.id === robotId);
  const [busy, setBusy] = useState(false);
  const { message } = App.useApp();
  const navigate = useNavigate();
  return <Modal open={open} title="发起应用运行" onCancel={close} confirmLoading={busy} okText="加入队列" onOk={async () => {
    try {
      const values = await form.validateFields();
      const release = robot?.deployments.find(d => `${d.app_id}@${d.version}` === values.release);
      if (!release) throw new Error("请选择已部署版本");
      const inputs = JSON.parse(values.inputs);
      if (!inputs || Array.isArray(inputs) || typeof inputs !== "object") throw new Error("业务参数必须是 JSON 对象");
      setBusy(true);
      const run = await api<{ id: string }>("/runs", { name: values.name, robot_id: values.robot_id, credentials: values.credentials,
        snapshot: { ...release, inputs, download_dir: values.download_dir || null } });
      form.resetFields(); close(); navigate(`/runs/${run.id}`);
    } catch (error) { if (error instanceof Error) void message.error(error.message); }
    finally { setBusy(false); }
  }}>
    <Form form={form} layout="vertical" clearOnDestroy initialValues={{ inputs: "{}" }}>
      <Form.Item name="name" label="运行名称" rules={[{ required: true }]}><Input /></Form.Item>
      <Form.Item name="robot_id" label="机器人" rules={[{ required: true }]}><Select options={robots?.filter(r => !r.revoked).map(r => ({ value: r.id, label: `${r.name} · ${r.online ? "在线" : "离线"}` }))} onChange={() => form.setFieldValue("release", undefined)} /></Form.Item>
      <Form.Item name="release" label="已部署应用 / 版本" rules={[{ required: true }]}><Select options={robot?.deployments.map(d => ({ value: `${d.app_id}@${d.version}`, label: `${d.app_id} · ${d.version}` }))} /></Form.Item>
      <Form.Item name={["credentials", "username"]} label="业务登录账号" rules={[{ required: true }]}><Input autoComplete="off" /></Form.Item>
      <Form.Item name={["credentials", "password"]} label="业务登录密码" rules={[{ required: true }]}><Input.Password autoComplete="new-password" /></Form.Item>
      <Form.Item name={["credentials", "expected_identity"]} label="登录后预期可见身份" extra="用于核对登录后的店铺或账号身份。账号密码随本次运行保存，从头重跑沿用。" rules={[{ required: true }]}><Input autoComplete="off" /></Form.Item>
      <Form.Item name="inputs" label="实际业务参数（JSON）" extra="填写应用要求的字段和实际日期。" rules={[{ required: true }]}><Input.TextArea rows={5} /></Form.Item>
      <Form.Item name="download_dir" label="下载目录（可选）"><Input /></Form.Item>
    </Form>
  </Modal>;
}

function LiveDetail({ business }: { business: boolean }) {
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
      { key: "source", label: "来源运行", children: run.rerun_of ? <Link to={`/runs/${run.rerun_of}`}>{run.rerun_of}</Link> : "—" },
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

function LiveRobots() {
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
