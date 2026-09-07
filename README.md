# KK RPA 控制台

RPA 控制台与失败接管 Agent。包含 React 前端、Python/FastAPI 运行控制后端、独立 pi Agent 服务和 macOS Docker 部署配置。Windows 执行端与核心接入扩展位于同级 `kk-rpa-monorepo`。

失败接管的实现、配置与验收状态见 [接管实施说明](docs/recovery-implementation.md)，原规格见 [Dashboard RPA 失败接管](workflows/dashboard-rpa-recovery.md)。代码与离线接口已验证；Windows 真实业务、飞书登录与 DeepSeek 官方模型的现场验收尚未进行。

## 真实运行模式

测试部署复用 Mac 已运行的 PostgreSQL，使用 ngrok 提供 HTTPS/WSS。保持一个终端运行 `ngrok http 8088 --inspect=false`，另一个终端运行 `python3 deploy/mac.py prepare`。只填写生成的 `deploy/.env` 顶部五项飞书/DeepSeek 配置，登记脚本打印的飞书回调，再运行 `python3 deploy/mac.py up`。

Windows 拉取同级 monorepo 的最新代码，在仓库根目录运行 `.\packages\rpa-executor\start.ps1`；首次输入连接地址和账号凭据后，后续复用本机加密配置。完整步骤见 [简化测试部署](docs/recovery-implementation.md#简化测试部署现有-postgresql--ngrok)。

镜像启用真实模式，提供运行列表/详情、运行发起与重跑、机器人凭据管理、SSE 事件、证据和停止请求。

本地前端使用 `VITE_RUNTIME=live pnpm dev`，通过 `/api` 连接 8000 端口的后端。真实模式不会在接口失败时退回演示状态。应用导入、任务编辑与定时等其余页面仍属于下文的演示模式。

开发验证：`pnpm build`、`pnpm test`、`pnpm test:backend`。后端使用 `uv sync --project apps/backend` 安装锁定依赖。

## 本地运行

不设置 `VITE_RUNTIME=live` 时，保留原有前端演示：

```sh
pnpm install
pnpm dev
```

访问 http://127.0.0.1:5173。构建：`pnpm build`；测试：`pnpm test`。

## 演示页面

- 工作总览、应用列表与版本详情、四步模拟导入。
- 任务创建/编辑、日期绑定、凭据已配置状态、Cron 五次触发预览、启停定时。
- 运行筛选与详情、业务日志、执行尝试、取消排队、请求停止、从头重跑。
- 机器人与队列、管理员名单、数据保留设置、只读成员视图。
- 点击右上角管理员菜单可切换只读成员，检验页面和导航权限。

## 演示边界

所有数据与操作均在浏览器内存中模拟，刷新恢复初始数据。密码只保留输入期间的临时状态，保存后丢弃，仅记录“已配置”。示例应用共用演示参数声明；真实应用的 Schema、版本、来源解析待后端接入。

Git/ZIP 导入不会拉取仓库、读取归档或上传文件；模拟运行只加入队列，不执行真实任务或自动推进状态。日志为静态样例；失败截图显示明确的缺失说明。相对日期暂不解析，等待后端创建运行时处理。

演示模式不连接后端或机器人；运行相关的飞书登录、权限、SSE 和机器人连接通过上文的真实运行模式提供。真实调度与应用导入仍待接入。Vite 使用 `/api` 到 `http://127.0.0.1:8000` 的同源开发代理。

## 目录

- `apps/web/src/pages`：页面与交互
- `apps/web/src/mock`：演示模型、数据和状态
- `apps/web/src/form`：Schema 表单、日期规则、提交装配
- `apps/web/src/schedule`：Cron 编辑与计算
- `apps/web/src/components`：共享展示组件

生产构建输出 `apps/web/dist`；静态托管需要为前端路由配置回退到 `index.html`。
