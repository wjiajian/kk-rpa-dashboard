import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { TokenUsage } from "./TokenUsage";

it("shows total and cached input without counting cache twice", () => {
  const html = renderToStaticMarkup(<TokenUsage usage={{ input: 100, output: 50, cache_read: 200, cache_write: 0, total: 350, requests: 3, unreported_responses: 1 }} />);
  expect(html).toContain("350");
  expect(html).toContain("300");
  expect(html).toContain("50");
  expect(html).toContain("部分响应未返回用量");
});

it("missing usage is not displayed as zero", () => {
  expect(renderToStaticMarkup(<TokenUsage usage={undefined} />)).toContain("尚未记录");
});
