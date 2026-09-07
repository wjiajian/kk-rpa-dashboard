# 测试部署指南与 Linux 服务端约定

本指南用于 Mac 测试服务端与 Windows 执行端联调。**实际服务端是 Linux 服务器**；Mac 只是开发阶段的临时测试环境。

| 项目 | Mac 测试环境 | Linux 实际服务端 |
| --- | --- | --- |
| 应用服务 | Docker Desktop 上的 Web、backend、Agent | Docker Engine + Compose 上的相同三个服务 |
| HTTPS/WSS 入口 | Mac 本机 ngrok → `127.0.0.1:8088` | 正式域名 → Linux HTTPS 反向代理 → `127.0.0.1:8088` |
| 数据库 | 复用 Mac 已有 PostgreSQL 容器，独立应用库 | Linux 环境自己的 PostgreSQL 应用库 |
| 配置来源 | `mac.py prepare` 自动填已知值，再补外部凭据 | 从完整 `.env.example` 独立配置 |
| Windows | 主动连接测试地址 | 主动连接正式域名，使用该服务端的机器人凭据 |

服务端仓库为 `kk-rpa-dashboard`，Windows 仓库为 `kk-rpa-monorepo`。Mac 与 Linux 不共享运行中的数据库、内部服务凭据或 ngrok 地址。

## 完整配置字段

[deploy/.env.example](../deploy/.env.example) 是可提交的完整示例；`deploy/.env` 是被 Git 忽略的实际配置。示例中的占位值需要替换，不能当成已就绪的部署配置。下表覆盖当前 Compose 和 Mac 辅助脚本的全部 15 个字段。

| 字段 | 用途 | Mac 测试 `.env` | Linux `.env` |
| --- | --- | --- | --- |
| `DEEPSEEK_API_KEY` | 官方模型调用 Key | 待填写 | 独立填写 |
| `DEEPSEEK_MODEL` | Agent 模型名 | 已填默认值 | 示例默认值，按可用模型确认 |
| `FEISHU_APP_ID` | 企业自建应用 ID | 待填写 | 填写实际应用 |
| `FEISHU_APP_SECRET` | 应用 Secret | 待填写 | 填写实际应用 |
| `FEISHU_TENANT_KEY` | 允许登录的企业 | 待填写 | 填写实际企业 |
| `ADMIN_OPEN_IDS` | 同一应用内的管理员 ID，逗号分隔 | 待填写 | 填写实际管理员 |
| `PUBLIC_URL` | 浏览器与 Windows 使用的 HTTPS 根地址 | 自动读 ngrok | 正式域名 |
| `WEB_PORT` | Web 的宿主机回环端口 | 默认 `8088` | 默认 `8088`，与 HTTPS 代理一致 |
| `DATABASE_URL` | backend 的 PostgreSQL 连接串 | 已生成独立应用库连接 | 服务器数据库连接串，密码按 URL 编码 |
| `POSTGRES_NETWORK` | backend 加入的现有 Docker 网络 | 自动探测 | 填写服务器实际已有网络 |
| `POSTGRES_CONTAINER` | Mac 脚本探测/建库目标 | 自动填入 | Compose 不使用；可保留示例 |
| `POSTGRES_ADMIN` | Mac 脚本建库所用管理员 | 自动探测 | Compose 不使用；可保留示例 |
| `AGENT_INTERNAL_TOKEN` | backend 与 Agent 的内部认证 | 自动生成并保留 | 单独生成随机值 |
| `CREDENTIAL_ENCRYPTION_KEY` | backend 加密业务凭据的独立密钥 | 自动生成并保留 | 独立生成并备份，保持稳定 |
| `RETENTION_DAYS` | 已结束 Run 保存天数 | 默认 `30` | 按实际要求填写 |

`BACKEND_URL=http://backend:8000`、`EVIDENCE_DIR=/data/evidence`、`PI_SESSION_DIR=/data/sessions` 是 Compose 固定的容器内地址与路径，已在示例注释中列明，不是另外三项待填参数。Windows 只配置控制台地址和机器人连接凭据。业务账号、密码和预期登录身份在控制台发起运行时填写，加密存入独立凭据表，不写入 `.env`、运行快照或日志。

## Mac 测试服务端与 Windows 执行端

Mac 仅承担测试服务端，运行 Web、后端和 Agent 三个容器。数据库使用已经运行的 PostgreSQL 容器；后端加入其现有 Docker 网络，以容器名连接。ngrok 将公网 HTTPS/WSS 转发到 Mac 的 `127.0.0.1:8088`，不用 hosts、自签证书或 Windows CA 配置。外部仍经过飞书登录和机器人凭据认证。

### Mac 首次准备

前置条件：Docker Desktop、Python 3、ngrok 已安装；ngrok 已登录；现有 PostgreSQL 容器运行并有本地管理员访问能力。默认容器名为 `postgresql`。

在 dashboard 仓库根目录，终端一运行并保持：

```sh
ngrok http 8088 --inspect=false
```

终端二运行：

```sh
python3 deploy/mac.py prepare
```

脚本从 ngrok 本机接口读取当前 HTTPS 地址，检测 PostgreSQL 用户和 Docker 网络，生成权限为 `0600` 的忽略文件 `deploy/.env`。`prepare` 只准备配置，不创建数据库、不启动应用。重复执行会更新地址和网络，保留已有数据库口令、内部凭据和填写内容。

当前开发 Mac 的 `deploy/.env` 已填入可确定的地址、数据库连接、网络、内部凭据与默认值；实际内容以本机私有文件为准。首次生成时尚未准备的飞书、DeepSeek 字段留空；后续执行保留已填写值。不要复制 `.env.example` 覆盖这个文件。

这台 Mac 只需补齐 `deploy/.env` 最上方五项；这不代表部署配置只有五项：

| 字段 | 内容 |
| --- | --- |
| `DEEPSEEK_API_KEY` | DeepSeek 官方 Key |
| `FEISHU_APP_ID` | 飞书企业自建应用 App ID |
| `FEISHU_APP_SECRET` | 同一应用的 App Secret |
| `FEISHU_TENANT_KEY` | 允许登录的企业 tenant_key |
| `ADMIN_OPEN_IDS` | 本应用内的管理员 open_id；多个用英文逗号分隔 |

在飞书开发者后台进入当前应用 → **开发配置 → 安全设置 → 重定向 URL**，添加脚本打印的完整地址 `${PUBLIC_URL}/api/auth/feishu/callback`。这是网页登录 OAuth 重定向地址；当前项目没有使用飞书事件订阅，不要把它填到“事件与回调”的“请求地址”中。后者会发送 POST 请求并要求返回 `challenge`，与本项目接收 `code`、`state` 的 GET 登录回调不同。参见 [网页登录配置](https://open.feishu.cn/document/sso/web-application-end-user-consent/guide) 与 [事件 challenge 校验](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/server-side-sdk/nodejs-sdk/handling-events)。

发布应用并将测试成员加入可用范围。`tenant_key` 与 `open_id` 可从同一飞书应用的“获取登录用户信息”接口取得。服务启动后从控制台的飞书登录入口登录，不直接打开缺少 `code`、`state` 的回调地址。

填写后启动：

```sh
python3 deploy/mac.py up
```

启动脚本先检查五项配置，再在现有 PostgreSQL 中创建独立的 `rpa_console` 角色和数据库，最后构建并启动三个服务。不会新建 PostgreSQL 容器、重置已有角色密码、改动现有业务数据库或修改其端口。如果同名数据库已有其他属主，脚本停止并说明原因。

首次启动后，浏览器打开 ngrok 地址，通过飞书登录，在“机器人”页面创建机器人并保存一次性显示的连接凭据。ngrok 免费域名若显示访问提示页，先按页面提示进入。

自定义现有容器名：`python3 deploy/mac.py prepare --postgres-container <container>`；后续 `up` 也使用同一参数。若 ngrok 本机接口不在默认 4040 端口，可用 `--url https://实际域名` 显式传入地址。

### Windows 首次准备

安装 Google Chrome 和 uv，把本次更新后的完整 `kk-rpa-monorepo` 放到任意目录。保留 `apps` 与 `packages` 的相对结构，不复制 Mac 的 `.venv`。

未安装 uv 时：

```powershell
winget install --id astral-sh.uv -e
```

重新打开 PowerShell，在 monorepo 根目录运行：

```powershell
.\packages\rpa-executor\start.ps1
```

若 PowerShell 提示禁止运行脚本，用下面的命令启动；执行策略仅作用于这次进程：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\packages\rpa-executor\start.ps1
```

脚本自动为执行端和两个应用同步 Python 3.12 独立环境，首次只询问：控制台 HTTPS 地址、机器人连接凭据。Windows 不询问业务账号密码。

应用路径、版本、模块名和 WSS 地址由现有模板提供，不用手填 TOML。相对路径以配置文件所在目录为基准，不受 PowerShell 当前目录影响。执行端按控制台 Run ID 隔离浏览器 Profile，无需填写账号别名或在 Windows 预先登记账号。

连接配置写入忽略的 `packages/rpa-executor/config.local.toml`；只有机器人连接凭据通过 Windows DPAPI 加密写入同目录 `credentials.local.clixml`。启动脚本会移除旧版该文件中的业务账号字段，保留机器人连接凭据。业务凭据通过 WSS 随运行下发，在执行进程内注入应用，不写入本地配置或 SQLite 请求日志。

以后启动仍只运行同一条命令。更新地址或重新录入机器人连接凭据：

```powershell
.\packages\rpa-executor\start.ps1 -ServerUrl https://新的测试域名
.\packages\rpa-executor\start.ps1 -Configure
```

首次在有桌面的 Windows 登录用户会话内联调。执行端上线后，控制台应显示“在线”、两个已部署应用版本和空闲状态。真实业务与 Windows DPAPI 的现场验收仍需在该 Windows 电脑完成。

### 在控制台填写本次运行的业务账号

Windows 在线后，在控制台的真实运行列表选择“发起应用运行”，填写运行名称、机器人、已部署应用版本，再填写业务登录账号、密码、登录后预期可见身份，以及业务输入与下载目录。预期身份用于原应用的登录校验。

这三项凭据只通过专用字段提交，不放进业务参数 JSON。backend 使用独立 `CREDENTIAL_ENCRYPTION_KEY` 加密保存；派发时只向认证通过且承担此 Run 的机器人提供明文。Agent 仍只拿到凭据字段引用，使用 `credential` 工具让执行端代填，不接触密码。

运行详情不回显凭据；失败接管和“从头重跑”沿用本次提交值。若要换账号密码，重新发起运行并填写新值。旧版本未保存凭据的运行不能直接重跑，需要重新发起。凭据记录与 Run 一起按保留期清理。

### 已部署版本的更新

升级前先结束活跃 Run。Mac 执行 `python3 deploy/mac.py prepare` 自动补齐新的加密密钥，保留其余已填配置，再执行 `python3 deploy/mac.py up` 更新镜像和数据库表。Windows 同步本轮执行端代码后重启 `start.ps1`。服务端与 Windows 需同时更新，旧执行端仍会查找本地账号配置。

Linux 在独立 `.env` 中增加 `CREDENTIAL_ENCRYPTION_KEY`，然后按下文 Compose 启动命令更新。backend 启动时执行 `0002` 迁移创建加密凭据表。该密钥要与数据库备份一起妥善保存；不要在已有凭据记录后重新随机生成，否则旧运行无法解密。

### 日常操作与验证

```sh
python3 deploy/mac.py status
python3 deploy/mac.py down
python3 deploy/mac.py up
```

以上命令在 dashboard 根目录执行。`down` 只关闭本项目三个服务，保留证据/会话卷，不关闭共享 PostgreSQL、不删除其数据库；ngrok 在终端一用 Ctrl+C 停止。ngrok 地址变化时重新执行 `prepare`，同步飞书回调和 Windows 地址，再执行 `up`。`up` 会应用 `.env` 变更。

健康检查：`curl -H 'ngrok-skip-browser-warning: 1' https://实际域名/api/health`，应返回 `{"status":"ok","mode":"live"}`。查看日志：

```sh
docker compose --env-file deploy/.env -f deploy/compose.yaml logs --tail=100 backend agent web
```

部署脚本离线测试：`python3 -m unittest discover -s deploy/tests -v`。Windows 执行桥离线测试：在 monorepo 运行 `uv run --project packages/rpa-executor pytest packages/rpa-executor/tests`。

后端保持一个 Uvicorn worker，Agent 保持一个实例。截图和 pi 会话仍使用持久卷；Run、Attempt、预算与事件存在共享 PostgreSQL 的独立应用库中。`RETENTION_DAYS` 默认 30，仅清理达到期限的已结束运行。业务下载保留在 Windows 原目录。应用导入和定时调度仍未接入此次运行入口。

接口依据：[ngrok WebSocket](https://ngrok.com/docs/using-ngrok-with/websockets/)、[Docker 共享网络](https://docs.docker.com/compose/how-tos/networking/)、[uv 安装](https://docs.astral.sh/uv/getting-started/installation/)、[Windows 加密凭据](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/export-clixml)、[PowerShell 执行策略](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies)。

## Linux 实际服务端

本节说明当前部署文件在 Linux 上的使用方式；尚未在目标 Linux 服务器部署或验收。Linux 不运行 `mac.py`，也不需要 ngrok。Compose 只启动三个应用服务，不负责在 Linux 上创建数据库角色或数据库。

### 1. 准备服务器与数据库

服务器需有 Docker Engine、Compose 插件，以及能从 backend 容器访问的 PostgreSQL 应用库。下面以已有 PostgreSQL 容器、已有自定义网络为例：确认 PostgreSQL 容器已加入该网络，把网络名写入 `POSTGRES_NETWORK`，把容器在该网络的名称或别名写入 `DATABASE_URL`。该 external 网络必须事先存在；不能把 Mac 的网络名直接当作 Linux 的实际网络名。

由数据库管理员创建独立应用角色与数据库。新建示例在 `psql` 管理员会话内执行；若同名角色/库已存在，使用现有应用配置核对，不重复创建或重置密码：

```sql
CREATE ROLE rpa_console LOGIN;
\password rpa_console
CREATE DATABASE rpa_console OWNER rpa_console;
```

`\password` 交互输入的密码须与 Linux `.env` 的连接串一致，角色配置参见 [PostgreSQL 官方说明](https://www.postgresql.org/docs/17/sql-createrole.html)。数据库主机不能写 `127.0.0.1` 来表示宿主机数据库，因为 backend 运行在容器内。若实际使用外部数据库服务，使用容器可访问的实际地址；当前 Compose 仍要求 `POSTGRES_NETWORK` 指向一个已有网络。

### 2. 独立填写 Linux 配置

在 Linux 的 dashboard 仓库根目录，首次配置时执行：

```sh
cp -n deploy/.env.example deploy/.env
chmod 600 deploy/.env
```

填写上表全部适用字段，替换所有 `replace-with-*`。`PUBLIC_URL` 设为正式 HTTPS 域名，例如 `https://console.example.com`。数据库口令使用 URL 编码；`AGENT_INTERNAL_TOKEN` 使用独立随机值。`CREDENTIAL_ENCRYPTION_KEY` 为 URL-safe Base64 编码的 32 字节随机密钥，仅提供给 backend；有 Python 3 的机器可用 `python3 -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"` 生成，写入 Linux 私有 `.env` 并备份。示例中的 `POSTGRES_CONTAINER` 与 `POSTGRES_ADMIN` 不会触发任何建库操作。

### 3. 配置正式 HTTPS 入口

正式域名解析到 Linux 服务器，由宿主机上的 HTTPS 反向代理转发到 `127.0.0.1:8088`。例如宿主机已安装 Caddy 时，将以下站点块加入其配置，域名替换为实际值；若 `WEB_PORT` 改动，代理端口同步修改：

```caddyfile
console.example.com {
    reverse_proxy 127.0.0.1:8088 {
        flush_interval -1
    }
}
```

这是 Linux 宿主机入口的配置，不是替换仓库中的 `deploy/Caddyfile`；仓库内的 Caddy 仍负责容器内 HTTP、前端静态文件和 API 路由。宿主机 Caddy 的自动 HTTPS 需要正确的公网 DNS 和可访问的 80/443 端口；WebSocket 由反向代理支持，SSE 使用及时刷新。若已有其他 HTTPS 入口，应提供相同的转发能力。此处的 `127.0.0.1` 示例只适用于代理运行在宿主机的情况。

在飞书应用的 **开发配置 → 安全设置 → 重定向 URL** 登记 `https://正式域名/api/auth/feishu/callback`，并确认应用发布范围包含实际使用成员。此地址用于网页登录，不填入事件订阅请求地址。

### 4. 启动与验收

在 Linux 的 dashboard 根目录执行：

```sh
docker compose --env-file deploy/.env -f deploy/compose.yaml config --quiet
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d --build
docker compose --env-file deploy/.env -f deploy/compose.yaml ps
curl https://正式域名/api/health
```

后端启动时自动执行 Alembic 表结构迁移，前提是应用库、角色及连接权限已经准备好。健康检查应返回 `{"status":"ok","mode":"live"}`。随后完成飞书登录、创建机器人，并在 Windows 使用正式地址和这个服务端签发的机器人凭据。可用 `start.ps1 -Configure` 重新录入；不要把测试服务端的机器人凭据当成 Linux 服务端凭据。

Linux 的日常停止、启动和日志查看直接使用上述 Compose 命令；停止使用 `down`，启动使用 `up -d`，日志使用 `logs --tail=100 backend agent web`。持久卷和 PostgreSQL 应用库需要按实际服务器要求备份。服务实例数仍按当前实现保持 backend 一个 worker、Agent 一个实例。

参考：[Docker external 网络](https://docs.docker.com/compose/how-tos/networking/)、[回环端口发布](https://docs.docker.com/engine/network/port-publishing/)、[Caddy HTTPS 前提](https://caddyserver.com/docs/quick-starts/https)、[Caddy 反向代理](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)。

## 测试顺序与通过标准

先完成离线检查，再在已配置环境执行真实联调。以下真实用例需要实际飞书、DeepSeek 与 Windows 业务账号，当前尚未执行。

| 顺序 | 检查 | 通过标准 |
| --- | --- | --- |
| 1 | 服务健康 | 三个服务运行，`/api/health` 返回 live/ok |
| 2 | 飞书登录 | 配置企业可登录；管理员可创建机器人 |
| 3 | Windows 连接 | 机器人在线、空闲，并上报两个应用版本 |
| 4 | 正常 Run | 填写登录账号、密码及预期身份，按应用要求填输入；步骤、下载及结束状态正确；截图及时可见，日志按时间降序 |
| 5 | 聚水潭失败接管 | 按原规格制造品牌干扰/定位器失效；截图进入模型，恢复结果经过原 verify |
| 6 | 京麦恢复下载 | 按原规格使用已生成报表，只恢复下载，保留原参数与实际下载文件信息 |
| 7 | 停止、断连与重启 | 停止后无新增动作；状态不能确认时保持待确认；终态确认后才释放机器人 |

每次保存 Run、Attempt、截图、预算、下载路径与最终结果。两个失败案例的完整条件见 [原规格](../workflows/dashboard-rpa-recovery.md)，现有离线测试结果与尚未验收项见 [实施记录](recovery-implementation.md#验证记录)。Mac 联调通过后，Linux 仍需执行入口、数据库持久化、登录和 Windows 连接验收，不能将 Mac 结果标成 Linux 已验收。

## 常见问题

| 现象 | 检查与处理 |
| --- | --- |
| ngrok 地址打不开或返回网关错误 | 确认隧道仍运行、目标端口与 `WEB_PORT` 一致、三个应用服务已启动；配置留空时应用尚未启动是预期状态 |
| `up` 要求补齐五项 | 只编辑私有 `.env`；不要把示例占位值作为真实值 |
| external 网络不存在或数据库名称无法解析 | 核对当前机器的 `POSTGRES_NETWORK`，以及数据库容器是否加入此网络 |
| 业务凭据无法解密 | 恢复原有 `CREDENTIAL_ENCRYPTION_KEY`；不要重置为新随机值 |
| 数据库认证失败 | 核对现有应用角色密码与连接串的 URL 编码；Mac 脚本不会重置已有密码 |
| 飞书回调失败 | 核对 `PUBLIC_URL`、回调完整路径、应用 ID、发布范围；改 `.env` 后重新 `up` |
| 飞书后台提示 Challenge code 没有返回 | 登录回调被填到了事件/回调请求地址；应在“开发配置 → 安全设置 → 重定向 URL”配置，本项目不需要事件订阅 challenge 接口 |
| 机器人连接失败 | 核对 HTTPS 地址及当前服务端签发的机器人凭据；Linux 切换使用 `-Configure` |
| 管理请求来源不匹配 | 用与 `PUBLIC_URL` 完全一致的地址打开控制台 |
| PowerShell 禁止执行脚本 | 使用上文仅作用于当前进程的启动命令 |
