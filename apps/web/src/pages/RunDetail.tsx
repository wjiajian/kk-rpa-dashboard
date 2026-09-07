import { useState } from "react";
import {
  Alert,
  App,
  Button,
  Descriptions,
  Empty,
  Progress,
  Space,
  Table,
  Tag,
} from "antd";
import {
  ReloadOutlined,
  StopOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
} from "@ant-design/icons";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useStore } from "../mock/store";
import { time, type Status } from "../mock/data";
import { PageTitle, Panel, StatusTag, NotFound } from "../components/shared";
export default function RunDetail({
  business = false,
}: {
  business?: boolean;
}) {
  const { id } = useParams();
  const { runs, setRuns, apps } = useStore();
  const run = runs.find((r) => r.id === id);
  const { modal, message } = App.useApp();
  const navigate = useNavigate();
  const [errorsOnly, setErrorsOnly] = useState(false);
  if (!run) return <NotFound />;
  const terminal = ["成功", "失败", "已取消", "已停止"].includes(run.status);
  const canStop = ["启动中", "运行中"].includes(run.status);
  const action = (kind: string) =>
    modal.confirm({
      title: kind === "重跑" ? "从头重跑本次运行？" : `${kind}？`,
      content:
        kind === "重跑"
          ? "沿用原账号、应用版本与实际业务参数，从第一步重新执行。此操作只创建模拟记录。"
          : kind === "请求停止"
            ? "在当前步骤结束后停止；请求已接收不代表运行已停止。"
            : "取消这条尚未执行的模拟运行。",
      okText: "确认",
      onOk: () => {
        if (kind === "重跑") {
          const newId = `RUN-${crypto.randomUUID().slice(0, 8)}`;
          setRuns((old) => [
            {
              ...run,
              id: newId,
              status: "排队中",
              source: "手动",
              created: new Date().toISOString(),
              duration: "—",
              progress: 0,
              error: undefined,
              rerunOf: run.id,
            },
            ...old,
          ]);
          navigate(`${business ? "/business" : ""}/runs/${newId}`);
        } else
          setRuns((old) =>
            old.map((r) =>
              r.id === id
                ? {
                    ...r,
                    status: (kind === "请求停止"
                      ? "停止中"
                      : "已取消") as Status,
                  }
                : r,
            ),
          );
        message.success("模拟操作已记录");
      },
    });
  const logSteps = [
    "登录业务平台",
    "检查账号身份",
    "选择品牌与业务日期",
    "下载业务报表",
    "校验并保存结果",
  ];
  const count =
    run.status === "成功"
      ? 5
      : run.status === "失败"
        ? Math.round(run.progress / 20) + 1
        : run.progress
          ? 3
          : 0;
  return (
    <>
      <PageTitle
        back
        title={run.name}
        description={
          business
            ? `创建于 ${time(run.created, "YYYY-MM-DD HH:mm:ss")}`
            : run.id
        }
        actions={
          <Space>
            <StatusTag status={run.status} />
            {!business &&
              (terminal ? (
                <Button
                  icon={<ReloadOutlined />}
                  onClick={() => action("重跑")}
                >
                  从头重跑
                </Button>
              ) : run.status === "排队中" ? (
                <Button onClick={() => action("取消排队")}>取消排队</Button>
              ) : canStop ? (
                <Button
                  danger
                  icon={<StopOutlined />}
                  onClick={() => action("请求停止")}
                >
                  请求停止
                </Button>
              ) : null)}
          </Space>
        }
      />
      {run.error && (
        <Alert className="mb" showIcon type="error" message={run.error} />
      )}{" "}
      {["停止中", "状态待确认", "Agent 接管中"].includes(run.status) && (
        <Alert
          className="mb"
          showIcon
          type="warning"
          message={
            run.status === "停止中"
              ? "停止请求已记录，等待当前步骤结束和执行端确认。"
              : run.status === "状态待确认"
                ? "正在核对执行状态，机器人仍保持占用。"
                : "Agent 接管中，接管剩余时间待执行端提供。"
          }
        />
      )}
      {!business && (
        <Panel title="运行信息">
          <Descriptions
            className="panel-padding"
            column={{ xs: 1, sm: 2, lg: 3 }}
            items={[
              {
                key: "app",
                label: "应用 / 版本",
                children: `${apps.find((a) => a.id === run.appId)?.name} · v${run.version}`,
              },
              { key: "robot", label: "执行机器人", children: run.robot },
              { key: "source", label: "触发来源", children: run.source },
              {
                key: "time",
                label: "创建时间",
                children: time(run.created, "YYYY-MM-DD HH:mm:ss"),
              },
              {
                key: "rerun",
                label: "来源运行",
                children: run.rerunOf ? (
                  <Link to={`/runs/${run.rerunOf}`}>{run.rerunOf}</Link>
                ) : (
                  "—"
                ),
              },
            ]}
          />
          <div className="params-row">
            <strong>实际业务参数</strong>
            {Object.entries(run.params).map(([key, v]) => (
              <span key={key}>
                <code>{key}</code> <b>{v}</b>
              </span>
            ))}
          </div>
        </Panel>
      )}
      <div className="detail-grid">
        <div>
          <Panel
            title="业务进度"
            extra={
              <span className="muted small">
                {Math.round(run.progress / 20)} / 5 步骤
              </span>
            }
          >
            <div className="panel-padding">
              <Progress
                percent={run.progress}
                status={
                  run.status === "失败"
                    ? "exception"
                    : run.status === "成功"
                      ? "success"
                      : "normal"
                }
              />
              <div className="step-labels">
                {logSteps.map((s, i) => (
                  <div key={s} className={i < run.progress / 20 ? "done" : ""}>
                    <span>
                      {i < run.progress / 20 ? (
                        <CheckCircleOutlined />
                      ) : (
                        <ClockCircleOutlined />
                      )}
                    </span>
                    {s}
                  </div>
                ))}
              </div>
            </div>
          </Panel>
          <Panel
            title="执行日志"
            extra={
              <Space>
                <Tag bordered={false}>模拟日志</Tag>
                <Button
                  size="small"
                  type={errorsOnly ? "primary" : "default"}
                  onClick={() => setErrorsOnly(!errorsOnly)}
                >
                  {errorsOnly ? "显示全部" : "只看失败"}
                </Button>
              </Space>
            }
          >
            <div className="log-stream">
              {count ? (
                logSteps.slice(0, count).map((s, i) => ({ s, i })).reverse().map(({ s, i }) => {
                  const failed = run.status === "失败" && i === count - 1;
                  if (errorsOnly && !failed) return null;
                  return (
                    <div
                      key={s}
                      className={`log-line ${failed ? "log-error" : ""}`}
                    >
                      <span className="log-time mono">
                        {time(
                          new Date(
                            new Date(run.created).getTime() + i * 12000,
                          ).toISOString(),
                          "HH:mm:ss",
                        )}
                      </span>
                      {failed ? (
                        <CloseCircleOutlined />
                      ) : (
                        <CheckCircleOutlined />
                      )}
                      <div>
                        <strong>
                          {s}：{failed ? "失败" : "完成"}
                        </strong>
                        <p>
                          {failed
                            ? run.error
                            : `步骤 ${i + 1} / 5 · 耗时 12 秒`}
                        </p>
                      </div>
                    </div>
                  );
                })
              ) : (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={
                    run.status === "已取消"
                      ? "运行已取消，未产生执行日志"
                      : "等待执行，暂无日志"
                  }
                />
              )}{" "}
              {errorsOnly && count > 0 && run.status !== "失败" && (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="没有失败日志"
                />
              )}
            </div>
            <div className="panel-foot">
              {terminal
                ? "运行已结束"
                : "当前展示静态模拟日志，实时事件将在接口接入后启用"}
            </div>
          </Panel>
        </div>
        <div>
          {!business && (
            <Panel title="执行尝试">
              <Table
                size="small"
                rowKey="id"
                pagination={false}
                dataSource={
                  count ? [{ id: "attempt-01", status: run.status }] : []
                }
                columns={[
                  {
                    title: "尝试",
                    render: () => (
                      <>
                        第 1 次
                        <div className="muted small mono">local-demo-01</div>
                      </>
                    ),
                  },
                  {
                    title: "结果",
                    dataIndex: "status",
                    render: (s) => <StatusTag status={s} />,
                  },
                ]}
              />
            </Panel>
          )}
          <Panel title="失败截图">
            <div className="evidence-empty">
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  run.status === "失败" ? "演示记录未附带截图" : "暂无失败截图"
                }
              />
              <p>执行端接入后将在这里展示失败现场。</p>
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
