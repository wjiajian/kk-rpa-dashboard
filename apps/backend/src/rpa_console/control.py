"""Durable transitions; only executor acknowledgements release robot ownership."""
from copy import deepcopy
from hashlib import sha256
import hmac
import secrets
from time import time

from sqlalchemy import select

from .storage import Event, Operation, Robot, Run, uid

TERMINAL = {"succeeded", "failed", "stopped", "cancelled"}
TOOLS = {"context", "observe", "act", "credential", "resume", "give_up"}
PENDING = {"accepted", "running", "unknown"}
BUDGET = 900.0
MAX_RECOVERY_ROUNDS = 3


class Conflict(ValueError):
    pass


def remaining(data, now):
    return max(0.0, BUDGET - data["recovery_used"] - (
        max(0, now - data["recovery_since"]) if data.get("recovery_since") is not None else 0
    ))


def pause_budget(data, at):
    if data.get("recovery_since") is not None:
        data["recovery_used"] += max(0, at - data["recovery_since"])
        data["recovery_since"] = None


class Control:
    def __init__(self, database, clock=time, credentials=None):
        self.db, self.clock = database, clock
        self.credentials = credentials

    def add_robot(self, name):
        token = secrets.token_urlsafe(32)
        with self.db.transaction() as s:
            robot = Robot(id=uid(), name=name, credential_hash=sha256(token.encode()).hexdigest())
            s.add(robot)
        return {"id": robot.id, "name": name, "credential": token}

    def authenticate_robot(self, token):
        digest = sha256(token.encode()).hexdigest()
        with self.db.transaction() as s:
            robot = s.scalar(select(Robot).where(Robot.credential_hash == digest))
            return robot.id if robot else None

    def event(self, s, run, data, kind, message, *, details=None):
        data["seq"] += 1
        s.add(Event(run_id=run.id, seq=data["seq"], data={
            "kind": kind, "message": message, "at": self.clock(),
            "attempt_id": data.get("attempt_id"), "details": details or {},
        }))

    def agent_activity(self, s, run, data, operation, status):
        body = operation["body"]
        action = body["action"]
        if action not in TOOLS:
            return
        label = {"context": "读取运行上下文", "observe": "观察页面", "credential": "填写登录凭据",
                 "resume": "提交程序续跑", "give_up": "结束接管"}.get(action)
        if action == "act":
            label = {"navigate": "打开业务页面", "click": "点击页面控件", "new_tab": "打开新页签",
                     "input": "填写页面内容", "select": "选择业务条件", "read": "读取页面状态",
                     "wait": "等待页面就绪", "download": "下载报表"}.get(body["params"].get("operation"), "操作业务页面")
        result = operation.get("result") or {}
        if result.get("observation_error"):
            status = "failed"
        state = {"running": "执行中", "succeeded": "已完成", "failed": "失败，等待处理", "unknown": "结果待确认"}[status]
        if action == "resume" and status == "succeeded":
            state = "执行端已返回，结果以原程序校验为准"
        self.event(s, run, data, "agent_activity", f"第 {operation.get('recovery_round', len(data.get('recovery_rounds', [])))} 轮 · {label}：{state}")

    def finish_round(self, s, run, data, summary=None):
        rounds = data.get("recovery_rounds", [])
        if not rounds or rounds[-1].get("summary"):
            return
        current = rounds[-1]
        if summary is None:
            summary = {
                "budget_exhausted": "累计接管时间已达到 900 秒，本轮接管结束。",
                "rounds_exhausted": "已达到 3 轮接管上限，结束接管并等待执行端收尾。",
                "administrator": "管理员已请求停止，本轮接管结束。",
                "agent_unavailable": "Agent 未能完成本轮接管，已请求停止。",
                "requires_administrator": "检测到人工验证，本轮接管结束，请管理员处理后重跑。",
            }.get(data.get("stop_reason"), "本轮接管中断，未提交可继续执行的恢复结果。")
        if self.credentials is not None:
            for secret in sorted(self.credentials.read(s, run.id).values(), key=len, reverse=True):
                summary = summary.replace(secret, "<redacted>")
        current.update(summary=summary, ended=self.clock())
        self.event(s, run, data, "agent_summary", f"Agent 第 {current['number']} 轮接管总结\n{summary}",
                   details={"round": current["number"]})

    def create_run(self, robot_id, snapshot, name, rerun_of=None, credentials=None):
        with self.db.transaction() as s:
            robot = self.db.lock_robot(s, robot_id)
            if not robot.credential_hash:
                raise Conflict("机器人凭据已撤销")
            if not any(d["app_id"] == snapshot["app_id"] and d["version"] == snapshot["version"]
                       for d in robot.deployments):
                raise Conflict("机器人未声明部署此应用版本")
            run = Run(id=uid(), robot_id=robot_id, created=self.clock(), data={
                "name": name, "snapshot": deepcopy(snapshot), "rerun_of": rerun_of,
                "status": "queued", "phase": "queued", "attempt_id": uid(), "attempts": [],
                "recovery_used": 0.0, "recovery_since": None, "seq": 0,
                "recovery_rounds": [],
                "stop_reason": None, "lease": None, "executor_seq": 0,
            })
            s.add(run)
            s.flush()
            if credentials is not None:
                self.credentials.save(s, run.id, credentials)
            data = deepcopy(run.data)
            self.event(s, run, data, "queued", "运行已排队")
            run.data = data
            return run.id

    def _load(self, s, run_id):
        run = s.get(Run, run_id)
        if not run:
            raise Conflict("运行不存在")
        robot = self.db.lock_robot(s, run.robot_id)
        s.refresh(run)
        return run, robot, deepcopy(run.data)

    def pending(self, s, run_id):
        return [op for op in s.scalars(select(Operation).where(Operation.run_id == run_id))
                if op.data["status"] in PENDING]

    def enqueue(self, s, run, data, action, params, request_id=None):
        request_id = request_id or uid()
        body = {"action": action, "params": params, "execution_attempt_id": data["attempt_id"]}
        existing = s.get(Operation, request_id)
        if existing:
            if existing.run_id != run.id or existing.data["body"] != body:
                raise Conflict("request_id 已用于不同请求")
            return existing.id
        if self.pending(s, run.id) and action != "stop":
            raise Conflict("上一操作结果尚未确认")
        s.add(Operation(id=request_id, run_id=run.id, data={
            "body": body, "status": "accepted", "sent": False,
            "created": self.clock(), "result": None,
        }))
        return request_id

    def request_stop(self, run_id, reason="administrator"):
        with self.db.transaction() as s:
            run, robot, d = self._load(s, run_id)
            if d["status"] in TERMINAL:
                return
            if d["phase"] == "queued":
                d.update(status="cancelled", phase="ended", ended=self.clock())
            else:
                d["stop_reason"] = d["stop_reason"] or reason
                d["status"] = "stopping"
                d["lease"] = None
                pending = self.pending(s, run.id)
                for op in pending:
                    if op.data["status"] == "accepted" and not op.data["sent"]:
                        od = deepcopy(op.data)
                        od["status"] = "cancelled"
                        op.data = od
                        if od["body"]["action"] == "resume":
                            d.update(attempt_id=od["body"]["execution_attempt_id"], phase="recovery")
                        elif od["body"]["action"] == "start":
                            # Never dispatched, so no executor can own this attempt.
                            d.update(status="stopped" if reason == "administrator" else "failed", phase="ended", ended=self.clock())
                            robot.active_run = None
            self.finish_round(s, run, d)
            self.event(s, run, d, "stop_requested", "运行在下发执行前取消" if d["phase"] == "ended" else "停止请求已记录，等待执行端确认")
            run.data = d

    def revoke(self, robot_id, rotate=False):
        token = secrets.token_urlsafe(32) if rotate else None
        with self.db.transaction() as s:
            robot = self.db.lock_robot(s, robot_id)
            robot.credential_hash = sha256(token.encode()).hexdigest() if token else None
            active = robot.active_run
        if active:
            self.request_stop(active, "credential_revoked")
        return token

    def tick(self, connected):
        now = self.clock()
        with self.db.transaction() as s:
            ids = list(s.scalars(select(Run.id).order_by(Run.created)))
        for run_id in ids:
            with self.db.transaction() as s:
                run, robot, d = self._load(s, run_id)
                if d["status"] in TERMINAL:
                    continue
                online = robot.id in connected
                if d["phase"] == "queued":
                    if robot.active_run or not online or not robot.credential_hash:
                        continue
                    robot.active_run = run.id
                    d.update(status="starting", phase="starting")
                    self.enqueue(s, run, d, "start", {"snapshot": d["snapshot"]})
                elif d.get("recovery_since") is not None and remaining(d, now) <= 0:
                    d["stop_reason"] = d["stop_reason"] or "budget_exhausted"
                    d["lease"] = None
                elif (d["phase"] == "recovery" and len(d.get("recovery_rounds", [])) >= MAX_RECOVERY_ROUNDS
                      and (not d.get("lease") or d["lease"]["expires"] <= now)):
                    d["stop_reason"] = d["stop_reason"] or "rounds_exhausted"
                    d["lease"] = None
                if d["stop_reason"]:
                    self.finish_round(s, run, d)
                    d["status"] = "stopping" if online else "uncertain"
                    ops = list(s.scalars(select(Operation).where(Operation.run_id == run.id)))
                    for op in ops:
                        if op.data["status"] == "accepted" and not op.data["sent"] and op.data["body"]["action"] != "stop":
                            od = deepcopy(op.data)
                            od["status"] = "cancelled"
                            op.data = od
                            if od["body"]["action"] == "resume":
                                d.update(attempt_id=od["body"]["execution_attempt_id"], phase="recovery")
                    if not any(op.data["body"]["action"] == "stop" for op in ops):
                        self.enqueue(s, run, d, "stop", {"reason": d["stop_reason"]})
                elif not online and d["phase"] != "queued":
                    d["status"] = "uncertain"
                elif d["phase"] == "failed" and not self.pending(s, run.id):
                    if len(d.get("recovery_rounds", [])) >= MAX_RECOVERY_ROUNDS:
                        d["stop_reason"] = "rounds_exhausted"
                        d["conclusion"] = {"reason": "已达到 3 轮接管上限，程序仍未完成。",
                            "attempted": ["已分配 3 轮 Agent 接管"],
                            "next_actions": ["管理员检查失败原因后重跑"], "evidence": []}
                    elif not d.get("recoverable") or remaining(d, now) <= 0:
                        d["stop_reason"] = "not_recoverable"
                    else:
                        d["phase"] = "opening"
                        self.enqueue(s, run, d, "open_recovery", {
                            "local_run_id": d["local_run_id"], "remaining_seconds": remaining(d, now),
                        })
                run.data = d

    def disconnect(self, robot_id):
        with self.db.transaction() as s:
            robot = self.db.lock_robot(s, robot_id)
            if robot.active_run:
                run = s.get(Run, robot.active_run)
                d = deepcopy(run.data)
                if d["status"] not in TERMINAL:
                    d["status"] = "uncertain"
                    d["lease"] = None
                    self.event(s, run, d, "disconnected", "控制连接断开，机器人仍被本次运行占用")
                    run.data = d

    def commands(self, robot_id):
        with self.db.transaction() as s:
            robot = self.db.lock_robot(s, robot_id)
            if not robot.active_run:
                return []
            run = s.get(Run, robot.active_run)
            run_data = deepcopy(run.data)
            messages = []
            for op in s.scalars(select(Operation).where(Operation.run_id == run.id)):
                d = deepcopy(op.data)
                if d["status"] != "accepted" or d["sent"]:
                    continue
                # Decrypt only for the authenticated robot transport. Never mutate
                # the persisted operation body with credentials.
                body = deepcopy(d["body"])
                if body["action"] == "start" and self.credentials is not None:
                    body["params"]["credentials"] = self.credentials.read(s, run.id)
                # A durable sent bit forbids blind resend after server/socket failure.
                d["sent"] = True
                op.data = d
                self.agent_activity(s, run, run_data, d, "running")
                messages.append({"type": "command", "console_run_id": run.id,
                                 "request_id": op.id, **body,
                                 **({"next_attempt_id": d["next_attempt_id"]} if d.get("next_attempt_id") else {})})
            run.data = run_data
            return messages

    def reconcile(self, robot_id, hello):
        with self.db.transaction() as s:
            robot = self.db.lock_robot(s, robot_id)
            robot.deployments = hello.get("deployments", [])
            if not robot.active_run:
                if hello.get("active_run"):
                    previous = s.get(Run, hello["active_run"])
                    if not previous or previous.robot_id != robot_id or previous.data["status"] not in TERMINAL:
                        raise Conflict("执行端持有控制台未知的运行")
                return
            run = s.get(Run, robot.active_run)
            d = deepcopy(run.data)
            active = hello.get("active_run")
            requests = hello.get("requests", {})
            # A journal's explicit absence proves that the executor never accepted it.
            for op in s.scalars(select(Operation).where(Operation.run_id == run.id)):
                od = deepcopy(op.data)
                if od["status"] in PENDING and op.id not in requests and hello.get("journal_complete"):
                    if od["status"] == "accepted":
                        od["sent"] = False
                        op.data = od
            if active not in {None, run.id}:
                raise Conflict("机器人现场归属不匹配")
            if active == run.id and hello.get("execution_attempt_id") == d["attempt_id"]:
                if hello.get("phase") == d["phase"] and not d["stop_reason"]:
                    d["status"] = {"recovery": "recovering", "program": "running"}.get(d["phase"], "uncertain")
            run.data = d

    def accept_message(self, robot_id, message, *, save_image=None):
        with self.db.transaction() as s:
            run, robot, d = self._load(s, message["console_run_id"])
            if robot.id != robot_id:
                raise Conflict("机器人不能报告其他机器人的运行")
            seq = message["seq"]
            if seq <= d["executor_seq"]:
                return d["executor_seq"]
            if seq != d["executor_seq"] + 1:
                raise Conflict("执行端事件序号有缺口，须补传")
            if (robot.active_run != run.id or d["status"] in TERMINAL) and message["type"] != "result":
                raise Conflict("运行已结束或现场不匹配")
            kind = message["type"]
            if kind == "result":
                op = s.get(Operation, message["request_id"])
                if not op or op.run_id != run.id:
                    raise Conflict("没有对应的请求")
                od = deepcopy(op.data)
                if message["execution_attempt_id"] != od["body"]["execution_attempt_id"]:
                    raise Conflict("操作尝试不匹配")
                if save_image:
                    save_image(s, run, message)
                od.update(status=message["status"], result=message.get("result", {}))
                op.data = od
                self.agent_activity(s, run, d, od, od["status"])
                if od["result"].get("requires_administrator"):
                    d["stop_reason"] = "requires_administrator"
                    d["conclusion"] = {"reason": od["result"]["requires_administrator"],
                        "attempted": ["观察页面并保留可用证据"], "next_actions": ["管理员处理后从 dashboard 重跑"],
                        "evidence": [od["result"]["evidence_id"]] if od["result"].get("evidence_id") else []}
                    d["lease"] = None
                if od["status"] == "unknown":
                    d["status"] = "uncertain"
                    d["lease"] = None
                if od["status"] == "failed" and od["body"]["action"] in {"start", "open_recovery"}:
                    d["stop_reason"] = "executor_error"
                    self.event(s, run, d, "preparation_failed", "执行环境准备失败" if od["body"]["action"] == "start" else "无法打开接管现场",
                               details=od["result"])
                if od["status"] == "failed" and od["body"]["action"] == "resume" and d["phase"] == "submitting":
                    if od["result"].get("recovery_active"):
                        d.update(attempt_id=od["body"]["execution_attempt_id"], phase="recovery", status="recovering", lease=None)
                    else:
                        d.update(status="uncertain", stop_reason="resume_result_unknown", lease=None)
                if od["result"].get("screenshot_missing"):
                    self.event(s, run, d, "evidence_missing", "现场截图未取得：" + od["result"]["screenshot_missing"])
            else:
                if message["execution_attempt_id"] != d["attempt_id"]:
                    raise Conflict("拒绝旧尝试事件")
                payload = message.get("data", {})
                at = min(self.clock(), float(message.get("at", self.clock())))
                if kind == "recovery_started":
                    if d["phase"] != "opening":
                        raise Conflict("未请求打开恢复上下文")
                    d.update(phase="recovery", status="recovering", recovery_since=at, lease=None)
                    self.event(s, run, d, kind, "Agent 已实际接管，开始累计接管时间")
                elif kind == "program_started":
                    if d["phase"] not in {"starting", "submitting"}:
                        raise Conflict("未分配本次程序执行")
                    pause_budget(d, at)
                    d.update(phase="program", status="stopping" if d["stop_reason"] else "running")
                    d["local_run_id"] = payload["local_run_id"]
                    d["attempts"].append({"id": d["attempt_id"], "local_run_id": payload["local_run_id"],
                                          "status": "running", "started": at})
                    self.event(s, run, d, kind, "程序开始执行，接管计时暂停")
                elif kind == "resolved":
                    if len(d["attempts"]) > 1 and (payload["inputs"] != d["snapshot"]["inputs"] or payload["download_dir"] != d["snapshot"]["download_dir"]):
                        raise Conflict("续跑不能改变原参数")
                    d["snapshot"] = {**d["snapshot"], "inputs": payload["inputs"], "download_dir": payload["download_dir"]}
                elif kind == "attempt_finished":
                    status = payload["status"]
                    if status not in {"succeeded", "failed", "stopped"}:
                        raise Conflict("执行结果无效")
                    d["local_run_id"] = payload["local_run_id"]
                    if not d["attempts"] or d["attempts"][-1]["id"] != d["attempt_id"]:
                        d["attempts"].append({"id": d["attempt_id"], "local_run_id": payload["local_run_id"]})
                    d["attempts"][-1].update(status=status, result=payload, ended=at)
                    d.update(phase="failed" if status == "failed" else "finishing", lease=None,
                             recoverable=bool(payload.get("recoverable")), last_result=payload)
                    self.event(s, run, d, kind, {"succeeded": "程序及原校验通过，等待收尾确认", "failed": "本次执行失败", "stopped": "程序已在步骤边界停止"}[status], details=payload)
                elif kind == "ended":
                    pause_budget(d, at)
                    self.finish_round(s, run, d)
                    status = "failed"
                    if d.get("last_result", {}).get("status") == "succeeded":
                        status = "succeeded"
                    elif d["stop_reason"] == "administrator":
                        status = "stopped"
                    d.update(status=status, phase="ended", ended=at, lease=None)
                    robot.active_run = None
                    self.event(s, run, d, kind, {"succeeded": "运行成功，机器人已释放", "failed": "运行失败，机器人已释放", "stopped": "运行已停止，机器人已释放"}[status], details=payload)
                elif kind == "uncertain":
                    d.update(status="uncertain", lease=None)
                    self.event(s, run, d, kind, "执行结束尚未确认，继续保留机器人占用", details=payload)
                elif kind == "progress":
                    # Business messages are a fixed vocabulary, never raw diagnostics.
                    labels = {"step.started": "步骤开始", "step.succeeded": "步骤通过原校验", "step.failed": "步骤失败"}
                    self.event(s, run, d, kind, (payload.get("step_name", "") + "：" if payload.get("step_name") else "") + labels.get(payload.get("event_type"), "程序执行事件"), details=payload)
                elif kind == "evidence":
                    if save_image:
                        save_image(s, run, message)
                    self.event(s, run, d, kind, "现场截图已上传", details=payload)
                elif kind == "evidence_missing":
                    self.event(s, run, d, kind, "现场截图未取得：" + payload["reason"], details=payload)
                else:
                    raise Conflict("未知执行事件")
            d["executor_seq"] = seq
            run.data = d
            return seq

    def claim(self, run_id, connected):
        with self.db.transaction() as s:
            run, robot, d = self._load(s, run_id)
            now = self.clock()
            lease = d.get("lease")
            if (d["phase"] != "recovery" or d["status"] != "recovering" or d["stop_reason"]
                    or robot.id not in connected or not robot.credential_hash or remaining(d, now) <= 0
                    or (lease and lease["expires"] > now) or self.pending(s, run.id)):
                raise Conflict("当前运行不能分配 Agent")
            rounds = d.setdefault("recovery_rounds", [])
            if len(rounds) >= MAX_RECOVERY_ROUNDS:
                raise Conflict("已达到 3 轮接管上限")
            self.finish_round(s, run, d)
            rounds.append({"number": len(rounds) + 1, "started": now, "attempt_id": d["attempt_id"]})
            self.event(s, run, d, "agent_activity", f"第 {len(rounds)} 轮 · Agent 开始分析失败现场")
            d["lease"] = {"id": uid(), "expires": now + 30}
            run.data = d
            return {"console_run_id": run.id, "execution_attempt_id": d["attempt_id"],
                    "lease": d["lease"]["id"], "remaining_seconds": remaining(d, now),
                    "recovery_round": len(rounds), "max_recovery_rounds": MAX_RECOVERY_ROUNDS}

    def agent_state(self, run_id, lease_id, renew=False):
        with self.db.transaction() as s:
            run, robot, d = self._load(s, run_id)
            lease = d.get("lease")
            valid = bool(lease and hmac.compare_digest(lease["id"], lease_id) and lease["expires"] > self.clock())
            if renew and valid:
                lease["expires"] = self.clock() + 30
                run.data = d
            return {"active": valid and d["status"] == "recovering" and not d["stop_reason"],
                    "remaining_seconds": remaining(d, self.clock()), "phase": d["phase"]}

    def tool(self, run_id, lease_id, attempt_id, request_id, action, params, connected):
        if action not in TOOLS:
            raise Conflict("不提供此工具")
        with self.db.transaction() as s:
            run, robot, d = self._load(s, run_id)
            old = s.get(Operation, request_id)
            if old:
                if old.run_id != run.id or old.data["body"] != {"action": action, "params": params, "execution_attempt_id": attempt_id}:
                    raise Conflict("request_id 内容不一致")
                return old.id
            lease = d.get("lease")
            if (not lease or lease["id"] != lease_id or lease["expires"] <= self.clock()
                    or d["attempt_id"] != attempt_id or d["phase"] != "recovery" or d["stop_reason"]
                    or d["status"] != "recovering" or robot.id not in connected
                    or robot.active_run != run.id or not robot.credential_hash or remaining(d, self.clock()) <= 0):
                raise Conflict("接管已停止、断连、过期或尝试不匹配")
            if action == "give_up":
                d["stop_reason"] = "agent_gave_up"
                d["conclusion"] = params
                d["lease"] = None
            op_id = self.enqueue(s, run, d, action, params, request_id)
            op = s.get(Operation, op_id)
            op.data = {**op.data, "recovery_round": len(d.get("recovery_rounds", []))}
            if action in {"resume", "give_up"}:
                summary = params.get("summary")
                if not isinstance(summary, str) or not summary.strip() or len(summary) > 4000:
                    raise Conflict("请提交本轮最终接管总结（1–4000 字）")
                self.finish_round(s, run, d, summary.strip())
            if action == "resume":
                # Resume commands keep the source attempt in their envelope.
                op = s.get(Operation, op_id)
                new_id = uid()
                od = deepcopy(op.data)
                od["next_attempt_id"] = new_id
                op.data = od
                d.update(attempt_id=new_id, phase="submitting", lease=None)
            run.data = d
            return op_id
