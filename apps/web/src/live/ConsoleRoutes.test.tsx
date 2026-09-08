import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { App as AntApp } from "antd";
import { ConsoleRoutes, consoleNavigation } from "../App";
vi.mock("./useResource", () => ({ useResource: (path: string) => ({
  data: path === "/robots" ? [{ id: "robot-live", name: "接口机器人", online: true, revoked: false, deployments: [{ app_id: "actual-program", version: "1.0" }] }] : [{ id: "real-run", name: "接口运行记录", status: "queued", created: 1, robot_id: "robot-live", snapshot: { app_id: "actual-program", version: "1.0", inputs: {} } }],
  error: "", refresh: () => {},
}) }));
const page = (path: string, admin = true) => renderToStaticMarkup(<AntApp><MemoryRouter initialEntries={[path]}><ConsoleRoutes user={{ name: "测试用户", admin }} /></MemoryRouter></AntApp>);
describe("统一控制台路由", () => {
  it("任务与运行记录均显示接口返回的数据", () => {
    for (const path of ["/tasks", "/runs"]) {
      const html = page(path);
      expect(html).toContain("接口运行记录");
      expect(html).toContain("/runs/real-run");
      expect(html).not.toContain("商品日报 · 全部门店");
    }
  });
  it("新建任务保留当前表单并提交真实执行，不再模拟保存", () => {
    const html = page("/tasks/new");
    for (const label of ["请选择执行应用", "请选择执行机器人", "登录账号", "登录密码", "立即执行"]) expect(html).toContain(label);
    expect(html).not.toContain("登录后预期可见身份");
    expect(html).not.toContain("演示版");
    expect(html).not.toContain("保存任务");
  });
  it("只读成员不出现管理导航或新建入口", () => {
    expect(consoleNavigation(false).map(n => n.path)).toEqual(["/business/runs"]);
    const html = page("/business/runs", false);
    expect(html).toContain("/business/runs/real-run");
    expect(html).not.toContain("新建任务");
  });
});
