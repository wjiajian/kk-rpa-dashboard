import { useEffect, useState } from "react";
import {
  Alert,
  App,
  Button,
  Input,
  Progress,
  Radio,
  Result,
  Space,
  Steps,
  Table,
  Tag,
  Upload,
} from "antd";
import { InboxOutlined } from "@ant-design/icons";
import { Link } from "react-router-dom";
import { useStore } from "../mock/store";
import { today, type Application } from "../mock/data";
import { PageTitle, Panel } from "../components/shared";
import { parameterDefaults, reportSchema } from "../form/parameters";
import { SchemaForm } from "../form/SchemaForm";
export default function ImportWizard() {
  const { setApps } = useStore();
  const { message } = App.useApp();
  const [step, setStep] = useState(0);
  const [source, setSource] = useState("git");
  const [url, setUrl] = useState("");
  const [ref, setRef] = useState("main");
  const [file, setFile] = useState("");
  const [progress, setProgress] = useState(0);
  const [keys, setKeys] = useState<React.Key[]>(["demo-sales"]);
  const candidates: Application[] = [
    {
      id: "demo-sales",
      inputSchema: reportSchema,
      name: "销售日报汇总",
      description: "按门店汇总每日销售指标。",
      tags: ["经营报表", "数据汇总"],
      source: source === "git" ? url : "上传包",
      version: "1.0.0",
      valid: true,
      imported: today,
    },
    {
      id: "demo-legacy",
      name: "历史数据归档",
      description: "整理历史业务数据。",
      tags: ["数据同步", "数据归档"],
      source: source === "git" ? url : "上传包",
      version: "0.1.0",
      valid: false,
      imported: today,
    },
  ];
  useEffect(() => {
    if (step !== 1) return;
    const timer = setInterval(
      () => setProgress((p) => Math.min(p + 20, 100)),
      350,
    );
    return () => clearInterval(timer);
  }, [step]);
  useEffect(() => {
    if (progress === 100 && step === 1) setStep(2);
  }, [progress, step]);
  return (
    <>
      <PageTitle
        back
        title="导入应用"
        description="从代码仓库或源码包导入应用，预览参数声明后确认。"
      />
      <Alert
        className="mb"
        showIcon
        type="info"
        message="演示流程：不会拉取 Git 仓库或读取 ZIP 内容，下方将展示预置应用。"
      />
      <Panel>
        <div className="wizard">
          <Steps
            current={step}
            items={["选择来源", "导入中", "预览应用", "确认结果"].map(
              (title) => ({ title }),
            )}
          />
          {step === 0 && (
            <div className="wizard-content">
              <Radio.Group
                value={source}
                onChange={(e) => setSource(e.target.value)}
                optionType="button"
                options={[
                  { label: "Git 仓库", value: "git" },
                  { label: "上传 ZIP", value: "zip" },
                ]}
              />
              {source === "git" ? (
                <>
                  <label>仓库地址</label>
                  <Input
                    aria-label="仓库地址"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="https://github.com/team/rpa-apps.git"
                  />
                  <label>分支 / Tag / Commit</label>
                  <Input
                    aria-label="分支"
                    value={ref}
                    onChange={(e) => setRef(e.target.value)}
                  />
                </>
              ) : (
                <Upload.Dragger
                  accept=".zip"
                  maxCount={1}
                  beforeUpload={(f) => {
                    if (!f.name.toLowerCase().endsWith(".zip")) {
                      message.error("请选择 ZIP 文件");
                      return Upload.LIST_IGNORE;
                    }
                    setFile(f.name);
                    return false;
                  }}
                  onRemove={() => setFile("")}
                >
                  <p className="ant-upload-drag-icon">
                    <InboxOutlined />
                  </p>
                  <p>点击或拖拽 ZIP 源码包到这里</p>
                  <p className="muted">仅在本地选择，不上传文件</p>
                </Upload.Dragger>
              )}
              <Button
                type="primary"
                onClick={() => {
                  if (
                    source === "git" &&
                    (!/^(https?:\/\/|git@).+/.test(url) || !ref.trim())
                  ) {
                    message.error("请填写有效仓库地址和版本引用");
                    return;
                  }
                  if (source === "zip" && !file) {
                    message.error("请选择 ZIP 源码包");
                    return;
                  }
                  setStep(1);
                }}
              >
                开始模拟导入
              </Button>
            </div>
          )}
          {step === 1 && (
            <div className="wizard-content">
              <h2>正在模拟解析应用声明</h2>
              <Progress percent={progress} />
              <p className="muted">识别应用入口、版本与参数表单…</p>
            </div>
          )}
          {step === 2 && (
            <div className="wizard-preview">
              <Table
                rowKey="id"
                pagination={false}
                dataSource={candidates}
                rowSelection={{
                  selectedRowKeys: keys,
                  onChange: setKeys,
                  getCheckboxProps: (a) => ({ disabled: !a.valid }),
                }}
                expandable={{
                  expandedRowRender: (a) =>
                    a.valid ? (
                      <SchemaForm
                        readonly
                        schema={a.inputSchema}
                        data={parameterDefaults(a.inputSchema)}
                      />
                    ) : (
                      <Alert
                        type="error"
                        message="缺少 form.schema.json，无法创建任务。"
                      />
                    ),
                }}
                columns={[
                  { title: "识别出的应用", dataIndex: "name" },
                  { title: "版本", dataIndex: "version" },
                  {
                    title: "参数声明",
                    render: (_, a) => (
                      <Tag color={a.valid ? "green" : "orange"}>
                        {a.valid ? "校验通过" : "缺少参数表单声明"}
                      </Tag>
                    ),
                  },
                ]}
              />
              <div className="wizard-footer">
                <Button
                  onClick={() => {
                    setStep(0);
                    setProgress(0);
                  }}
                >
                  上一步
                </Button>
                <Button
                  type="primary"
                  disabled={!keys.length}
                  onClick={() => {
                    setApps((old) => [
                      ...old.filter((a) => !keys.includes(a.id)),
                      ...candidates.filter((a) => keys.includes(a.id)),
                    ]);
                    setStep(3);
                  }}
                >
                  确认导入 {keys.length} 个应用
                </Button>
              </div>
            </div>
          )}
          {step === 3 && (
            <Result
              status="success"
              title="模拟应用已导入"
              subTitle={`已建立 ${keys.length} 个应用及其 v1.0.0 版本，可继续创建任务。`}
              extra={
                <Space>
                  <Link to="/applications">
                    <Button>返回应用中心</Button>
                  </Link>
                  <Link to="/tasks/new?app=demo-sales">
                    <Button type="primary">创建任务</Button>
                  </Link>
                </Space>
              }
            />
          )}
        </div>
      </Panel>
    </>
  );
}
