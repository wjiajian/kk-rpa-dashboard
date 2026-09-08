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

后端现有连接流程保存并返回部署信息，因此不需要数据库迁移。外部执行端需要从该程序的参数声明读取并上报此字段；本仓库不包含该执行端的部署扫描实现。旧版部署未上报声明时保留 JSON 输入兼容，不推测程序字段。实时运行提交实际值，不解析相对日期。

参数声明用于表单渲染和前端校验，执行端仍负责验证实际输入。参数表单不会上传到运行快照中；快照仅提交应用标识、版本、输入值及下载目录。当前后端尚无计划管理和自动调度接口；统一界面提供真实的手动执行，不再挂载内存演示页面。运行由后端保存，刷新不会丢失。
