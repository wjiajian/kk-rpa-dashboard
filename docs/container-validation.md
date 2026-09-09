# 当前镜像的隔离容器验证

2026-09-08，使用当前未提交工作区构建独立验证镜像，并在 Docker 的 Linux 容器中完成四服务启动测试。项目、数据库、网络和数据卷均临时创建，测试完成后删除；未更新现有服务镜像标签或部署。

## 构建与重复执行

先从待验证的工作区构建以下标签。测试不自动构建镜像，代码变化后应重新构建，避免用旧镜像替代新版本验收。

```sh
docker build -f deploy/Dockerfile.backend -t rpa-platform-verification-backend:local .
docker build -f deploy/Dockerfile.node --target web -t rpa-platform-verification-web:local .
docker build -f deploy/Dockerfile.node --target agent -t rpa-platform-verification-agent:local .
RPA_COMPOSE_DOCKER_TEST=1 uv run --project apps/backend pytest deploy/tests/test_compose.py -q
```

脚本读取仓库 Compose，替换为独立镜像标签及本次临时环境，保留四服务的命令、用户、网络与持久卷结构。publisher 复用 backend 镜像。飞书和模型使用不会用于真实请求的测试配置，不创建恢复作业、不调用模型。

## 验证结果

| 项目 | 结果 |
| --- | --- |
| backend、web、agent 镜像构建 | 通过 |
| 四服务启动，新数据库迁移至 0005 | 通过 |
| Web 代理访问实际后端 health；当前任务页面静态资源可达 | 通过 |
| Agent health 与后端内部轮询 | 通过 |
| publisher 常驻进程读取持久作业，处理不可访问的回环 Git 来源并保存失败 | 通过 |
| 创建离线队列后进入维护，再重启 backend | 队列和维护状态保留 |

测试通过不代表正式 Linux 主机已部署。公网 HTTPS/WSS、真实飞书登录、远端私有 Git 凭据、Windows 安装与业务运行仍需目标环境验收。备份恢复的独立验证见 [恢复说明](backup-recovery.md)。
