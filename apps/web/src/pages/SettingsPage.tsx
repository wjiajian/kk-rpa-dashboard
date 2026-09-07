import { useState } from "react";
import {
  App,
  Avatar,
  Button,
  Input,
  InputNumber,
  Space,
  Table,
  Tag,
} from "antd";
import { PlusOutlined, UserOutlined } from "@ant-design/icons";
import { useStore } from "../mock/store";
import { PageTitle, Panel } from "../components/shared";
export default function SettingsPage() {
  const { admins, setAdmins, retention, setRetention } = useStore();
  const [name, setName] = useState("");
  const [days, setDays] = useState<number | null>(retention);
  const { modal, message } = App.useApp();
  return (
    <>
      <PageTitle
        title="管理设置"
        description="管理控制台管理员与运行数据保留规则。"
      />
      <div className="settings-grid">
        <Panel
          title="管理员名单"
          extra={<Tag bordered={false}>{admins.length} 位管理员</Tag>}
        >
          <Table
            rowKey="name"
            pagination={false}
            dataSource={admins.map((name) => ({ name }))}
            columns={[
              {
                title: "飞书成员（示例）",
                render: (_, r) => (
                  <Space>
                    <Avatar icon={<UserOutlined />} />
                    {r.name}
                  </Space>
                ),
              },
              {
                title: "权限",
                render: () => (
                  <Tag color="blue" bordered={false}>
                    管理员
                  </Tag>
                ),
              },
              {
                title: "操作",
                render: (_, r) => (
                  <Button
                    type="link"
                    danger
                    onClick={() =>
                      modal.confirm({
                        title: `移除管理员 ${r.name}？`,
                        content:
                          "移除后立即失去管理权限，仅保留业务运行只读权限。本次仅更新演示名单。",
                        onOk: () =>
                          setAdmins((old) => old.filter((n) => n !== r.name)),
                      })
                    }
                  >
                    移除
                  </Button>
                ),
              },
            ]}
          />
          <div className="panel-padding">
            <Space.Compact block>
              <Input
                aria-label="添加管理员姓名"
                placeholder="输入示例成员姓名"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <Button
                icon={<PlusOutlined />}
                onClick={() => {
                  if (!name.trim() || admins.includes(name.trim())) {
                    message.error("请填写未添加的成员姓名");
                    return;
                  }
                  setAdmins((old) => [...old, name.trim()]);
                  setName("");
                  message.success("已添加模拟管理员");
                }}
              >
                添加管理员
              </Button>
            </Space.Compact>
          </div>
        </Panel>
        <Panel title="数据保留">
          <div className="form-body">
            <label>运行记录、日志和截图</label>
            <Space>
              <InputNumber
                aria-label="保留天数"
                min={1}
                precision={0}
                value={days}
                onChange={setDays}
              />
              天
            </Space>
            <p className="muted">
              从运行结束时开始计算。活跃运行保留至结束，任务配置与业务文件不受影响。
            </p>
            <Button
              type="primary"
              onClick={() => {
                if (!days || !Number.isInteger(days) || days < 1) {
                  message.error("请输入至少 1 天的整数");
                  return;
                }
                modal.confirm({
                  title: `将保留期限改为 ${days} 天？`,
                  content:
                    "新规则即时生效，过期运行记录、日志与截图将按规则清理。演示版不会删除真实数据。",
                  onOk: () => {
                    setRetention(days);
                    message.success("演示保留期限已更新");
                  },
                });
              }}
            >
              保存保留规则
            </Button>
          </div>
        </Panel>
      </div>
    </>
  );
}
