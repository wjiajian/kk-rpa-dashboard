#!/usr/bin/env python3
"""Prepare a private config, then start the console against an existing PostgreSQL."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / "deploy" / ".env"
MANUAL = ("DEEPSEEK_API_KEY", "FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_TENANT_KEY", "ADMIN_OPEN_IDS")
DATABASE = "rpa_console"


def read_env(path):
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise ValueError(".env 包含无效字段，请使用 KEY=value 格式")
        if value.startswith("'") and value.endswith("'"):
            value = value[1:-1].replace("\\'", "'")
        elif value.startswith('"') and value.endswith('"'):
            value = json.loads(value)
        values[key] = value
    return values


def write_env(path, values):
    lines = ["# 只需填写下面五项；不要提交此文件。"]
    for index, keys in enumerate((MANUAL, sorted(set(values) - set(MANUAL)))):
        if index:
            lines.extend(["", "# 自动生成；重复 prepare 会保留已有凭据。"])
        for key in keys:
            value = values.get(key, "")
            if any(c in value for c in "\r\n\0"):
                raise ValueError(".env 字段不能包含换行或空字符")
            # Compose single quotes preserve literal $ and # in credentials.
            lines.append(key + "='" + value.replace("'", "\\'") + "'")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(path, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")


def postgres_info(container):
    result = subprocess.run(["docker", "inspect", container], check=True, capture_output=True, text=True)
    info = json.loads(result.stdout)[0]
    if not info["State"]["Running"]:
        raise ValueError("指定的 PostgreSQL 容器没有运行")
    networks = [name for name in info["NetworkSettings"]["Networks"] if name not in {"bridge", "host", "none"}]
    if not networks:
        raise ValueError("PostgreSQL 需要连接一个 Docker 自定义网络")
    env = dict(item.split("=", 1) for item in info["Config"]["Env"] if "=" in item)
    return env.get("POSTGRES_USER", "postgres"), networks[0]


def public_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("测试地址必须是 https://域名，可带端口，不能带路径")
    return value.rstrip("/")


def tunnel_url(endpoints, port):
    matches = []
    for endpoint in endpoints:
        address = str(endpoint.get("upstream", {}).get("url", ""))
        upstream = urlsplit(address if "://" in address else "http://" + address)
        if upstream.hostname in {"127.0.0.1", "localhost", "::1"} and upstream.port == port:
            url = endpoint.get("url", "")
            if url.startswith("https://"):
                matches.append(public_url(url))
    if len(matches) != 1:
        raise ValueError(f"需要一个指向本机 {port} 端口的 HTTPS ngrok 隧道")
    return matches[0]


def prepare(path=ENV_FILE, container="postgresql", url=None):
    values = read_env(path)
    admin, network = postgres_info(container)
    values.update(POSTGRES_CONTAINER=container, POSTGRES_ADMIN=admin, POSTGRES_NETWORK=network)
    values.setdefault("WEB_PORT", "8088")
    values.setdefault("AGENT_INTERNAL_TOKEN", secrets.token_hex(32))
    values.setdefault("CREDENTIAL_ENCRYPTION_KEY", base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
    values.setdefault("DATABASE_URL", f"postgresql+psycopg://{DATABASE}:{secrets.token_hex(32)}@{container}:5432/{DATABASE}")
    values.setdefault("DEEPSEEK_MODEL", "deepseek-v4-flash-vision-exp")
    values.setdefault("RETENTION_DAYS", "30")
    if "ADMIN_OPEN_IDS" in values:
        values["ADMIN_OPEN_IDS"] = ",".join(item.strip() for item in values["ADMIN_OPEN_IDS"].split(",") if item.strip())
    if url:
        values["PUBLIC_URL"] = public_url(url)
    else:
        try:
            with urlopen("http://127.0.0.1:4040/api/endpoints", timeout=3) as response:
                values["PUBLIC_URL"] = tunnel_url(json.load(response)["endpoints"], int(values["WEB_PORT"]))
        except OSError as error:
            write_env(path, values)
            raise ValueError(f"先在另一个终端运行：ngrok http {values['WEB_PORT']} --inspect=false") from error
    write_env(path, values)
    print(f"私有配置：{path}")
    print(f"测试地址：{values['PUBLIC_URL']}")
    print(f"飞书 OAuth 重定向 URL（开发配置 → 安全设置）：{values['PUBLIC_URL']}/api/auth/feishu/callback")
    return values


def validate(values):
    missing = [key for key in MANUAL if not values.get(key, "").strip() or values[key].startswith("replace-with-")]
    if missing:
        raise ValueError("请先填写 deploy/.env：" + ", ".join(missing))
    public_url(values["PUBLIC_URL"])


def psql(values, sql, app_user=False):
    user = DATABASE if app_user else values["POSTGRES_ADMIN"]
    command = ["docker", "exec", "-i"]
    environment = None
    if app_user:
        environment = {**os.environ, "PGPASSWORD": unquote(urlsplit(values["DATABASE_URL"]).password or "")}
        command.extend(["-e", "PGPASSWORD"])
    command.extend([values["POSTGRES_CONTAINER"], "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1", "-U", user,
                    "-d", DATABASE if app_user else "postgres"])
    if app_user:
        # Match the backend's TCP destination; loopback may use passwordless trust.
        command.extend(["-h", values["POSTGRES_CONTAINER"]])
    result = subprocess.run(command, input=sql, text=True, capture_output=True, env=environment)
    if result.returncode:
        raise ValueError("PostgreSQL 操作失败；请检查管理员连接或本应用数据库凭据，脚本不会重置已有角色密码")
    return result.stdout.strip()


def ensure_database(values):
    connection = urlsplit(values["DATABASE_URL"])
    if (connection.scheme != "postgresql+psycopg" or connection.hostname != values["POSTGRES_CONTAINER"]
            or connection.username != DATABASE or connection.path != "/" + DATABASE or not connection.password):
        raise ValueError("自动初始化仅管理当前 PostgreSQL 容器中的 rpa_console 数据库和同名角色")
    owner = psql(values, f"SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='{DATABASE}';")
    if owner and owner != DATABASE:
        raise ValueError("已有 rpa_console 数据库属于其他角色，未做修改")
    password = unquote(connection.password).replace("'", "''")
    psql(values, rf"""
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', '{DATABASE}', '{password}')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{DATABASE}')
\gexec
SELECT format('CREATE DATABASE %I OWNER %I', '{DATABASE}', '{DATABASE}')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname='{DATABASE}')
\gexec
""")
    psql(values, "SELECT 1;", app_user=True)
    print("应用数据库已就绪；复用现有 PostgreSQL 容器。")


def compose(*args):
    subprocess.run(["docker", "compose", "--env-file", str(ENV_FILE), "-f", str(ROOT / "deploy" / "compose.yaml"), *args],
                   cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "up", "status", "down"))
    parser.add_argument("--postgres-container", default="postgresql")
    parser.add_argument("--url", help="使用已知 HTTPS 地址，省略时从本机 ngrok 读取")
    args = parser.parse_args()
    if args.action in {"status", "down"}:
        compose("ps" if args.action == "status" else "down")
        return
    values = prepare(container=args.postgres_container, url=args.url)
    if args.action == "prepare":
        try:
            validate(values)
        except ValueError as error:
            print(str(error))
            print("补齐配置后运行：python3 deploy/mac.py up")
        else:
            print("配置已填写完整（尚未验证外部凭据有效性）。")
            print("启动服务：python3 deploy/mac.py up")
        return
    validate(values)
    compose("config", "--quiet")
    ensure_database(values)
    compose("up", "-d", "--build")
    print("服务已启动；通过测试地址完成飞书登录并创建机器人。")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
