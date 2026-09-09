# 应用参数表单

新建任务中的「参数」根据所选应用的 JSON Schema 显示名称、类型、值和描述。参数修改在弹窗内暂存，确定后写入任务草稿，点击「立即执行」提交到后端。取消弹窗不保留本次修改。新建任务的应用、机器人及参数均为空；切换应用会清空参数及登录配置，不自动填入声明中的默认值。已有任务继续回显保存值。

保留的历史演示源码通过 `Application.inputSchema` 提供业务参数定义。当前三种预置应用的声明仅用于演示，不代表外部程序的真实接口。`Task.parameters` 保存参数，旧任务按对应应用声明读取已有字段。日期字段可在计划中使用固定日期或相对日期。当前统一界面仅填写账号和密码；京麦、聚水潭程序不再要求或匹配预期可见身份。历史演示源码不作为测试入口。

## 实时运行接入

实时运行从 `/api/robots` 返回的对应部署版本读取 `input_schema`，或完整 `form_schema.properties.inputs`。例如机器人连接时声明：

```json
{
  "deployments": [{
    "app_id": "reservation",
    "version": "1.0.0",
    "input_schema": {
      "type": "object",
      "required": ["batch", "date", "booking_method"],
      "additionalProperties": false,
      "properties": {
        "batch": { "type": "integer", "minimum": 1, "description": "批次，例如 1" },
        "date": { "type": "string", "minLength": 1, "description": "日期，例如 7.7" },
        "booking_method": { "type": "string", "title": "预约方式", "enum": ["TC", "速佳"], "default": "TC" }
      }
    }
  }]
}
```

后端连接流程保存并返回部署信息；参数上报本身不需要数据库迁移。执行端位于同级 `kk-rpa-monorepo`，现已从应用 `app.toml` 的 `[console].input_schema` 静态读取声明，并上报 `input_schema`、`schema_status` 及必要的 `schema_error`。两个应用已补齐 `input.schema.json`。这是本地代码进度，现有测试服务与 Windows 仍需更新后生效。

有效声明同时用于前端和后端校验，执行端继续执行原 Python 参数校验。旧部署缺少声明时保留 JSON 临时运行；声明损坏时显示具体错误并禁止新建运行，不静默降级。计划保存要求有效声明。新建表单不应用 Schema 默认值，可选文件名留空不传值，由程序生成并回报实际值。

参数声明不写入运行快照，只保存应用标识、版本、实际输入及下载目录。计划的相对日期由后端在触发时解析；临时运行填写实际日期。计划和运行均持久化，账号密码独立加密。当前本地计划实现需要 `0003` 数据库迁移；详细进度及后续发布实现见 [完整平台实施方案](platform-implementation.md)。
