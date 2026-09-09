import { useEffect, useRef, useState } from "react";
import { Alert, App, Button, Form, Input, Select, Space, Tag } from "antd";
import { AppstoreOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { PageTitle, Panel } from "../components/shared";
import { ParameterModal } from "../form/ParameterModal";
import { parameterError, type ParameterValues } from "../form/parameters";
import { PlanSchedule } from "./PlanSchedule";
import { api, type TaskRecord, type RobotRecord } from "./api";
import { useResource } from "./useResource";
import { deployedApplications, inputSchemaFor, releaseKey } from "./deployments";

export default function NewTask({ plan = false, task }: { plan?: boolean; task?: TaskRecord }) {
  const { data: robots, error, refresh } = useResource<RobotRecord[]>("/robots", 10000);
  const [form] = Form.useForm();
  const [selectedRelease, setSelectedRelease] = useState<string | undefined>(task ? releaseKey(task) : undefined);
  const [robotId, setRobotId] = useState<string | undefined>(task?.robot_id);
  const [replaceCredentials, setReplaceCredentials] = useState(!task);
  const [cron, setCron] = useState(task?.schedule.cron || "");
  const [enabled, setEnabled] = useState(task?.schedule.enabled || false);
  const savedRevision = useRef(task?.revision);
  const request = useRef<{ body: string; id: string }>();
  const releases = deployedApplications(robots || []);
  const application = releases.find(d => releaseKey(d) === selectedRelease);
  const robot = robots?.find(r => r.id === robotId && !r.revoked);
  const deployment = robot?.deployments.find(d => releaseKey(d) === selectedRelease);
  // Read the chosen robot's declaration: two machines can have different deployments.
  const schema = inputSchemaFor(deployment);
  const invalidSchema = deployment?.schema_status === "invalid";
  const [inputs, setInputs] = useState<ParameterValues>(() => Object.fromEntries(Object.entries(task?.input_bindings || {}).map(([key, binding]) => [key, binding.kind === "literal" ? binding.value : binding])));
  const [legacyInputs, setLegacyInputs] = useState("");
  const [parameterOpen, setParameterOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const [submitError, setSubmitError] = useState("");
  const { message } = App.useApp();
  const navigate = useNavigate();
  const previousSchema = useRef<string>();
  const schemaKey = JSON.stringify(schema);
  const clearInputs = () => { setInputs({}); setLegacyInputs(""); setParameterOpen(false); setSubmitError(""); };
  useEffect(() => {
    if (previousSchema.current !== undefined && previousSchema.current !== schemaKey) clearInputs();
    previousSchema.current = schemaKey;
  }, [schemaKey]);
  const submit = async () => {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    try {
      const values = await form.validateFields();
      if (!deployment || !robot) throw new Error("请选择仍部署该应用版本的机器人");
      if (invalidSchema) throw new Error("应用参数声明损坏，请更新执行端部署后再运行");
      let actualInputs = inputs;
      if (schema) {
        const problem = parameterError(schema, inputs, plan);
        if (problem) { setParameterOpen(true); throw new Error(problem); }
      } else {
        if (plan) throw new Error("计划需要有效参数声明，请先更新执行端部署");
        try { actualInputs = JSON.parse(legacyInputs); } catch { throw new Error("请输入有效的业务参数 JSON 对象；无参数时填写 {}"); }
        if (!actualInputs || Array.isArray(actualInputs) || typeof actualInputs !== "object") throw new Error("业务参数必须为 JSON 对象");
      }
      setBusy(true); setSubmitError("");
      if (plan) {
        const input_bindings = Object.fromEntries(Object.entries(actualInputs).filter(([, value]) => value !== undefined).map(([key, value]) => {
          const field = schema?.properties?.[key];
          const isDate = field && typeof field === "object" && field.format === "date";
          if (isDate && value && typeof value === "object" && "kind" in value) {
            if (value.kind === "relative_date") return [key, value];
            if (value.kind === "fixed" && "value" in value) return [key, { kind: "literal", value: value.value }];
          }
          return [key, { kind: "literal", value }];
        }));
        await api(task ? `/tasks/${task.id}` : "/tasks", {
          name: values.name.trim(), robot_id: robot.id, app_id: deployment.app_id, version: deployment.version, release_id: deployment.release_id,
          input_bindings, download_dir: values.download_dir || null, schedule: { cron, enabled, timezone: "Asia/Shanghai" },
          ...(replaceCredentials ? { credentials: values.credentials } : {}), ...(task ? { revision: savedRevision.current } : {}),
        }, task ? "PATCH" : "POST");
        message.success("计划已保存"); navigate("/tasks");
      } else {
        const body = { name: values.name.trim(), robot_id: robot.id, credentials: values.credentials,
          snapshot: { app_id: deployment.app_id, version: deployment.version, release_id: deployment.release_id, inputs: actualInputs, download_dir: values.download_dir || null } };
        const serialized = JSON.stringify(body);
        if (request.current?.body !== serialized) request.current = { body: serialized, id: crypto.randomUUID() };
        const run = await api<{ id: string }>("/runs", { ...body, request_id: request.current.id });
        request.current = undefined;
        form.resetFields(); message.success("任务已加入执行队列"); navigate(`/runs/${run.id}`);
      }
    } catch (error) { if (error instanceof Error) setSubmitError(error.message); }
    finally { submitting.current = false; setBusy(false); }
  };
  return <div className="task-editor">
    <PageTitle back title={plan ? task ? "编辑计划" : "新建计划" : "临时运行"} description={plan ? "保存应用、参数与触发配置，运行时生成独立记录。" : "选择应用、填写参数，交给机器人执行。"} />
    {error && <Alert className="mb" type="error" showIcon message={error} action={<Button onClick={refresh}>重试</Button>} />}
    {submitError && <Alert className="mb" type="error" showIcon message={submitError} />}
    <Panel><Form form={form} initialValues={task ? { name: task.name, robot_id: task.robot_id, release: releaseKey(task), download_dir: task.download_dir } : undefined} layout="vertical" disabled={busy} requiredMark className="form-body" onFinish={() => void submit()}>
      <Form.Item name="name" label="任务名称" rules={[{ required: true, whitespace: true, message: "请输入任务名称" }]}><Input placeholder="请输入任务名称" maxLength={200} /></Form.Item>
      <h2 className="form-section-title">应用与机器人</h2>
      <div className="application-config">
        <label htmlFor="execution-app">执行应用</label>
        <div className="application-selection"><AppstoreOutlined />
          <Form.Item name="release" noStyle rules={[{ required: true, message: "请选择执行应用" }]}><Select id="execution-app" aria-label="执行应用" placeholder="请选择执行应用" showSearch optionFilterProp="label" loading={!robots && !error}
            options={releases.map(d => ({ value: releaseKey(d), label: `${d.app_id} · v${d.version}${d.commit ? " · " + d.commit.slice(0, 8) : ""}` }))}
            onChange={value => { setSelectedRelease(value); setRobotId(undefined); clearInputs(); setReplaceCredentials(true); form.setFieldValue("robot_id", undefined); form.setFieldValue("credentials", {}); }} /></Form.Item>
          {application && <Tag>v{application.version}</Tag>}<Button type="link" disabled={!schema || busy} onClick={() => setParameterOpen(true)}>参数</Button>
        </div>
        <p className="muted">{!application ? "应用来自机器人上报的已部署程序。" : !robot ? "选择执行机器人后，填写对应程序的参数。" : invalidSchema ? "该程序的参数声明无效，暂时不能提交运行。" : schema ? `包含 ${Object.keys(schema.properties ?? {}).length} 个输入参数。` : "该程序尚未提供参数表单，请在下方填写业务参数。"}</p>
        <Form.Item name="robot_id" label="执行机器人" rules={[{ required: true, message: "请选择执行机器人" }]}><Select aria-label="执行机器人" placeholder="请选择执行机器人" disabled={!application || busy}
          onChange={value => { setRobotId(value); clearInputs(); }} options={application?.robots.map(r => ({ value: r.id, label: `${r.name} · ${r.online ? r.active_run ? "运行中" : "空闲" : "离线"}` }))} /></Form.Item>
        {robot && !robot.online && <Alert type="warning" showIcon message="机器人当前离线，任务将等待机器人连接后执行。" />}
        {invalidSchema && <Alert className="mb" type="error" showIcon message="应用参数声明损坏" description={deployment?.schema_error || "请更新执行端部署后重试"} />}
        {deployment && !schema && !invalidSchema && <Form.Item label="业务参数（旧版程序）"><Input.TextArea aria-label="旧版业务参数 JSON" placeholder="填写程序需要的 JSON 参数，无参数时填写 {}" rows={5} value={legacyInputs} onChange={e => setLegacyInputs(e.target.value)} /></Form.Item>}
      </div>
      <h2 className="form-section-title">登录配置</h2>
      {task && !replaceCredentials && <Space className="mb"><Tag>账号密码已配置</Tag><Button onClick={() => setReplaceCredentials(true)}>重新填写账号密码</Button></Space>}
      {replaceCredentials && <><Form.Item name={["credentials", "username"]} label="登录账号" rules={[{ required: true, whitespace: true, message: "请输入登录账号" }]}><Input autoComplete="off" placeholder="请输入业务平台登录账号" onChange={() => form.setFieldValue(["credentials", "password"], undefined)} /></Form.Item>
      <Form.Item name={["credentials", "password"]} label="登录密码" rules={[{ required: true, message: "请输入登录密码" }]}><Input.Password autoComplete="new-password" placeholder="请输入登录密码" /></Form.Item></>}
      <Form.Item name="download_dir" label="下载目录（可选）"><Input placeholder="使用执行端默认目录" /></Form.Item>
      <h2 className="form-section-title">触发配置</h2>
      {plan ? <PlanSchedule cron={cron} enabled={enabled} onCron={setCron} onEnabled={setEnabled} /> : <Space><Tag color="blue">手动触发</Tag><span>提交后加入执行队列</span></Space>}
    </Form><div className="task-editor-footer"><Button disabled={busy} onClick={() => navigate(plan ? "/tasks" : "/runs")}>取消</Button><Button type="primary" loading={busy} disabled={!robots || !!error || invalidSchema || (plan && !schema)} onClick={() => void submit()}>{plan ? "保存计划" : "立即执行"}</Button></div></Panel>
    {parameterOpen && schema && <ParameterModal relativeDates={plan} schema={schema} values={Object.fromEntries(Object.entries(inputs).map(([key, value]) => { const field = schema.properties?.[key]; return [key, plan && typeof field === "object" && field.format === "date" && typeof value === "string" ? { kind: "fixed", value } : value]; }))} onCancel={() => setParameterOpen(false)} onSave={values => { setInputs(values); setParameterOpen(false); setSubmitError(""); }} />}
  </div>;
}
