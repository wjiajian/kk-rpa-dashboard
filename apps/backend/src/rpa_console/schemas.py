"""Validate robot declarations and actual inputs before queueing new work."""
from jsonschema import Draft7Validator, FormatChecker, SchemaError


def input_schema(deployment):
    schema = deployment.get("input_schema")
    if schema is None:
        form = deployment.get("form_schema") or {}
        properties = form.get("properties", {}) if isinstance(form, dict) else {}
        schema = properties.get("inputs") if isinstance(properties, dict) else None
    return schema


def schema_validator(schema):
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("参数声明根节点必须为 object")
    def check_refs(value):
        if isinstance(value, dict):
            if "$ref" in value:
                raise ValueError("参数声明不支持 $ref，请内联字段定义")
            for item in value.values():
                check_refs(item)
        elif isinstance(value, list):
            for item in value:
                check_refs(item)
    check_refs(schema)
    try:
        Draft7Validator.check_schema(schema)
    except SchemaError as error:
        location = ".".join(map(str, error.absolute_path)) or "根节点"
        raise ValueError(f"参数声明 {location} 无效（{error.validator}）") from error
    return Draft7Validator(schema, format_checker=FormatChecker(formats=["date"]))


def normalize_deployment(deployment):
    result = dict(deployment)
    if result.get("schema_status") == "invalid":
        result.pop("input_schema", None)
        result.pop("form_schema", None)
        return result
    schema = input_schema(result)
    if schema is None and result.get("schema_status") != "valid" and "input_schema" not in result and "form_schema" not in result:
        return {**result, "schema_status": "missing"}
    try:
        schema_validator(schema)
    except ValueError as error:
        result.pop("input_schema", None)
        result.pop("form_schema", None)
        return {**result, "schema_status": "invalid", "schema_error": str(error)}
    return {**result, "input_schema": schema, "schema_status": "valid"}


def validate_inputs(deployment, values):
    reject_sensitive_inputs(values)
    if deployment.get("schema_status") == "invalid":
        raise ValueError("应用参数声明损坏，请更新执行端部署后再运行")
    schema = input_schema(deployment)
    if schema is None:
        if deployment.get("schema_status") == "valid":
            raise ValueError("应用参数声明缺失")
        return
    error = next(schema_validator(schema).iter_errors(values), None)
    if error:
        location = ".".join(map(str, error.absolute_path)) or "inputs"
        # Do not echo submitted values into diagnostics.
        raise ValueError(f"业务参数 {location} 不符合声明（{error.validator}）")


def reject_sensitive_inputs(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if any(part in key.lower() for part in ("password", "secret", "token", "credential")):
                raise ValueError("账号密码请填写专用凭据字段，不能进入业务参数")
            reject_sensitive_inputs(item)
    elif isinstance(value, list):
        for item in value:
            reject_sensitive_inputs(item)


def require_installed_release(session, robot_id, release_id):
    from sqlalchemy import select
    from .storage import RobotDeployment, DeploymentJob
    installed = session.get(RobotDeployment, (robot_id, release_id))
    if not installed or installed.status != "installed":
        raise ValueError("请先在该机器人安装原发布版本")
    jobs = session.scalars(select(DeploymentJob).where(DeploymentJob.robot_id == robot_id,
        DeploymentJob.release_id == release_id, DeploymentJob.status.in_(["queued", "installing", "uncertain"])))
    if any(job.data["action"] == "uninstall" for job in jobs):
        raise ValueError("该版本正在卸载，不能新增引用")
