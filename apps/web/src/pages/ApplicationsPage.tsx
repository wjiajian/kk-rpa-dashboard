import { useState } from "react";
import { Button, Input, Space, Table, Tag, Alert, Select, Empty } from "antd";
import { ImportOutlined, SearchOutlined } from "@ant-design/icons";
import { Link, useParams } from "react-router-dom";
import { useStore } from "../mock/store";
import { PageTitle, Panel, NotFound } from "../components/shared";
import { ApplicationTagEditor } from "../components/ApplicationTagEditor";
import { SchemaForm } from "../form/SchemaForm";
export default function ApplicationsPage() {
  const { apps, tasks } = useStore();
  const [search, setSearch] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const availableTags = [...new Set(apps.flatMap((app) => app.tags))];
  const filteredApps = apps.filter(
    (app) =>
      `${app.name} ${app.id}`
        .toLowerCase()
        .includes(search.trim().toLowerCase()) &&
      (!tags.length || app.tags.some((tag) => tags.includes(tag))),
  );
  return (
    <>
      <PageTitle
        title="应用中心"
        description="将业务流程封装为应用，以不同配置重复使用。"
        actions={
          <Link to="/applications/import">
            <Button type="primary" icon={<ImportOutlined />}>
              导入应用
            </Button>
          </Link>
        }
      />
      <Panel>
        <div className="filter-bar">
          <Input
            prefix={<SearchOutlined />}
            placeholder="搜索应用名称或 ID"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            allowClear
          />
          <Select
            mode="multiple"
            aria-label="按应用标签筛选"
            placeholder="按标签筛选"
            value={tags}
            onChange={setTags}
            allowClear
            maxTagCount="responsive"
            style={{ minWidth: 220 }}
            options={availableTags.map((tag) => ({ label: tag, value: tag }))}
          />
          <span className="muted">共 {filteredApps.length} 个应用</span>
        </div>
        <Table
          rowKey="id"
          dataSource={filteredApps}
          scroll={{ x: 1050 }}
          pagination={{
            pageSize: 8,
            showTotal: (total) => `共 ${total} 个应用`,
          }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="没有匹配的应用，请调整关键词或标签。"
              />
            ),
          }}
          columns={[
            {
              title: "应用名称 / ID",
              width: 210,
              render: (_, app) => (
                <Link to={`/applications/${app.id}`}>
                  <strong>{app.name}</strong>
                  <div className="mono muted small">{app.id}</div>
                </Link>
              ),
            },
            {
              title: "标签",
              dataIndex: "tags",
              width: 180,
              render: (appTags: string[]) => (
                <Space size={[4, 6]} wrap>
                  {!appTags.length && <span className="muted">暂无标签</span>}
                  {appTags.map((tag) => (
                    <Button
                      key={tag}
                      size="small"
                      type={tags.includes(tag) ? "primary" : "default"}
                      aria-pressed={tags.includes(tag)}
                      onClick={() =>
                        setTags((old) =>
                          old.includes(tag)
                            ? old.filter((item) => item !== tag)
                            : [...old, tag],
                        )
                      }
                      style={{ fontSize: 10, height: 24, paddingInline: 8 }}
                    >
                      {tag}
                    </Button>
                  ))}
                </Space>
              ),
            },
            { title: "应用说明", dataIndex: "description", width: 240 },
            { title: "来源", dataIndex: "source", width: 160 },
            {
              title: "最新版本",
              dataIndex: "version",
              width: 90,
              render: (version) => <span className="mono">v{version}</span>,
            },
            {
              title: "任务数",
              width: 75,
              render: (_, app) =>
                tasks.filter((task) => task.appId === app.id).length,
            },
            {
              title: "表单状态",
              width: 150,
              render: (_, app) => (
                <Tag bordered={false} color={app.valid ? "green" : "orange"}>
                  {app.valid ? "可用" : "缺少参数表单声明"}
                </Tag>
              ),
            },
            {
              title: "操作",
              fixed: "right",
              width: 230,
              render: (_, app) => (
                <Space>
                  <Link to={`/applications/${app.id}`}>详情</Link>
                  <ApplicationTagEditor application={app} />
                  {app.valid ? (
                    <Link to={`/tasks/new?app=${app.id}`}>创建任务</Link>
                  ) : (
                    <Button type="link" disabled size="small">
                      创建任务
                    </Button>
                  )}
                </Space>
              ),
            },
          ]}
        />
      </Panel>
    </>
  );
}
export function ApplicationDetail() {
  const { id } = useParams();
  const { apps } = useStore();
  const app = apps.find((a) => a.id === id);
  if (!app) return <NotFound />;
  return (
    <>
      <PageTitle
        back
        title={app.name}
        description={app.description}
        actions={
          app.valid ? (
            <Link to={`/tasks/new?app=${app.id}`}>
              <Button type="primary">基于该版本创建任务</Button>
            </Link>
          ) : (
            <Button disabled>缺少参数表单声明</Button>
          )
        }
      />
      <Space size={[6, 6]} wrap className="mb">
        {!app.tags.length && <span className="muted">暂无标签</span>}
        <ApplicationTagEditor application={app} />
        {app.tags.map((tag) => (
          <Tag key={tag} color="blue" bordered={false}>
            {tag}
          </Tag>
        ))}
      </Space>
      <Panel title="应用版本">
        <Table
          rowKey="version"
          pagination={false}
          dataSource={[app]}
          columns={[
            {
              title: "版本",
              dataIndex: "version",
              render: (v) => <Tag color="blue">v{v}</Tag>,
            },
            { title: "来源", dataIndex: "source" },
            {
              title: "Commit",
              render: () => (app.source === "上传包" ? "—" : "a72f9e1（示例）"),
            },
            { title: "导入时间", dataIndex: "imported" },
            {
              title: "表单状态",
              render: () => (app.valid ? "可用" : "缺少参数表单声明"),
            },
          ]}
        />
      </Panel>
      <Panel title="参数表单预览">
        <div className="form-body narrow">
          {app.valid ? (
            <>
              <Alert
                className="mb"
                message="示例参数声明 · 只读预览"
                type="info"
              />
              <SchemaForm
                readonly
                data={{ brand: "全部品牌", filename: "report.xlsx" }}
              />
              <Space>
                业务日期<Tag>固定日期 / 相对日期</Tag>
              </Space>
            </>
          ) : (
            <Alert
              message="缺少 form.schema.json，请为应用补齐参数表单声明后重新导入。"
              type="warning"
            />
          )}
        </div>
      </Panel>
    </>
  );
}
