import { useState } from "react";
import { Alert, Button, Drawer, Empty, Table, Space } from "antd";
import { RobotOutlined } from "@ant-design/icons";
import { Link } from "react-router-dom";
import { robots } from "../mock/data";
import { useStore } from "../mock/store";
import { PageTitle, Panel, StatusTag } from "../components/shared";
export default function RobotsPage() {
  const { runs } = useStore();
  const [selected, setSelected] = useState<string>();
  const queue = runs
    .filter((r) => r.robot === selected && r.status === "排队中")
    .sort((a, b) => a.created.localeCompare(b.created));
  return (
    <>
      <PageTitle
        title="机器人"
        description="查看执行资源、占用状态与等待队列。"
      />
      <Alert
        showIcon
        className="mb"
        message="当前为示例机器人。连接、应用部署与版本发布将在后续接入。"
        type="info"
      />
      <Panel>
        <Table
          rowKey="id"
          scroll={{ x: 1050 }}
          pagination={{
            pageSize: 8,
            showTotal: (total) => `共 ${total} 台机器人`,
          }}
          dataSource={robots.map((robot) => ({
            ...robot,
            active: runs.find(
              (run) =>
                run.robot === robot.id &&
                [
                  "运行中",
                  "停止中",
                  "启动中",
                  "Agent 接管中",
                  "状态待确认",
                ].includes(run.status),
            ),
            queued: runs.filter(
              (run) => run.robot === robot.id && run.status === "排队中",
            ).length,
          }))}
          columns={[
            {
              title: "机器人 / ID",
              width: 220,
              render: (_, robot) => (
                <Space size={12}>
                  <div
                    className={`robot-mini ${robot.status === "离线" ? "offline" : ""}`}
                  >
                    <RobotOutlined />
                  </div>
                  <div>
                    <strong>{robot.name}</strong>
                    <div className="mono muted small">{robot.id}</div>
                  </div>
                </Space>
              ),
            },
            {
              title: "状态",
              width: 115,
              render: (_, robot) => (
                <StatusTag status={robot.active?.status || robot.status} />
              ),
            },
            { title: "执行位置", dataIndex: "location", width: 140 },
            {
              title: "当前占用运行",
              width: 210,
              render: (_, robot) =>
                robot.active ? (
                  <Link to={`/runs/${robot.active.id}`}>
                    {robot.active.name}
                  </Link>
                ) : (
                  <span className="muted">暂无运行</span>
                ),
            },
            { title: "已部署版本（示例）", dataIndex: "version", width: 200 },
            { title: "排队数", dataIndex: "queued", width: 85 },
            {
              title: "操作",
              fixed: "right",
              width: 110,
              render: (_, robot) => (
                <Button type="link" onClick={() => setSelected(robot.id)}>
                  查看队列
                </Button>
              ),
            },
          ]}
        />
      </Panel>
      <Drawer
        width={560}
        title={`${selected} · 等待队列`}
        open={!!selected}
        onClose={() => setSelected(undefined)}
      >
        <p className="muted">按入队时间排序，同一机器人一次执行一个任务。</p>
        {queue.length ? (
          <Table
            rowKey="id"
            pagination={false}
            dataSource={queue}
            columns={[
              { title: "序号", render: (_, __, i) => i + 1 },
              {
                title: "任务",
                render: (_, r) => <Link to={`/runs/${r.id}`}>{r.name}</Link>,
              },
              { title: "状态", render: () => <StatusTag status="排队中" /> },
            ]}
          />
        ) : (
          <Empty description="当前没有排队任务" />
        )}
      </Drawer>
    </>
  );
}
