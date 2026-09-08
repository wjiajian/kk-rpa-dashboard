import { useEffect, useState } from "react";
import { Alert, App, Button, Form, Input, Select, Space, Tag } from "antd";
import { AppstoreOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { PageTitle, Panel } from "../components/shared";
import { ParameterModal } from "../form/ParameterModal";
import { parameterError, type ParameterValues } from "../form/parameters";
import { api, type RobotRecord } from "./api";
import { useResource } from "./useResource";
import { deployedApplications, inputSchemaFor, releaseKey } from "./deployments";

export default function NewTask() {
  const { data: robots, error, refresh } = useResource<RobotRecord[]>("/robots", 10000);
  const [form] = Form.useForm();
  const selectedRelease = Form.useWatch("release", form);
  const robotId = Form.useWatch("robot_id", form);
  const releases = deployedApplications(robots || []);
  const application = releases.find(d => releaseKey(d) === selectedRelease);
  const robot = robots?.find(r => r.id === robotId && !r.revoked);
  const deployment = robot?.deployments.find(d => releaseKey(d) === selectedRelease);
  // Read the chosen robot's declaration: two machines can have different deployments.
  const schema = inputSchemaFor(deployment);
  const [inputs, setInputs] = useState<ParameterValues>({});
  const [legacyInputs, setLegacyInputs] = useState("");
  const [parameterOpen, setParameterOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const { message } = App.useApp();
  const navigate = useNavigate();
  useEffect(() => { setInputs({}); setLegacyInputs(""); setParameterOpen(false); setSubmitError(""); }, [selectedRelease, robotId, JSON.stringify(schema)]);
  const submit = async () => {
    if (busy) return;
    try {
      const values = await form.validateFields();
      if (!deployment || !robot) throw new Error("请选择仍部署该应用版本的机器人");
      let actualInputs = inputs;
      if (schema) {
        const problem = parameterError(schema, inputs);
        if (problem) { setParameterOpen(true); throw new Error(problem); }
      } else {
        try { actualInputs = JSON.parse(legacyInputs); } catch { throw new Error("请输入有效的业务参数 JSON 对象；无参数时填写 {}"); }
        if (!actualInputs || Array.isArray(actualInputs) || typeof actualInputs !== "object") throw new Error("业务参数必须为 JSON 对象");
      }
      setBusy(true); setSubmitError("");
      const run = await api<{ id: string }>("/runs", { name: values.name.trim(), robot_id: robot.id, credentials: values.credentials,
        snapshot: { app_id: deployment.app_id, version: deployment.version, inputs: actualInputs, download_dir: values.download_dir || null } });
      form.resetFields();
      message.success("任务已加入执行队列");
      navigate(`/runs/${run.id}`);
    } catch (error) { if (error instanceof Error) setSubmitError(error.message); }
    finally { setBusy(false); }
  };
  return <div className="task-editor">
    <PageTitle back title="新建任务" description="选择应用、填写参数，交给机器人执行。" />
    {error && <Alert className="mb" type="error" showIcon message={error} action={<Button onClick={refresh}>重试</Button>} />}
    {submitError && <Alert className="mb" type="error" showIcon message={submitError} />}
    <Panel><Form form={form} layout="vertical" disabled={busy} requiredMark className="form-body" onFinish={() => void submit()}>
      <Form.Item name="name" label="任务名称" rules={[{ required: true, whitespace: true, message: "请输入任务名称" }]}><Input placeholder="请输入任务名称" maxLength={200} /></Form.Item>
      <h2 className="form-section-title">应用与机器人</h2>
      <div className="application-config">
        <label htmlFor="execution-app">执行应用</label>
        <div className="application-selection"><AppstoreOutlined />
          <Form.Item name="release" noStyle rules={[{ required: true, message: "请选择执行应用" }]}><Select id="execution-app" aria-label="执行应用" placeholder="请选择执行应用" showSearch optionFilterProp="label" loading={!robots && !error}
            options={releases.map(d => ({ value: releaseKey(d), label: `${d.app_id} · v${d.version}` }))}
            onChange={() => { form.setFieldValue("robot_id", undefined); form.setFieldValue("credentials", {}); }} /></Form.Item>
          {application && <Tag>v{application.version}</Tag>}<Button type="link" disabled={!schema || busy} onClick={() => setParameterOpen(true)}>参数</Button>
        </div>
        <p className="muted">{!application ? "应用来自机器人上报的已部署程序。" : !robot ? "选择执行机器人后，填写对应程序的参数。" : schema ? `包含 ${Object.keys(schema.properties ?? {}).length} 个输入参数。` : "该程序尚未提供参数表单，请在下方填写业务参数。"}</p>
        <Form.Item name="robot_id" label="执行机器人" rules={[{ required: true, message: "请选择执行机器人" }]}><Select aria-label="执行机器人" placeholder="请选择执行机器人" disabled={!application || busy}
          options={application?.robots.map(r => ({ value: r.id, label: `${r.name} · ${r.online ? r.active_run ? "运行中" : "空闲" : "离线"}` }))} /></Form.Item>
        {robot && !robot.online && <Alert type="warning" showIcon message="机器人当前离线，任务将等待机器人连接后执行。" />}
        {deployment && !schema && <Form.Item label="业务参数（旧版程序）"><Input.TextArea aria-label="旧版业务参数 JSON" placeholder="填写程序需要的 JSON 参数，无参数时填写 {}" rows={5} value={legacyInputs} onChange={e => setLegacyInputs(e.target.value)} /></Form.Item>}
      </div>
      <h2 className="form-section-title">登录配置</h2>
      <Form.Item name={["credentials", "username"]} label="登录账号" rules={[{ required: true, whitespace: true, message: "请输入登录账号" }]}><Input autoComplete="off" placeholder="请输入业务平台登录账号" onChange={() => form.setFieldValue(["credentials", "password"], undefined)} /></Form.Item>
      <Form.Item name={["credentials", "password"]} label="登录密码" rules={[{ required: true, message: "请输入登录密码" }]}><Input.Password autoComplete="new-password" placeholder="请输入登录密码" /></Form.Item>
      <Form.Item name="download_dir" label="下载目录（可选）"><Input placeholder="使用执行端默认目录" /></Form.Item>
      <h2 className="form-section-title">触发配置</h2>
      <Space><Tag color="blue">手动触发</Tag><span>提交后加入执行队列</span></Space>
      <p className="muted">当前服务尚未接入定时计划，定时功能接入后将在这里配置。</p>
    </Form><div className="task-editor-footer"><Button disabled={busy} onClick={() => navigate("/tasks")}>取消</Button><Button type="primary" loading={busy} disabled={!robots || !!error} onClick={() => void submit()}>立即执行</Button></div></Panel>
    {parameterOpen && schema && <ParameterModal schema={schema} values={inputs} onCancel={() => setParameterOpen(false)} onSave={values => { setInputs(values); setParameterOpen(false); setSubmitError(""); }} />}
  </div>;
}
