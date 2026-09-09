import { useState } from "react";
import { Alert, Button, Empty, Input, Select, Space, Table, Tag } from "antd";
import { AppstoreOutlined, PlayCircleOutlined, PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { Link, useSearchParams } from "react-router-dom";
import { PageTitle, Panel, StatusTag } from "../components/shared";
import { date, statuses, terminal, type RobotRecord, type RunRecord } from "./api";
import { useResource } from "./useResource";
import { deployedApplications, inputSchemaFor, releaseKey } from "./deployments";

export function RunList({ business = false, tasks = false }: { business?: boolean; tasks?: boolean }) {
  const prefix = business ? "/business" : "";
  const { data, error, refresh } = useResource<RunRecord[]>(`${prefix}/runs`);
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [app, setApp] = useState<string>();
  const status = params.get("status") || undefined;
  const apps = [...new Set(data?.flatMap(r => r.snapshot ? [r.snapshot.app_id] : []) || [])];
  const filtered = data?.filter(r => r.name.includes(search) && (!status || r.status === status) && (!app || r.snapshot?.app_id === app));
  return <div className="task-plans"><PageTitle title={tasks ? "任务管理" : business ? "业务运行" : "运行记录"} description="查看已提交任务的实际执行状态；列表显示最近 500 次运行。"
    actions={<Space><Button icon={<ReloadOutlined />} aria-label="刷新运行记录" onClick={refresh} />{!business && <Link to="/runs/new"><Button type="primary" icon={<PlusOutlined />}>临时运行</Button></Link>}</Space>} />
    {error && <Alert type="error" showIcon message={error} className="mb" />}
    <Panel><div className="filter-bar"><Input aria-label="任务名称" placeholder="搜索任务名称" value={search} onChange={e => setSearch(e.target.value)} allowClear />
      <Select aria-label="运行状态" placeholder="全部状态" allowClear value={status} onChange={value => setParams(value ? { status: value } : {})} options={Object.entries(statuses).map(([value, label]) => ({ value, label }))} />
      {!business && <Select aria-label="应用" placeholder="全部应用" value={app} allowClear onChange={setApp} options={apps.map(value => ({ value, label: value }))} />}
    </div><Table rowKey="id" loading={!data && !error} dataSource={filtered} scroll={{ x: business ? 700 : 1050 }} pagination={{ defaultPageSize: 10, showSizeChanger: true, showTotal: n => `共 ${n} 条` }} columns={[
      { title: "任务名称", render: (_, r) => <Link to={`${prefix}/runs/${r.id}`}><strong>{r.name}</strong><div className="muted small mono">{r.id}</div></Link> },
      ...(!business ? [{ title: "执行应用", render: (_: unknown, r: RunRecord) => <>{r.snapshot?.app_id || "—"}<div className="muted small">{r.snapshot?.version}</div></> }, { title: "执行机器人", dataIndex: "robot_id" }] : []),
      { title: "运行状态", dataIndex: "status", render: status => <StatusTag status={statuses[status] || status} /> },
      { title: "创建时间", dataIndex: "created", render: date },
      { title: "结束时间", dataIndex: "ended", render: date },
      { title: "操作", fixed: "right", width: 110, render: (_, r) => <Link to={`${prefix}/runs/${r.id}`}>查看详情</Link> },
    ]} /></Panel></div>;
}

export function ApplicationList() {
  const { data, error, refresh } = useResource<RobotRecord[]>("/robots", 10000);
  const [search, setSearch] = useState("");
  const apps = deployedApplications(data || []).filter(a => a.app_id.includes(search));
  return <><PageTitle title="应用中心" description="查看机器人已部署的程序与版本。" actions={<Button icon={<ReloadOutlined />} onClick={refresh}>刷新</Button>} />
    {error && <Alert type="error" showIcon message={error} className="mb" />}
    <div className="filter-bar standalone"><Input placeholder="搜索应用名称" aria-label="搜索应用" value={search} onChange={e => setSearch(e.target.value)} allowClear /></div>
    {data && !apps.length && <Empty description="暂无已部署应用，请先连接机器人并部署程序" />}
    <div className="application-grid">{apps.map(app => <Panel key={releaseKey(app)} className="application-card"><div className="app-icon"><AppstoreOutlined /></div>
      <h2>{app.app_id}</h2><Tag>v{app.version}{app.commit ? " · " + app.commit.slice(0, 8) : ""}</Tag><p>{app.robots.map(r => r.name).join("、")}</p>
      <div className="app-meta">{inputSchemaFor(app) ? `${Object.keys(inputSchemaFor(app)?.properties || {}).length} 个参数` : app.schema_status === "invalid" ? "参数声明损坏" : "尚未上报参数表单"}<span>{app.robots.filter(r => r.online).length} 台在线</span></div>
      <div className="card-actions"><Link to="/runs/new">创建任务</Link><Link to="/robots">查看机器人</Link></div>
    </Panel>)}</div></>;
}

export function WorkspaceOverview() {
  const runs = useResource<RunRecord[]>("/runs");
  const robots = useResource<RobotRecord[]>("/robots");
  const metrics = [
    { label: "运行中", value: runs.data?.filter(r => !terminal(r.status) && r.status !== "queued").length, to: "/runs" },
    { label: "排队中", value: runs.data?.filter(r => r.status === "queued").length, to: "/runs?status=queued" },
    { label: "失败运行", value: runs.data?.filter(r => r.status === "failed").length, to: "/runs?status=failed" },
    { label: "在线机器人", value: robots.data?.filter(r => r.online && !r.revoked).length, to: "/robots" },
  ];
  return <><PageTitle title="工作总览" description="运行统计基于最近 500 次运行；机器人状态实时更新。" actions={<Link to="/runs/new"><Button type="primary" icon={<PlusOutlined />}>临时运行</Button></Link>} />
    {(runs.error || robots.error) && <Alert className="mb" type="error" showIcon message={runs.error || robots.error} />}
    <div className="stats-grid">{metrics.map(item => <Link key={item.label} to={item.to} className="stat"><div className="stat-label">{item.label}<PlayCircleOutlined /></div><div className="stat-number">{item.value ?? "—"}</div><div className="stat-note">查看详情 →</div></Link>)}</div>
    <Panel title="最近运行" extra={<Link to="/runs">全部记录</Link>}><Table rowKey="id" loading={!runs.data && !runs.error} dataSource={runs.data?.slice(0, 8)} pagination={false} scroll={{ x: 600 }} columns={[
      { title: "任务名称", render: (_, run) => <Link to={`/runs/${run.id}`}>{run.name}</Link> },
      { title: "运行状态", dataIndex: "status", render: s => <StatusTag status={statuses[s] || s} /> },
      { title: "创建时间", dataIndex: "created", render: date },
    ]} /></Panel></>;
}
