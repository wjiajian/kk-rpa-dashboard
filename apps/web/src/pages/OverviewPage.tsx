import { Button, Progress, Space, Table } from "antd";
import {
  ArrowRightOutlined,
  PlusOutlined,
  ImportOutlined,
  PlayCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import { Link } from "react-router-dom";
import { useStore } from "../mock/store";
import { robots, time, today } from "../mock/data";
import { Panel, PageTitle, StatusTag } from "../components/shared";
export default function OverviewPage() {
  const { runs, tasks, apps } = useStore();
  const failed = runs.filter((r) => r.status === "失败");
  const active = runs.filter((r) => r.status === "运行中");
  const stats = [
    {
      label: "今日运行",
      value: runs.filter((r) => time(r.created, "YYYY-MM-DD") === today).length,
      note: `${runs.filter((r) => r.status === "成功").length} 次已完成`,
      icon: <PlayCircleOutlined />,
      color: "blue",
      to: "/runs",
    },
    {
      label: "排队中",
      value: runs.filter((r) => r.status === "排队中").length,
      note: "等待机器人空闲",
      icon: <ClockCircleOutlined />,
      color: "amber",
      to: "/runs?status=排队中",
    },
    {
      label: "失败运行",
      value: failed.length,
      note: "需要关注与处理",
      icon: <ExclamationCircleOutlined />,
      color: "red",
      to: "/runs?status=失败",
    },
    {
      label: "在线机器人",
      value: robots.filter((r) => r.status !== "离线").length,
      note: `共 ${robots.length} 台 · ${robots.filter((r) => r.status === "空闲").length} 台空闲`,
      icon: <RobotOutlined />,
      color: "green",
      to: "/robots",
    },
  ];
  return (
    <>
      <PageTitle
        title="工作总览"
        description="查看自动化任务的运行情况，让每一次执行都有迹可循。"
        actions={
          <Space>
            <Link to="/applications/import">
              <Button icon={<ImportOutlined />}>导入应用</Button>
            </Link>
            <Link to="/tasks/new">
              <Button type="primary" icon={<PlusOutlined />}>
                创建任务
              </Button>
            </Link>
          </Space>
        }
      />
      <div className="overview-strip">
        <span>
          <span className="live-dot" />
          自动化工作台
        </span>
        <span>
          {today} <span className="divider">/</span> Asia/Shanghai{" "}
          <span className="divider">/</span> 演示数据
        </span>
      </div>
      <div className="stats-grid">
        {stats.map((s) => (
          <Link className={`stat ${s.color}`} to={s.to} key={s.label}>
            <div className="stat-label">
              {s.label}
              <span className="stat-icon">{s.icon}</span>
            </div>
            <div className="stat-number">
              {String(s.value).padStart(2, "0")}
              <span>{s.label === "在线机器人" ? "台" : "次"}</span>
            </div>
            <div className="stat-note">
              {s.note}
              <ArrowRightOutlined />
            </div>
          </Link>
        ))}
      </div>
      <div className="overview-main">
        <Panel
          title={
            <>
              <span className="live-dot" />
              正在执行 <span className="count-label">{active.length}</span>
            </>
          }
          extra={
            <Link to="/runs?status=运行中">
              全部运行 <ArrowRightOutlined />
            </Link>
          }
        >
          {active.length ? (
            active.map((r) => (
              <Link to={`/runs/${r.id}`} className="active-run" key={r.id}>
                <div className="run-app-icon">
                  <PlayCircleOutlined />
                </div>
                <div className="run-content">
                  <div className="flex-between">
                    <strong>{r.name}</strong>
                    <StatusTag status={r.status} />
                  </div>
                  <div className="muted small">
                    {r.robot} <span className="divider">·</span> {r.source}触发{" "}
                    <span className="divider">·</span>{" "}
                    {time(r.created, "HH:mm")} 开始
                  </div>
                  <Progress
                    percent={r.progress}
                    size="small"
                    showInfo={false}
                  />
                  <div className="flex-between small muted">
                    <span>正在下载业务报表</span>
                    <span>步骤 3 / 5</span>
                  </div>
                </div>
              </Link>
            ))
          ) : (
            <p className="panel-padding muted">当前没有正在执行的任务</p>
          )}
          <div className="panel-foot">
            单台机器人串行执行，排队任务将在空闲后依次运行。
          </div>
        </Panel>
        <Panel title="工作区" className="workspace-panel">
          <div className="workspace-metrics">
            <Link to="/applications">
              <strong>{apps.length}</strong>
              <span>
                已导入应用 <ArrowRightOutlined />
              </span>
            </Link>
            <Link to="/tasks">
              <strong>{tasks.length}</strong>
              <span>
                已配置任务 <ArrowRightOutlined />
              </span>
            </Link>
          </div>
          <div className="workspace-rule">
            <ClockCircleOutlined />
            <div>
              <strong>
                {tasks.filter((t) => t.enabled).length} 个定时任务已启用
              </strong>
              <p>按照任务计划自动加入执行队列</p>
            </div>
          </div>
          <Link className="workspace-link" to="/tasks">
            管理任务与定时 <ArrowRightOutlined />
          </Link>
        </Panel>
      </div>
      <div className="overview-bottom">
        <Panel
          title={
            <>
              <span className="failure-mark" />
              最近失败运行 <span className="count-label">{failed.length}</span>
            </>
          }
          extra={
            <Link to="/runs?status=失败">
              查看全部 <ArrowRightOutlined />
            </Link>
          }
        >
          <Table
            rowKey="id"
            pagination={false}
            dataSource={failed.slice(0, 3)}
            scroll={{ x: 520 }}
            columns={[
              {
                title: "任务 / 失败原因",
                render: (_, r) => (
                  <Link to={`/runs/${r.id}`}>
                    <strong>{r.name}</strong>
                    <div className="error-reason">{r.error}</div>
                  </Link>
                ),
              },
              {
                title: "开始时间",
                dataIndex: "created",
                render: (v) => (
                  <span className="mono">{time(v, "HH:mm:ss")}</span>
                ),
              },
              {
                title: "操作",
                render: (_, r) => <Link to={`/runs/${r.id}`}>查看详情</Link>,
              },
            ]}
          />
        </Panel>
        <Panel
          title="机器人状态"
          extra={
            <Link to="/robots">
              管理 <ArrowRightOutlined />
            </Link>
          }
        >
          {robots.map((r) => (
            <div className="robot-row" key={r.id}>
              <div
                className={`robot-mini ${r.status === "离线" ? "offline" : ""}`}
              >
                <RobotOutlined />
              </div>
              <div>
                <strong>{r.name}</strong>
                <div className="mono muted small">{r.id}</div>
              </div>
              <StatusTag status={r.status} />
            </div>
          ))}
        </Panel>
      </div>
      <div className="page-foot">
        KK RPA 控制台 <span>让重复工作自动发生</span>
      </div>
    </>
  );
}
