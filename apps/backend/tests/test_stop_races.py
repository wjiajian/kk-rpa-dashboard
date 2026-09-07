from test_control import env


def test_stop_cancels_unsent_action_before_browser_dispatch(env):
    job = env.recover()
    env.c.tool(env.run, job["lease"], job["execution_attempt_id"], "unsent-click", "act", {"operation": "click"}, {env.robot})
    env.c.request_stop(env.run)
    env.c.tick({env.robot})
    assert [c["action"] for c in env.c.commands(env.robot)] == ["stop"]


def test_stop_before_start_dispatch_has_no_robot_work_to_wait_for(env):
    env.c.tick({env.robot})
    env.c.request_stop(env.run)
    assert env.c.commands(env.robot) == []
    assert env.owned() is None
    assert env.state()["status"] == "stopped"


def test_stop_before_resume_dispatch_keeps_executor_source_attempt(env):
    job = env.recover()
    env.c.tool(env.run, job["lease"], job["execution_attempt_id"], "unsent-resume", "resume", {"from_step": "S2", "summary": "提交 S2，等待执行端校验。"}, {env.robot})
    env.c.request_stop(env.run)
    assert env.state()["attempt_id"] == job["execution_attempt_id"]
    env.c.tick({env.robot})
    assert [c["action"] for c in env.c.commands(env.robot)] == ["stop"]
    env.send("ended", attempt=job["execution_attempt_id"])
    assert env.owned() is None
