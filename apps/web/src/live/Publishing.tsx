import { useState } from "react";
import { Alert, Button, Checkbox, Form, Input, Modal, Select, Space, Table, Tag } from "antd";
import { PageTitle, Panel } from "../components/shared";
import { api, type RobotRecord } from "./api";
import { useResource } from "./useResource";
import { ApplicationList } from "./WorkspacePages";

type Source = { id: string; name: string; url: string; credentials_configured: boolean };
type Application = { id: string; app_id: string; name: string; source_id: string };
type Release = { id: string; app_id: string; version: string; commit: string; name: string };
type ImportJob = { id: string; status: string; ref: string; commit?: string; error?: string; applications?: { app_id: string; name: string; version?: string; error?: string; input_schema?: { properties?: Record<string, { title?: string }> } }[] };
type Job = { id: string; release_id: string; status: string; action: string; stage?: string; error?: string };
type DeploymentState = { deployments: { release_id: string; status: string }[]; jobs: Job[] };
const states: Record<string, string> = { queued: "排队中", fetching: "获取源码", ready: "待确认", confirmed: "已导入", failed: "失败", installing: "安装处理中", installed: "已安装", uninstalled: "已卸载", uncertain: "状态待确认" };

export default function Publishing() {
  const sources = useResource<Source[]>("/application-sources", 10000);
  const imports = useResource<ImportJob[]>("/application-imports", 3000);
  const applications = useResource<Application[]>("/applications", 5000);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [sourceForm] = Form.useForm();
  const [sourceId, setSourceId] = useState<string>();
  const [ref, setRef] = useState("");
  const [selected, setSelected] = useState<Record<string, string[]>>({});
  const [appId, setAppId] = useState<string>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const execute = async (work: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(true); setError("");
    try { await work(); sources.refresh(); imports.refresh(); applications.refresh(); }
    catch (error) { setError((error as Error).message); }
    finally { setBusy(false); }
  };
  return <><PageTitle title="应用发布" description="从固定 Git commit 导入应用，安装到指定机器人后使用。" actions={<Button onClick={() => setSourceOpen(true)}>添加 Git 来源</Button>} />
    {(error || sources.error || imports.error || applications.error) && <Alert className="mb" type="error" message={error || sources.error || imports.error || applications.error} />}
    <Panel title="导入应用"><div className="panel-padding"><Space wrap><Select aria-label="Git 来源" placeholder="选择 Git 来源" value={sourceId} style={{ minWidth: 220 }} options={sources.data?.map(s => ({ value: s.id, label: s.name }))} onChange={setSourceId} />
      <Input aria-label="Git 引用" placeholder="分支、tag 或 commit" value={ref} onChange={e => setRef(e.target.value)} />
      <Button type="primary" disabled={!sourceId || !ref.trim() || busy} loading={busy} onClick={() => void execute(() => api("/application-imports", { source_id: sourceId, ref: ref.trim() }))}>获取并预览</Button></Space></div>
      <Table rowKey="id" dataSource={imports.data} pagination={{ pageSize: 5 }} columns={[
        { title: "引用", dataIndex: "ref" }, { title: "Commit", render: (_, job: ImportJob) => job.commit?.slice(0, 12) || "—" },
        { title: "状态", render: (_, job: ImportJob) => <><Tag>{states[job.status] || job.status}</Tag>{job.error && <div>{job.error}</div>}</> },
        { title: "应用预览", render: (_, job: ImportJob) => job.applications?.map(app => <div key={app.app_id}><Checkbox disabled={!!app.error || job.status === "confirmed" || busy} checked={selected[job.id]?.includes(app.app_id)} onChange={e => setSelected(old => ({ ...old, [job.id]: e.target.checked ? [...(old[job.id] || []), app.app_id] : (old[job.id] || []).filter(id => id !== app.app_id) }))}>{app.name} · {app.version}</Checkbox>
          {app.error ? <div className="muted">{app.error}</div> : <div className="muted">参数：{Object.entries(app.input_schema?.properties || {}).map(([key, field]) => field.title || key).join("、") || "无"}</div>}</div>) || "—" },
        { title: "操作", render: (_, job: ImportJob) => <Button disabled={busy || job.status !== "ready" || !selected[job.id]?.length} onClick={() => void execute(() => api(`/application-imports/${job.id}/confirm`, { app_ids: selected[job.id] }))}>确认导入</Button> },
      ]} /></Panel>
    <Panel title="发布版本"><div className="panel-padding"><Select aria-label="已导入应用" placeholder="选择已导入应用" value={appId} style={{ minWidth: 300 }} options={applications.data?.map(a => ({ value: a.id, label: `${a.name} · ${sources.data?.find(s => s.id === a.source_id)?.name || a.source_id}` }))} onChange={setAppId} /></div>{appId && <ReleaseDeployment key={appId} appId={appId} />}</Panel>
    <ApplicationList />
    {sourceOpen && <Modal open title="添加 Git 来源" confirmLoading={busy} okText="保存来源" cancelText="取消" onCancel={() => setSourceOpen(false)} onOk={() => void execute(async () => {
      const values = await sourceForm.validateFields();
      const credentials = Object.fromEntries(Object.entries({ username: values.username, token: values.token, ssh_private_key: values.ssh_private_key }).filter(([, v]) => v));
      await api("/application-sources", { name: values.name, url: values.url, ...(Object.keys(credentials).length ? { credentials } : {}) });
      sourceForm.resetFields(); setSourceOpen(false);
    })}><Form form={sourceForm} layout="vertical"><Form.Item name="name" label="来源名称" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item>
      <Form.Item name="url" label="Git URL" rules={[{ required: true }]}><Input placeholder="https:// 或 ssh://，不包含口令" /></Form.Item>
      <Form.Item name="username" label="HTTPS 账号（可选）"><Input autoComplete="off" /></Form.Item>
      <Form.Item name="token" label="HTTPS 只读令牌（可选）"><Input.Password autoComplete="new-password" /></Form.Item>
      <Form.Item name="ssh_private_key" label="SSH 只读部署密钥（可选）"><Input.TextArea autoComplete="off" rows={3} /></Form.Item>
      <p className="muted">私有凭据仅保存在服务端。SSH 主机指纹需要由部署管理员配置。</p>
    </Form></Modal>}
  </>;
}

function ReleaseDeployment({ appId }: { appId: string }) {
  const releases = useResource<Release[]>(`/applications/${appId}/releases`);
  const robots = useResource<RobotRecord[]>("/robots");
  const [robotId, setRobotId] = useState<string>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const deployment = useResource<DeploymentState>(robotId ? `/robots/${robotId}/deployments` : null);
  const act = async (release: Release, remove: boolean) => {
    if (!robotId || busy) return;
    setBusy(true); setError("");
    try {
      await api(`/robots/${robotId}/deployments${remove ? "/" + release.id : ""}`, remove ? undefined : { release_id: release.id }, remove ? "DELETE" : "POST");
      deployment.refresh(); robots.refresh();
    } catch (error) { setError((error as Error).message); }
    finally { setBusy(false); }
  };
  const releaseState = (release: Release) => {
    const pending = deployment.data?.jobs.find(job => job.release_id === release.id && ["queued", "installing", "uncertain"].includes(job.status));
    const installed = deployment.data?.deployments.some(row => row.release_id === release.id && row.status === "installed");
    return { pending, installed };
  };
  return <div className="panel-padding">{(error || releases.error || robots.error || deployment.error) && <Alert className="mb" type="error" message={error || releases.error || robots.error || deployment.error} />}
    <Select aria-label="部署机器人" placeholder="选择部署机器人" value={robotId} style={{ minWidth: 260 }} onChange={setRobotId} options={robots.data?.filter(r => !r.revoked).map(r => ({ value: r.id, label: `${r.name} · ${r.online ? "在线" : "离线"}`, disabled: !r.capabilities?.includes("deploy-v1") }))} />
    <Table rowKey="id" dataSource={releases.data} columns={[
      { title: "版本", dataIndex: "version" }, { title: "Commit", render: (_, release: Release) => release.commit.slice(0, 12) },
      { title: "机器人部署状态", render: (_, release: Release) => {
        const { pending, installed } = releaseState(release);
        return !robotId ? "请选择机器人" : !deployment.data ? "读取中" : <Tag>{pending ? `${pending.action === "uninstall" ? "卸载" : "安装"} · ${states[pending.status]}` : installed ? "已安装" : "未安装"}</Tag>;
      } },
      { title: "操作", render: (_, release: Release) => {
        const { pending, installed } = releaseState(release);
        const unavailable = !deployment.data || !!deployment.error || busy || !!pending;
        return <Space><Button disabled={unavailable || !!installed} onClick={() => void act(release, false)}>{installed ? "已安装" : "安装到机器人"}</Button><Button disabled={unavailable || !installed} onClick={() => void act(release, true)}>卸载</Button></Space>;
      } },
    ]} pagination={false} />
    {robotId && <DeploymentHistory jobs={deployment.data?.jobs.filter(job => releases.data?.some(release => release.id === job.release_id))} />}
  </div>;
}
function DeploymentHistory({ jobs }: { jobs?: Job[] }) {
  return <Table rowKey="id" dataSource={jobs} pagination={{ pageSize: 5 }} columns={[
    { title: "部署作业", dataIndex: "id" }, { title: "操作", render: (_, job: Job) => job.action === "install" ? "安装" : "卸载" },
    { title: "状态", render: (_, job: Job) => <><Tag>{states[job.status] || job.status}</Tag>{job.status === "uncertain" && <div>请在执行机确认安装进程已停止，按本作业 ID 完成本地收尾后重连。</div>}</> },
    { title: "阶段", dataIndex: "stage" }, { title: "错误", dataIndex: "error" },
  ]} />;
}
