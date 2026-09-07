import { Empty, Tag } from "antd";
import { Panel } from "../components/shared";
import { date, type RunEvent } from "./api";

const agentKinds = new Set(["agent_activity", "agent_summary", "recovery_started"]);

export function ExecutionLog({ events, business }: { events: RunEvent[]; business: boolean }) {
  const ordered = [...events].sort((a, b) => b.at - a.at || b.seq - a.seq);
  const agentEvents = ordered.filter(event => agentKinds.has(event.kind));
  const rows = ordered
    .filter(event => !agentKinds.has(event.kind) && event.kind !== "operation")
    .map(event => ({ key: String(event.seq), event }));
  if (agentEvents.length) rows.push({ key: "agent", event: agentEvents[0] });
  rows.sort((a, b) => b.event.at - a.event.at || b.event.seq - a.event.seq);

  return <Panel title="执行过程" extra={<Tag>{rows.length} 条日志</Tag>}>
    <div className="log-stream">
      {rows.length ? rows.map(({ key, event }) => <div className="log-line" key={key}>
        <span className="log-time mono">{date(event.at)}</span>
        <div className="log-content">
          {key === "agent" ? <details className="agent-log">
            <summary>Agent 执行情况 <span className="small">· 点击查看</span></summary>
            <div className="agent-log-body" tabIndex={0} role="region" aria-label="Agent 执行详情">
              {agentEvents.map(item => <div className="agent-log-item" key={item.seq}>
                <span className="log-time mono">{date(item.at)}</span>
                <div>{item.message}</div>
              </div>)}
            </div>
          </details> : <>
            <strong className="log-message">{event.message}</strong>
            {!business && event.details && Object.keys(event.details).length > 0 && <details>
              <summary>查看执行结果</summary>
              <pre className="log-message">{JSON.stringify(event.details, null, 2)}</pre>
            </details>}
          </>}
        </div>
      </div>) : <Empty description="尚无执行事件" />}
    </div>
  </Panel>;
}
