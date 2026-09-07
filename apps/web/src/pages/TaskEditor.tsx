import { useState } from "react";
import { Alert, App, Button, Input, Select, Space, Tag } from "antd";
import { SaveOutlined, PlayCircleOutlined } from "@ant-design/icons";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useStore } from "../mock/store";
import { robots, type Task } from "../mock/data";
import { PageTitle, Panel, NotFound } from "../components/shared";
import { SchemaForm } from "../form/SchemaForm";
import { DateBindingField, defaultDate } from "../form/DateBindingField";
import { ScheduleEditor } from "../schedule/ScheduleEditor";
import { nextDates } from "../schedule/cron";
import { assembleTask, validateTask } from "../form/submit";
import { useTrigger } from "./TasksPage";
export default function TaskEditor() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const { tasks, apps, saveTask } = useStore();
  const existing = tasks.find((t) => t.id === id);
  const initialApp =
    apps.find((a) => a.id === params.get("app") && a.valid) ||
    apps.find((a) => a.valid)!;
  const [task, setTask] = useState<Task>(
    existing || {
      id: crypto.randomUUID(),
      name: "",
      appId: initialApp.id,
      version: initialApp.version,
      robot: robots[0].id,
      account: "",
      brand: "全部品牌",
      filename: "report.xlsx",
      date: defaultDate,
      cron: "0 8 * * *",
      enabled: false,
      configured: false,
    },
  );
  const [password, setPassword] = useState("");
  const [editingPassword, setEditingPassword] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const { message } = App.useApp();
  const trigger = useTrigger();
  const update = (patch: Partial<Task>) => setTask((t) => ({ ...t, ...patch }));
  if (id && !existing) return <NotFound />;
  const save = () => {
    let err = validateTask(task);
    try {
      nextDates(task.cron);
    } catch {
      err = "请填写有效的五段 Cron 表达式";
    }
    if ((!task.configured || editingPassword) && !password)
      err = "请输入密码或取消修改";
    if (err) {
      setError(err);
      return;
    }
    assembleTask(task, password);
    const saved = { ...task, configured: true };
    saveTask(saved);
    setTask(saved);
    setPassword("");
    setEditingPassword(false);
    setError("");
    message.success("已保存，可点击立即运行触发");
    navigate(`/tasks/${task.id}/edit`, { replace: true });
  };
  return (
    <>
      <PageTitle
        back
        title={existing ? "编辑任务" : "创建任务"}
        description="保存一套可重复执行的业务配置。"
        actions={
          <Space>
            {existing && (
              <Button
                icon={<PlayCircleOutlined />}
                onClick={() => trigger(existing)}
              >
                立即运行
              </Button>
            )}
            <Button type="primary" icon={<SaveOutlined />} onClick={save}>
              保存任务
            </Button>
          </Space>
        }
      />
      {existing && (
        <Alert
          showIcon
          type="info"
          message="修改只影响之后触发的新运行，已排队和历史运行保持原参数。"
          className="mb"
        />
      )}
      {error && <Alert type="error" message={error} showIcon className="mb" />}
      <div className="editor-grid">
        <div>
          <Panel title="基本信息">
            <div className="form-body">
              <label>
                任务名称 <span>*</span>
              </label>
              <Input
                aria-label="任务名称"
                placeholder="例如：商品日报 · 全部门店"
                value={task.name}
                onChange={(e) => update({ name: e.target.value })}
              />
              <div className="form-two">
                <div>
                  <label>应用</label>
                  <Select
                    value={task.appId}
                    options={apps
                      .filter((a) => a.valid)
                      .map((a) => ({ label: a.name, value: a.id }))}
                    onChange={(v) => {
                      update({
                        appId: v,
                        version: apps.find((a) => a.id === v)!.version,
                        brand: "",
                        filename: "",
                        date: defaultDate,
                      });
                      message.info("已切换应用，请重新填写业务参数");
                    }}
                  />
                </div>
                <div>
                  <label>应用版本</label>
                  <Select
                    value={task.version}
                    options={[
                      {
                        label: `v${apps.find((a) => a.id === task.appId)?.version} · 最新版本`,
                        value: apps.find((a) => a.id === task.appId)?.version,
                      },
                    ]}
                  />
                </div>
              </div>
            </div>
          </Panel>
          <Panel title="业务参数">
            <div className="form-body">
              <SchemaForm
                data={{ brand: task.brand, filename: task.filename }}
                onChange={update}
              />
              <label>
                业务日期 <span>*</span>
              </label>
              <DateBindingField
                value={task.date}
                onChange={(date) => update({ date })}
              />
            </div>
          </Panel>
          <Panel title="执行配置">
            <div className="form-body">
              <label>执行机器人</label>
              <Select
                value={task.robot}
                options={robots.map((r) => ({
                  value: r.id,
                  label: `${r.name} · ${r.status}`,
                }))}
                onChange={(robot) => update({ robot })}
              />
              <label>
                账号别名 <span>*</span>
              </label>
              <Input
                aria-label="账号别名"
                placeholder="例如 STORE_001"
                value={task.account}
                onChange={(e) => update({ account: e.target.value })}
              />
              <label>
                登录密码 <span>*</span>
              </label>
              {task.configured && !editingPassword ? (
                <Space>
                  <Input.Password disabled placeholder="已配置" />
                  <Button onClick={() => setEditingPassword(true)}>修改</Button>
                  <Tag color="green">已配置</Tag>
                </Space>
              ) : (
                <Space>
                  <Input.Password
                    aria-label="登录密码"
                    value={password}
                    placeholder="请输入新密码"
                    autoComplete="new-password"
                    onChange={(e) => setPassword(e.target.value)}
                  />
                  {task.configured && (
                    <Button
                      onClick={() => {
                        setPassword("");
                        setEditingPassword(false);
                      }}
                    >
                      取消修改
                    </Button>
                  )}
                </Space>
              )}
              <p className="muted small">
                演示版只保存配置状态，密码不持久化。
              </p>
            </div>
          </Panel>
        </div>
        <div>
          <Panel title="定时计划">
            <div className="form-body">
              <ScheduleEditor
                cron={task.cron}
                enabled={task.enabled}
                onCron={(cron) => update({ cron })}
                onEnabled={(enabled) => update({ enabled })}
              />
            </div>
          </Panel>
          <div className="editor-note">
            <strong>保存与执行相互独立</strong>
            <p>保存后可点击「立即运行」，或等待已启用的定时计划触发。</p>
            <p>机器人连接与自动调度将在后续接入。</p>
          </div>
        </div>
      </div>
    </>
  );
}
