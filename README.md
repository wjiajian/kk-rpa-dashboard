# KK RPA 控制台

RPA 控制台与失败接管 Agent。包含 React 前端、Python/FastAPI 运行控制后端、独立 pi Agent 服务和 Docker Compose 部署配置。实际服务端为 Linux，Mac 仅作为开发测试服务端。Windows 执行端与核心接入扩展位于同级 `kk-rpa-monorepo`。

分享交流文档见 [技术分享导读](docs/sharing/README.md)，包含 [Monorepo 技术说明](docs/sharing/monorepo.md) 和 [Dashboard 技术说明](docs/sharing/dashboard.md)：框架、技术选型、设计思路、实现进度与待完成内容。

失败接管的实现、配置与验收状态见 [接管实施说明](docs/recovery-implementation.md)，原规格见 [Dashboard RPA 失败接管](workflows/dashboard-rpa-recovery.md)。代码与离线接口已验证；Windows 真实业务、飞书登录与 DeepSeek 官方模型的现场验收尚未进行。

## 真实运行模式

测试部署复用 Mac 已运行的 PostgreSQL，使用 ngrok 提供 HTTPS/WSS。保持一个终端运行 `ngrok http 8088 --inspect=false`，另一个终端运行 `python3 deploy/mac.py prepare`。只填写生成的 `deploy/.env` 顶部五项飞书/DeepSeek 配置，登记脚本打印的飞书回调，再运行 `python3 deploy/mac.py up`。

Windows 拉取同级 monorepo 的最新代码，在仓库根目录运行 `.\packages\rpa-executor\start.ps1`；首次只输入连接地址和机器人连接凭据；业务账号和密码在控制台发起运行时填写。完整步骤见 [测试部署文档](docs/test-deployment.md)。

[完整配置示例](deploy/.env.example) 保留所有部署字段。Linux 独立填写自己的 `.env`，准备应用数据库和正式 HTTPS 入口，再使用 Compose 启动；不依赖 Mac、ngrok 或 `mac.py`。具体约定见测试部署文档的 Linux 章节。

本地开发和部署统一使用同一套控制台界面，不再通过 `VITE_RUNTIME` 切换演示/测试页面。工作总览、应用中心、任务创建、运行记录及机器人管理均读取真实接口；接口失败时显示错误，不回退示例数据。

新建任务按“应用 → 机器人 → 参数 → 登录配置”填写，提交后直接加入执行队列。默认不预选应用、机器人或业务参数。应用来自机器人上报的已部署版本。旧版部署未上报参数声明时，保留 JSON 参数输入。当前后端不支持保存可复用计划和定时调度，界面仅提供实际可用的手动触发。

开发验证：`pnpm build`、`pnpm test`、`pnpm test:backend`。后端使用 `uv sync --project apps/backend` 安装锁定依赖。

## 本地运行

本地开发前端：

```sh
pnpm install
pnpm dev
```

访问 http://127.0.0.1:5173。构建：`pnpm build`；测试：`pnpm test`。

## 统一测试入口

`pnpm dev` 的 `/api` 默认代理本机 Compose 服务 `http://127.0.0.1:8088`。独立启动后端时可在前端环境文件中配置 `RPA_API_TARGET=http://127.0.0.1:8000`。飞书登录和管理请求继续遵守后端的 `PUBLIC_URL` 来源校验，完整联调请从已配置的 HTTPS 控制台地址进入。

- 工作总览和任务列表：最近 500 次真实运行，可按名称、状态、应用筛选。
- 应用中心：由机器人部署信息聚合程序与版本。
- 新建任务：空值表单、按程序生成参数、账号/密码、下载目录、手动执行。
- 运行详情：取消排队、停止、从头重跑、SSE 日志、接管轮次、Token 用量和现场截图。
- 机器人管理：创建机器人、查看部署与占用、轮换或撤销连接凭据。
- 只读成员：身份来自飞书会话，仅能查看业务运行，不提供角色模拟切换。

原 `mock` 与演示页面源码保留作历史参考，不再挂载到应用路由。

## 目录

- `apps/web/src/pages`：页面与交互
- `apps/web/src/mock`：演示模型、数据和状态
- `apps/web/src/form`：Schema 表单、日期规则、提交装配
- `apps/web/src/schedule`：Cron 编辑与计算
- `apps/web/src/components`：共享展示组件

生产构建输出 `apps/web/dist`；静态托管需要为前端路由配置回退到 `index.html`。
