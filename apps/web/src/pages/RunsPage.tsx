import { useState } from "react";
import { DatePicker, Input, Select, Table, Tag } from "antd";
import { SearchOutlined } from "@ant-design/icons";
import { Link, useSearchParams } from "react-router-dom";
import { useStore } from "../mock/store";
import { time, type Status } from "../mock/data";
import { PageTitle, Panel, StatusTag } from "../components/shared";
const statuses: Status[] = [
  "排队中",
  "启动中",
  "运行中",
  "停止中",
  "Agent 接管中",
  "成功",
  "失败",
  "已取消",
  "已停止",
  "状态待确认",
];
export default function RunsPage({ business = false }: { business?: boolean }) {
  const { runs } = useStore();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [range, setRange] = useState<[string, string] | null>(null);
  const status = params.get("status") || undefined;
  const data = runs
    .filter(
      (r) =>
        (!status || r.status === status) &&
        r.name.includes(search) &&
        (!range ||
          (time(r.created, "YYYY-MM-DD") >= range[0] &&
            time(r.created, "YYYY-MM-DD") <= range[1])),
    )
    .sort((a, b) => b.created.localeCompare(a.created));
  return (
    <>
      <PageTitle
        title={business ? "业务运行" : "运行记录"}
        description={
          business
            ? "查看业务执行进度、日志与结果。"
            : "追踪每一次执行，从触发到完成。"
        }
        actions={<Tag bordered={false}>演示数据</Tag>}
      />
      <Panel>
        <div className="filter-bar">
          {!business && (
            <Input
              prefix={<SearchOutlined />}
              placeholder="搜索任务名称"
              allowClear
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          )}
          <Select
            aria-label="运行状态"
            placeholder="全部状态"
            allowClear
            value={status}
            options={statuses.map((s) => ({ label: s, value: s }))}
            onChange={(s) => setParams(s ? { status: s } : {})}
          />
          <DatePicker.RangePicker
            onChange={(_, values) =>
              setRange(values[0] && values[1] ? values : null)
            }
          />
          <span className="muted">共 {data.length} 条</span>
        </div>
        <Table
          rowKey="id"
          dataSource={data}
          scroll={{ x: business ? 650 : 1000 }}
          pagination={{ pageSize: 8, showTotal: (n) => `共 ${n} 条运行` }}
          columns={[
            {
              title: "运行名称",
              render: (_, r) => (
                <Link to={`${business ? "/business" : ""}/runs/${r.id}`}>
                  <strong>{r.name}</strong>
                  {!business && <div className="mono muted small">{r.id}</div>}
                </Link>
              ),
            },
            {
              title: "状态",
              dataIndex: "status",
              render: (s) => <StatusTag status={s} />,
            },
            ...(!business
              ? [
                  {
                    title: "触发来源",
                    dataIndex: "source",
                    render: (s: string) => <Tag bordered={false}>{s}</Tag>,
                  },
                  { title: "机器人", dataIndex: "robot" },
                ]
              : []),
            {
              title: "创建时间",
              dataIndex: "created",
              render: (v: string) => <span className="mono">{time(v)}</span>,
            },
            { title: "耗时", dataIndex: "duration" },
            {
              title: "操作",
              render: (_, r) => (
                <Link to={`${business ? "/business" : ""}/runs/${r.id}`}>
                  查看详情
                </Link>
              ),
            },
          ]}
        />
      </Panel>
    </>
  );
}
