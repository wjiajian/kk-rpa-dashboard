# KK RPA 控制台

基于 `docs/rpa-console-frontend.md` 的第一版前端演示。React 18、TypeScript、Vite、Ant Design 5、RJSF。

## 本地运行

```sh
pnpm install
pnpm dev
```

访问 http://127.0.0.1:5173。构建：`pnpm build`；测试：`pnpm test`。

## 已实现

- 工作总览、应用列表与版本详情、四步模拟导入。
- 任务创建/编辑、日期绑定、凭据已配置状态、Cron 五次触发预览、启停定时。
- 运行筛选与详情、业务日志、执行尝试、取消排队、请求停止、从头重跑。
- 机器人与队列、管理员名单、数据保留设置、只读成员视图。
- 点击右上角管理员菜单可切换只读成员，检验页面和导航权限。

## 演示边界

所有数据与操作均在浏览器内存中模拟，刷新恢复初始数据。密码只保留输入期间的临时状态，保存后丢弃，仅记录“已配置”。示例应用共用演示参数声明；真实应用的 Schema、版本、来源解析待后端接入。

Git/ZIP 导入不会拉取仓库、读取归档或上传文件；模拟运行只加入队列，不执行真实任务或自动推进状态。日志为静态样例；失败截图显示明确的缺失说明。相对日期暂不解析，等待后端创建运行时处理。

飞书登录、后端权限、API/OpenAPI 客户端、TanStack Query 数据层、SSE、真实调度、部署和机器人连接尚未接入。Vite 已预留 `/api` 到 `http://127.0.0.1:8000` 的同源开发代理。

## 目录

- `apps/web/src/pages`：页面与交互
- `apps/web/src/mock`：演示模型、数据和状态
- `apps/web/src/form`：Schema 表单、日期规则、提交装配
- `apps/web/src/schedule`：Cron 编辑与计算
- `apps/web/src/components`：共享展示组件

生产构建输出 `apps/web/dist`；静态托管需要为前端路由配置回退到 `index.html`。
