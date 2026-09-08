import type { RJSFSchema } from "@rjsf/utils";
import type { RobotRecord } from "./api";
export type Deployment = RobotRecord["deployments"][number];
export const releaseKey = (release: Deployment) => JSON.stringify([release.app_id, release.version]);
export function inputSchemaFor(release?: Deployment): RJSFSchema | undefined {
  const inputs = release?.form_schema?.properties?.inputs;
  return release?.input_schema || (inputs && typeof inputs === "object" ? inputs : undefined);
}
export function deployedApplications(robots: RobotRecord[]) {
  const releases = new Map<string, Deployment & { robots: RobotRecord[] }>();
  for (const robot of robots.filter(r => !r.revoked)) for (const deployment of robot.deployments) {
    const key = releaseKey(deployment);
    const previous = releases.get(key);
    if (previous) previous.robots.push(robot);
    else releases.set(key, { ...deployment, robots: [robot] });
  }
  return [...releases.values()];
}
