import { useEffect } from "react";
import { Alert, Avatar, Button, Space, Spin, Tag } from "antd";
import { ApartmentOutlined, AppstoreOutlined, DashboardOutlined, HistoryOutlined, RobotOutlined, UnorderedListOutlined } from "@ant-design/icons";
import { Link, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { PageTitle, NotFound } from "./components/shared";
import { useResource } from "./live/useResource";
import { LiveDetail, LiveRobots } from "./live/RunOperations";
import { ApplicationList, RunList, WorkspaceOverview } from "./live/WorkspacePages";
import NewTask from "./live/NewTask";

export interface ConsoleUser { name: string; admin: boolean }
export const consoleNavigation = (admin: boolean) => admin ? [
  { path: "/", label: "工作总览", icon: <DashboardOutlined /> },
  { path: "/applications", label: "应用中心", icon: <AppstoreOutlined /> },
  { path: "/tasks", label: "任务管理", icon: <UnorderedListOutlined /> },
  { path: "/runs", label: "运行记录", icon: <HistoryOutlined /> },
  { path: "/robots", label: "机器人", icon: <RobotOutlined /> },
] : [{ path: "/business/runs", label: "业务运行", icon: <HistoryOutlined /> }];

export default function App() {
  const { data: user, error, refresh } = useResource<ConsoleUser>("/me", 60000);
  const location = useLocation();
  const nav = user ? consoleNavigation(user.admin) : [];
  const current = nav.find(n => n.path === "/" ? location.pathname === "/" : location.pathname.startsWith(n.path));
  useEffect(() => { document.title = `${current?.label || "控制台"} · KK RPA`; window.scrollTo(0, 0); }, [location.pathname, current?.label]);
  return <div className="shell"><aside className="sidebar">
    <Link to={user?.admin ? "/" : "/business/runs"} className="brand"><div className="brand-symbol"><ApartmentOutlined /></div><div><strong>KK RPA</strong><span>自动化控制台</span></div></Link>
    <div className="nav-caption">工作空间</div><nav>{nav.map(item => <NavLink end={item.path === "/"} key={item.path} to={item.path} className={({ isActive }) => `nav-item ${isActive ? "selected" : ""}`}>{item.icon}<span>{item.label}</span></NavLink>)}</nav>
    <div className="sidebar-bottom"><div className="connection-note"><span className="live-dot" /><strong>机器人执行环境</strong><p>任务与运行记录由服务端保存</p></div><div className="sidebar-version">KK RPA CONSOLE <span>v0.1</span></div></div>
  </aside><div className="main-shell"><header className="topbar"><Space size={12}><span className="breadcrumb-root">工作空间</span><span className="muted">/</span><span>{current?.label || "控制台"}</span></Space>
    <Space><Tag color={error ? "orange" : user ? "blue" : "default"}>{error ? "连接待恢复" : user ? "实时数据" : "正在连接"}</Tag>{user && <><Avatar style={{ background: "#edf3ff", color: "#3276ff" }}>{user.name.slice(0, 1)}</Avatar><span>{user.name} · {user.admin ? "管理员" : "只读成员"}</span></>}</Space></header>
    <main>{error ? <div className="panel panel-padding"><PageTitle title="连接控制台" description="请确认服务可用，并使用企业飞书账号登录。" /><Alert type="warning" showIcon message={error} className="mb" /><Space><Button type="primary" href="/api/auth/feishu/login">企业飞书登录</Button><Button onClick={refresh}>重试连接</Button></Space></div> : !user ? <Spin aria-label="正在连接控制台" /> : <ConsoleRoutes user={user} />}</main>
  </div></div>;
}
export function ConsoleRoutes({ user }: { user: ConsoleUser }) {
  return user.admin ? <Routes>
    <Route path="/" element={<WorkspaceOverview />} />
    <Route path="/applications" element={<ApplicationList />} />
    <Route path="/tasks" element={<RunList tasks />} />
    <Route path="/tasks/new" element={<NewTask />} />
    <Route path="/runs" element={<RunList />} />
    <Route path="/runs/new" element={<Navigate replace to="/tasks/new" />} />
    <Route path="/runs/:id" element={<LiveDetail business={false} />} />
    <Route path="/robots" element={<LiveRobots />} />
    <Route path="/business/runs" element={<RunList business />} />
    <Route path="/business/runs/:id" element={<LiveDetail business />} />
    <Route path="*" element={<NotFound />} />
  </Routes> : <Routes><Route path="/business/runs" element={<RunList business />} /><Route path="/business/runs/:id" element={<LiveDetail business />} /><Route path="*" element={<Navigate replace to="/business/runs" />} /></Routes>;
}
