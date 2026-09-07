import { useEffect } from "react";
import { Avatar, Button, Dropdown, Space, Tag } from "antd";
import {
  AppstoreOutlined,
  DashboardOutlined,
  UnorderedListOutlined,
  HistoryOutlined,
  RobotOutlined,
  SettingOutlined,
  EyeOutlined,
  DownOutlined,
  ApartmentOutlined,
  QuestionCircleOutlined,
} from "@ant-design/icons";
import {
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { useStore } from "./mock/store";
import OverviewPage from "./pages/OverviewPage";
import ApplicationsPage, { ApplicationDetail } from "./pages/ApplicationsPage";
import ImportWizard from "./pages/ImportWizard";
import TasksPage from "./pages/TasksPage";
import TaskEditor from "./pages/TaskEditor";
import RunsPage from "./pages/RunsPage";
import RunDetail from "./pages/RunDetail";
import RobotsPage from "./pages/RobotsPage";
import SettingsPage from "./pages/SettingsPage";
const nav = [
  { path: "/", label: "工作总览", icon: <DashboardOutlined /> },
  { path: "/applications", label: "应用中心", icon: <AppstoreOutlined /> },
  { path: "/tasks", label: "任务管理", icon: <UnorderedListOutlined /> },
  { path: "/runs", label: "运行记录", icon: <HistoryOutlined /> },
  { path: "/robots", label: "机器人", icon: <RobotOutlined /> },
  { path: "/business/runs", label: "业务运行", icon: <EyeOutlined /> },
  { path: "/settings", label: "管理设置", icon: <SettingOutlined /> },
];
export default function App() {
  const { member, setMember } = useStore();
  const location = useLocation();
  const current = nav.find((n) =>
    n.path === "/"
      ? location.pathname === "/"
      : location.pathname.startsWith(n.path),
  );
  useEffect(() => {
    document.title = `${current?.label || "页面"} · KK RPA`;
    window.scrollTo(0, 0);
  }, [location.pathname, current?.label]);
  return (
    <div className="shell">
      <aside className="sidebar">
        <Link to={member ? "/business/runs" : "/"} className="brand">
          <div className="brand-symbol">
            <ApartmentOutlined />
          </div>
          <div>
            <strong>KK RPA</strong>
            <span>自动化控制台</span>
          </div>
        </Link>
        <div className="nav-caption">工作空间</div>
        <nav>
          {nav
            .filter((n) => !member || n.path === "/business/runs")
            .map((n, i) => (
              <NavLink
                end={n.path === "/"}
                className={({ isActive }) =>
                  `nav-item ${isActive ? "selected" : ""} ${i === 5 ? "nav-separated" : ""}`
                }
                to={n.path}
                key={n.path}
              >
                {n.icon}
                <span>{n.label}</span>
                {n.path === "/robots" && <span className="nav-count">4</span>}
              </NavLink>
            ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="demo-note">
            <span className="live-dot" />
            <strong>前端演示环境</strong>
            <p>使用模拟数据预览业务流程</p>
          </div>
          <div className="sidebar-version">
            KK RPA CONSOLE <span>v0.1</span>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <Space size={12}>
            <span className="breadcrumb-root">工作空间</span>
            <span className="muted">/</span>
            <span>{current?.label || "详情"}</span>
          </Space>
          <Space size={18}>
            <Tag bordered={false} className="demo-tag">
              DEMO
            </Tag>
            <Dropdown
              menu={{
                items: [
                  {
                    key: "hint",
                    label:
                      "所有修改仅在当前页面会话中保留，刷新后恢复示例数据。",
                  },
                ],
              }}
            >
              <Button
                aria-label="演示说明"
                type="text"
                icon={<QuestionCircleOutlined />}
              />
            </Dropdown>
            <Dropdown
              menu={{
                items: [
                  {
                    key: "role",
                    label: member
                      ? "切换为管理员（演示）"
                      : "切换为只读成员（演示）",
                    onClick: () => setMember(!member),
                  },
                ],
              }}
            >
              <button className="profile">
                <Avatar
                  size={30}
                  style={{ background: "#e4eed9", color: "#507043" }}
                >
                  邵
                </Avatar>
                <span>{member ? "只读成员" : "管理员"}</span>
                <DownOutlined />
              </button>
            </Dropdown>
          </Space>
        </header>
        <main>
          {member && !location.pathname.startsWith("/business/") ? (
            <Navigate to="/business/runs" replace />
          ) : (
            <Routes>
              <Route path="/" element={<OverviewPage />} />
              <Route path="/applications" element={<ApplicationsPage />} />
              <Route path="/applications/import" element={<ImportWizard />} />
              <Route path="/applications/:id" element={<ApplicationDetail />} />
              <Route path="/tasks" element={<TasksPage />} />
              <Route path="/tasks/new" element={<TaskEditor key="new" />} />
              <Route
                path="/tasks/:id/edit"
                element={<TaskEditor key={location.pathname} />}
              />
              <Route path="/runs" element={<RunsPage />} />
              <Route
                path="/runs/:id"
                element={<RunDetail key={location.pathname} />}
              />
              <Route path="/business/runs" element={<RunsPage business />} />
              <Route
                path="/business/runs/:id"
                element={<RunDetail key={location.pathname} business />}
              />
              <Route path="/robots" element={<RobotsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          )}
        </main>
      </div>
    </div>
  );
}
