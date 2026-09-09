# 备份与恢复

`deploy/backup.py` 使用 Docker 中的 PostgreSQL 客户端和归档工具，针对当前四服务 Compose 执行离线备份。默认客户端镜像为 `postgres:17`；数据库版本变化时，用 `--postgres-image` 指定匹配镜像。备份采用 [pg_dump 自定义格式](https://www.postgresql.org/docs/17/app-pgdump.html)，恢复使用 [pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html)。

## 创建备份

先按 [维护操作](maintenance.md) 进入维护，等待活跃作业排空，再停止 web、backend、agent、publisher。保留容器和数据卷，不执行删除卷的命令。数据库本身继续运行。

在仓库根目录执行，目标目录必须尚不存在：

```sh
python3 deploy/backup.py create /srv/rpa-backups/2026-09-08
```

工具核对四服务均已停止、持久卷没有运行中的容器使用、数据库维护已开启且无活跃 Run、部署或导入，然后生成：

| 文件 | 内容 |
| --- | --- |
| database.dump | 应用数据库，包括历史运行、计划、凭据密文、发布记录和维护状态 |
| evidence.tar | 控制台截图证据 |
| sessions.tar | Agent 会话 |
| artifacts.tar | 固定 commit 的发布源码制品 |
| git_config.tar | Git 服务配置，包括 SSH known_hosts 等持久文件 |
| deployment.env、compose.json | 原部署文件和展开后的有效 Compose 配置，包含凭据加密密钥及其他服务凭据 |
| complete.json | 全部步骤完成标记、时间、迁移版本与客户端镜像 |

目录权限设为 700，文件为 600；不要提交或公开分享其中的配置。中途失败保留未完成目录供检查，缺少 complete.json 的备份不能恢复。每次使用新目录，不覆盖旧备份。

宿主机 HTTPS 代理配置、证书及对应代码版本需随运维备份另行保存；它们不在 Compose 数据卷内。执行机业务下载和 Windows journal 也不由该工具复制。备份应转存到独立受保护介质，保留原密钥，不能只保留数据库转储。

## 恢复到隔离环境或空的新环境

准备空的应用数据库、独立 Compose 项目及数据卷。目标服务使用与备份匹配的代码和镜像；先恢复，再按升级方案迁移。不要让恢复环境连接原业务机器人。

复制备份中的部署配置到受保护的恢复配置文件，调整数据库地址、数据库账号、Docker 网络和对外地址。`CREDENTIAL_ENCRYPTION_KEY` 必须保留原值；以 compose.json 中的有效值为准，因为原部署可能使用过环境变量覆盖 `.env`。原机器人连接凭据、飞书与 Agent 服务配置同样需按恢复目标核对。

创建容器和空数据卷，但不启动应用服务。下面示例使用独立项目名：

```sh
docker compose --env-file deploy/recovery.env -f deploy/compose.yaml --project-name rpa-recovery create
python3 deploy/backup.py restore /srv/rpa-backups/2026-09-08 --env-file deploy/recovery.env --project rpa-recovery
```

恢复拒绝错误密钥、非空数据库、非空数据卷及仍运行的服务，不删除或覆盖目标数据。若中途失败，保持服务停止，检查原因后换一个空恢复环境重试，不在部分恢复的目标上强行重放。

完成后数据库仍处于维护模式。启服务前核对恢复配置与网络隔离；启动后检查登录权限、历史 Run 和截图、凭据解密、计划下一触发时间、发布目录与制品。使用测试机器人验证原版本重新安装和重跑，确认结束与收尾后再按维护操作退出。数据库与执行机 journal 不一致时保留占用并核对，不自动重放未知业务动作。

## 本地隔离恢复记录

2026-09-08，使用临时 PostgreSQL 17、两个独立 Compose 项目和独立数据卷完成工具演练。恢复后核对原运行凭据可解密、已入队 Run 不变、维护状态保留，以及 evidence、sessions、artifacts、git_config 四卷文件内容一致；验证错误密钥、非空目标及运行中服务会阻止操作。

```sh
RPA_BACKUP_DOCKER_TEST=1 uv run --project apps/backend pytest deploy/tests/test_backup.py -q
```

该测试自行创建并清理隔离资源，默认不执行。它验证备份工具的数据恢复行为，不代表正式 Linux 的登录、真实截图展示、Windows 制品安装及业务重跑已验收；这些仍按完整平台方案完成。
