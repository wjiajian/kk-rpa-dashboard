# 升级维护操作

维护模式由运维命令控制，状态保存在 PostgreSQL，不随后端重启丢失。需要迁移 `0005` 及配套服务代码。首次从不具备维护能力的旧服务升级，应先停止新增业务请求并人工确认活跃运行结束，再停服务、备份和迁移；旧镜像不能执行下面的新命令。

以下命令在 Dashboard 仓库根目录、已配置 `deploy/.env` 的服务器执行。

```sh
docker compose --env-file deploy/.env -f deploy/compose.yaml exec backend uv run --no-sync python -m rpa_console.maintenance enter
docker compose --env-file deploy/.env -f deploy/compose.yaml exec backend uv run --no-sync python -m rpa_console.maintenance status
```

进入维护后，新临时运行、计划立即运行和历史重跑返回“控制台维护中”；定时不生成 Run，已有运行队列保留且暂不派发。新安装与导入作业保持排队。活跃运行的接管、停止和收尾仍继续，已分配安装可重连核对结果。

状态输出包括：

| 字段 | 含义 |
| --- | --- |
| maintenance | 是否处于维护模式 |
| drained | 维护已开启，且无机器人占用的 Run、部署作业及获取中的导入 |
| active_runs | 尚需结束确认的运行 ID |
| active_deployments | 尚需安装收尾确认的作业 ID |
| active_imports | 正在获取源码的导入作业 ID |

`drained=false` 时等待具体作业完成，或按正常停止、安装收尾流程处理。状态不确定的机器人仍算占用。获取中的导入若因发布进程崩溃中断，可退出维护让该作业恢复后重新进入维护；不得直接把数据库状态改成完成。

`drained=true` 表示活跃作业已经排空，尚不表示数据库和持久目录停止写入。取得一致备份前还需停止服务，阻止配置编辑、清理和会话写入：

```sh
docker compose --env-file deploy/.env -f deploy/compose.yaml stop web backend agent publisher
```

随后备份数据库、凭据加密密钥、证据、Agent 会话、发布制品及服务配置，按目标版本迁移和更新服务。数据库与目录必须来自同一停止写入窗口；备份恢复演练仍按完整平台方案验收。维护状态会保留到恢复后的数据库中。

重新启动服务并确认版本、迁移、权限和机器人连接正常后退出维护：

```sh
docker compose --env-file deploy/.env -f deploy/compose.yaml exec backend uv run --no-sync python -m rpa_console.maintenance exit
```

退出维护的事务会把启用计划的下一时间推进到当前时间之后，不补跑维护期间的计划；已有 Run 队列和待安装作业继续推进。重复执行 exit 不重置正常运行中的计划时间。
