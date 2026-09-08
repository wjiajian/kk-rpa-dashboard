import { expect, it } from "vitest";
import { deployedApplications, inputSchemaFor, releaseKey } from "./deployments";
import type { RobotRecord } from "./api";

const robot = (id: string, revoked = false): RobotRecord => ({ id, name: id, online: true, revoked, deployments: [{ app_id: "report", version: "1.0" }] });
it("应用版本聚合部署机器人并排除已撤销的机器人", () => {
  const apps = deployedApplications([robot("one"), robot("two"), robot("revoked", true)]);
  expect(apps).toHaveLength(1);
  expect(apps[0].robots.map(r => r.id)).toEqual(["one", "two"]);
  expect(releaseKey({ app_id: "a@b", version: "c" })).not.toEqual(releaseKey({ app_id: "a", version: "b@c" }));
});
it("参数声明只取程序提供的业务输入，不暴露凭据表单", () => {
  const inputs = { type: "object" as const, properties: { batch: { type: "integer" as const } } };
  expect(inputSchemaFor({ app_id: "a", version: "v", form_schema: { properties: { inputs, credentials: { type: "object" } } } })).toEqual(inputs);
  expect(inputSchemaFor({ app_id: "a", version: "v" })).toBeUndefined();
});
