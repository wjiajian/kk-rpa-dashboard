import { useState } from "react";
import { Alert, App, Button, Input, Select, Space, Tag } from "antd";
import { AppstoreOutlined } from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { useStore } from "../mock/store";
import { robots, type Task } from "../mock/data";
import { PageTitle, Panel, NotFound } from "../components/shared";
import { ParameterModal } from "../form/ParameterModal";
import { taskParameters } from "../form/parameters";
import { defaultDate } from "../form/DateBindingField";
import { ScheduleEditor } from "../schedule/ScheduleEditor";
import { nextDates } from "../schedule/cron";
import { validateTask } from "../form/submit";

export default function TaskEditor() {
  const { id } = useParams();
  const { tasks, apps, saveTask } = useStore();
  const existing = tasks.find(t => t.id === id);
  const [task, setTask] = useState<Task>(existing || {
    id: crypto.randomUUID(), name: "", appId: "", version: "",
    robot: "", brand: "", filename: "", date: defaultDate, parameters: {},
    username: "", expectedIdentity: "",
    cron: "0 8 * * *", enabled: false, configured: false,
  });
  const [password, setPassword] = useState("");
  const [editingPassword, setEditingPassword] = useState(false);
  const [parameterOpen, setParameterOpen] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const { message } = App.useApp();
  const app = apps.find(a => a.id === task.appId);
  const schema = app?.inputSchema;
  const update = (patch: Partial<Task>) => setTask(t => ({ ...t, ...patch }));
  if (id && !existing) return <NotFound />;
  const values = schema ? taskParameters(task, schema) : {};
  const save = () => {
    if (!task.appId) { setError("请选择执行应用"); return; }
    if (!task.robot) { setError("请选择执行机器人"); return; }
    if (!task.username?.trim()) { setError("请输入登录账号"); return; }
    if (!task.expectedIdentity?.trim()) { setError("请输入登录后预期可见身份"); return; }
    if (!schema) { setError("该应用缺少参数声明，请补齐后再创建任务。"); return; }
    const saved = { ...task, parameters: values, configured: true };
    let err = validateTask(saved, schema);
    if (task.enabled) { try { nextDates(task.cron); } catch { err = "请填写有效的五段 Cron 表达式"; } }
    if ((!task.configured || editingPassword) && !password) err = "请输入登录密码";
    if (err) { setError(err); return; }
    saveTask(saved);
    setPassword("");
    message.success("任务计划已保存");
    navigate("/tasks");
  };
  return <div className="task-editor">
    <PageTitle back title={existing ? "编辑任务计划" : "新建常规任务"} description="配置执行应用、机器人和触发时间。" />
    {error && <Alert type="error" message={error} showIcon className="mb" />}
    <Panel><div className="form-body">
      <label htmlFor="task-name">任务名称 <span>*</span></label>
      <Input id="task-name" placeholder="请输入任务名称" value={task.name} onChange={e => update({ name: e.target.value })} />
      <h2 className="form-section-title">应用与机器人</h2>
      <div className="application-config">
        <label htmlFor="task-app">执行应用</label>
        <div className="application-selection"><AppstoreOutlined /><Select id="task-app" aria-label="执行应用" showSearch optionFilterProp="label" placeholder="请选择执行应用" value={task.appId || undefined}
          options={apps.filter(a => a.valid).map(a => ({ label: a.name, value: a.id }))}
          onChange={value => { const selected = apps.find(a => a.id === value)!;
            update({ appId: value, version: selected.version, parameters: {}, username: "", expectedIdentity: "", configured: false });
            setPassword(""); setEditingPassword(false); setError("");
          }} />{task.version && <Tag>v{task.version}</Tag>}<Button type="link" disabled={!schema} onClick={() => setParameterOpen(true)}>参数</Button></div>
        <p className="muted">{schema ? `包含 ${Object.keys(schema.properties ?? {}).length} 个输入参数，点击「参数」填写。` : task.appId ? "该应用未提供参数声明，请补齐应用的参数表单。" : "选择应用后，可填写该程序的输入参数。"}</p>
        <label htmlFor="task-robot">执行机器人</label>
        <Select id="task-robot" aria-label="执行机器人" placeholder="请选择执行机器人" value={task.robot || undefined} options={robots.map(r => ({ value: r.id, label: `${r.name} · ${r.status}` }))} onChange={robot => update({ robot })} />
      </div>
      <h2 className="form-section-title">登录配置</h2>
      <label htmlFor="task-username">登录账号 <span>*</span></label>
      <Input id="task-username" placeholder="请输入业务平台登录账号" autoComplete="off" value={task.username || ""} onChange={e => { update({ username: e.target.value, configured: false }); setPassword(""); }} />
      <label htmlFor="task-identity">登录后预期可见身份 <span>*</span></label>
      <Input id="task-identity" placeholder="请输入登录后应显示的店铺或账号名称" autoComplete="off" value={task.expectedIdentity || ""} onChange={e => update({ expectedIdentity: e.target.value })} />
      <p className="muted">用于核对是否登录到正确的店铺或账号。</p>
      <label htmlFor="task-password">登录密码 <span>*</span></label>
      {task.configured && !editingPassword ? <Space><Input.Password disabled placeholder="已配置" /><Button onClick={() => setEditingPassword(true)}>修改</Button><Tag color="green">已配置</Tag></Space> :
        <Space><Input.Password id="task-password" value={password} placeholder="请输入登录密码" autoComplete="new-password" onChange={e => setPassword(e.target.value)} />{task.configured && <Button onClick={() => { setPassword(""); setEditingPassword(false); }}>取消修改</Button>}</Space>}
      <p className="muted">演示版仅保存配置状态，密码不持久化。</p>
      <h2 className="form-section-title">触发配置</h2>
      <ScheduleEditor cron={task.cron} enabled={task.enabled} onCron={cron => update({ cron })} onEnabled={enabled => update({ enabled })} />
    </div><div className="task-editor-footer"><Button onClick={() => navigate("/tasks")}>取消</Button><Button type="primary" onClick={save}>保存任务</Button></div></Panel>
    {parameterOpen && schema && <ParameterModal schema={schema} values={values} relativeDates onCancel={() => setParameterOpen(false)} onSave={parameters => { update({ parameters }); setParameterOpen(false); setError(""); }} />}
  </div>;
}
