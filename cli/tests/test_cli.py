"""Unit tests for the pure CLI helpers (no click / ADK needed)."""
from forsch.cli.scaffold import new_agent_block
from forsch.cli.workspace import find_workspace


def test_new_agent_block_naming():
    b = new_agent_block("foo-bar")
    assert b["package"] == "forsch.agent_foo_bar.agent"
    assert b["adk_name"] == "foo_bar_agent"
    assert b["model_code"] == "forsch.agent_foo_bar.agent.foo_bar_model"
    assert b["web_entrypoint"] == "web_agents/foo-bar"
    assert b["tools"] == []
    assert b["safety_level"] == "read_only"


def test_new_agent_block_description_fills_purpose():
    b = new_agent_block("x", description="does the X thing")
    assert b["description"] == "does the X thing"
    assert b["purpose"] == "does the X thing"


def test_find_workspace_prefers_env(tmp_path, monkeypatch):
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path))
    assert find_workspace() == tmp_path


def test_find_workspace_walks_up_to_manifest(tmp_path, monkeypatch):
    monkeypatch.delenv("FORSCH_ADK_WORKSPACE", raising=False)
    (tmp_path / "agent_specs").mkdir()
    (tmp_path / "agent_specs" / "agents.yaml").write_text("version: 1\nagents: {}\n")
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    assert find_workspace(sub) == tmp_path


def test_find_workspace_none_when_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("FORSCH_ADK_WORKSPACE", raising=False)
    assert find_workspace(tmp_path) is None


def test_scaffold_eval_set_shape(tmp_path):
    import json

    from forsch.cli.evals import eval_set_path, scaffold_eval_set

    p = tmp_path / "shelby.evalset.json"
    scaffold_eval_set(p, "shelby")
    d = json.loads(p.read_text())
    assert d["eval_set_id"] == "shelby-evals"
    case = d["eval_cases"][0]
    assert case["conversation"][0]["user_content"]["role"] == "user"
    assert case["conversation"][0]["final_response"]["role"] == "model"
    assert eval_set_path(tmp_path, "shelby").name == "shelby.evalset.json"


def test_graph_bare_strips_tool_prefix():
    from forsch.cli.graph import _bare

    assert _bare("forsch.adk_components.tools.search_movies") == "search_movies"
    assert _bare("search_movies") == "search_movies"


def test_goal_preamble_includes_goal():
    from forsch.cli.goal import goal_preamble

    out = goal_preamble("  wire shelby's grocery tool  ")
    assert "wire shelby's grocery tool" in out
    assert "GOAL MODE" in out


def test_skills_lists_and_resolves_dir(tmp_path):
    from forsch.cli.skills import list_skill_names, skills_dir

    d = tmp_path / "skills"
    d.mkdir()
    (d / "alpha.md").write_text("# Alpha\nfirst line\n")
    (d / "beta.md").write_text("# Beta\nsecond line\n")
    assert list_skill_names(tmp_path) == ["alpha", "beta"]
    assert skills_dir(tmp_path) == d


def test_goal_ledger_roundtrip(tmp_path):
    from forsch.cli.goal_engine import ledger
    from forsch.cli.goal_engine.schema import GoalPlan, GoalStep, new_id

    plan = GoalPlan(id=new_id(), goal="wire shelby's grocery tool", steps=[
        GoalStep(id="s1", intent="add log_groceries", actuator="add_tool",
                 args={"agent_id": "shelby", "tool_name": "log_groceries"},
                 success_check="check passes"),
        GoalStep(id="s2", intent="validate", actuator="check_agent",
                 args={"agent_id": "shelby"}, success_check="0 red tools"),
    ])
    ledger.checkpoint(tmp_path, plan)
    back = ledger.load(tmp_path, plan.id)
    assert back.goal == plan.goal
    assert back.steps[0].actuator == "add_tool"
    assert back.next_actionable().id == "s1"
    assert plan.id in [p.id for p in ledger.list_goals(tmp_path)]


def test_goal_actuators_exclude_gate_crossing_verbs():
    from forsch.cli.goal_engine.actuators import SAFE_ACTUATORS

    assert "deploy" not in SAFE_ACTUATORS
    assert "delete" not in SAFE_ACTUATORS
    assert "build_agent" in SAFE_ACTUATORS and "check_agent" in SAFE_ACTUATORS


def test_goal_plan_settled_logic():
    from forsch.cli.goal_engine.schema import GoalPlan, GoalStep

    step = GoalStep(id="s1", intent="x", actuator="check_agent", success_check="ok")
    plan = GoalPlan(id="g", goal="g", steps=[step])
    assert not plan.is_settled()
    step.status = "passed"
    assert plan.is_settled()
    assert plan.next_actionable() is None


def test_judge_deterministic_verdicts():
    from forsch.cli.goal_engine.judge import deterministic_verdict
    from forsch.cli.goal_engine.schema import GoalStep

    check = GoalStep(id="s1", intent="c", actuator="check_agent", success_check="green")
    assert deterministic_verdict(check, ["gate-red-count=0\nall tools validated"]).verdict == "pass"
    assert deterministic_verdict(check, ["gate-red-count=2\nissues found"]).verdict == "fail"
    # regression: a green report containing 'required'/'credentials' must NOT false-fail
    assert deterministic_verdict(check, ["gate-red-count=0\ncredentials required"]).verdict == "pass"
    # no machine-readable count -> defer to the LLM judge
    assert deterministic_verdict(check, ["some prose with no marker"]) is None
    # the crash marker fails ANY actuator, before its specific branch
    assert deterministic_verdict(check, ["[ACTUATION-ERROR] KeyError: x"]).verdict == "fail"
    manual = GoalStep(id="s2", intent="m", actuator="manual", args={"command": "git push"}, success_check="x")
    v = deterministic_verdict(manual, ["(manual)"])
    assert v.verdict == "blocked" and "git push" in (v.next_directive or "")
    add = GoalStep(id="s3", intent="a", actuator="add_tool", success_check="x")
    assert deterministic_verdict(add, ["added foo to bar"]) is None
    assert deterministic_verdict(add, ["[ACTUATION-ERROR] boom"]).verdict == "fail"


def test_goal_engine_parks_when_no_fix(tmp_path):
    import asyncio

    from forsch.cli.goal_engine.engine import run_goal
    from forsch.cli.goal_engine.schema import GoalPlan, GoalStep, Verdict, new_id

    async def plan_fn(ws, goal):
        return GoalPlan(id=new_id(), goal=goal, status="executing",
                        steps=[GoalStep(id="s1", intent="x", actuator="add_tool", args={}, success_check="x")])

    calls = {"judged": 0}

    async def judge_fn(ws, step, evidence):
        calls["judged"] += 1
        return Verdict(step_id=step.id, reasoning="no", verdict="fail", next_directive="fix it")

    async def replan_fn(ws, plan, step, directive):
        return {"amended_args": None, "fix_steps": []}   # no safe fix available

    plan = asyncio.run(run_goal(tmp_path, "g", plan_fn=plan_fn, judge_fn=judge_fn, replan_fn=replan_fn,
                                actuate_fn=lambda ws, a, args: "did a thing"))
    assert plan.steps[0].status == "blocked"                         # no fix -> parked
    assert calls["judged"] == 1                                       # not looped
    assert any("no fix found" in e for e in plan.steps[0].evidence)


def test_goal_engine_replan_amends_args(tmp_path):
    import asyncio

    from forsch.cli.goal_engine.engine import run_goal
    from forsch.cli.goal_engine.schema import GoalPlan, GoalStep, Verdict, new_id

    async def plan_fn(ws, goal):
        return GoalPlan(id=new_id(), goal=goal, status="executing",
                        steps=[GoalStep(id="s1", intent="x", actuator="add_tool",
                                        args={"agent_id": "a", "tool_name": "bad"}, success_check="x")])

    async def judge_fn(ws, step, evidence):
        if step.args.get("tool_name") == "good":
            return Verdict(step_id=step.id, reasoning="ok", verdict="pass")
        return Verdict(step_id=step.id, reasoning="bad tool", verdict="fail", next_directive="use 'good'")

    async def replan_fn(ws, plan, step, directive):
        return {"amended_args": {"tool_name": "good"}, "fix_steps": []}

    plan = asyncio.run(run_goal(tmp_path, "g", plan_fn=plan_fn, judge_fn=judge_fn, replan_fn=replan_fn,
                                actuate_fn=lambda ws, a, args: "did"))
    assert plan.steps[0].status == "passed"               # amended -> retried -> passed
    assert plan.steps[0].args["tool_name"] == "good"      # the amendment stuck


def test_goal_engine_replan_inserts_fix_step(tmp_path):
    import asyncio

    from forsch.cli.goal_engine.engine import run_goal
    from forsch.cli.goal_engine.schema import GoalPlan, GoalStep, Verdict, new_id

    async def plan_fn(ws, goal):
        return GoalPlan(id=new_id(), goal=goal, status="executing",
                        steps=[GoalStep(id="s1", intent="main", actuator="build_agent",
                                        args={"agent_id": "a"}, success_check="x")])

    state = {"fix_ran": False}

    async def judge_fn(ws, step, evidence):
        if step.id == "fix1":
            state["fix_ran"] = True
            return Verdict(step_id=step.id, reasoning="fixed", verdict="pass")
        if state["fix_ran"]:
            return Verdict(step_id=step.id, reasoning="ok now", verdict="pass")
        return Verdict(step_id=step.id, reasoning="needs fix", verdict="fail", next_directive="add the tool")

    async def replan_fn(ws, plan, step, directive):
        return {"amended_args": None,
                "fix_steps": [GoalStep(id="fix1", intent="add tool", actuator="add_tool",
                                       args={}, success_check="x")]}

    plan = asyncio.run(run_goal(tmp_path, "g", plan_fn=plan_fn, judge_fn=judge_fn, replan_fn=replan_fn,
                                actuate_fn=lambda ws, a, args: "did"))
    ids = [s.id for s in plan.steps]
    assert "fix1" in ids and ids.index("fix1") < ids.index("s1")    # fix inserted BEFORE the failed step
    assert state["fix_ran"]
    assert all(s.status == "passed" for s in plan.steps)            # fix + main both passed


def test_set_config_gate_privilege():
    from forsch.cli.operator import _set_config_gate

    # safety_level without confirm -> blocked privilege change
    blocked = _set_config_gate("safety_level", False)
    assert blocked and blocked.get("blocked") == "privilege_change"
    # safety_level WITH confirm -> allowed through
    assert _set_config_gate("safety_level", True) is None
    # ordinary editable fields -> allowed
    assert _set_config_gate("model", False) is None
    assert _set_config_gate("discord_channels", False) is None
    # a non-editable field -> refused, not silently written
    assert "error" in _set_config_gate("package", False)


def test_goal_engine_loop_with_stubs(tmp_path):
    import asyncio

    from forsch.cli.goal_engine import ledger
    from forsch.cli.goal_engine.engine import run_goal
    from forsch.cli.goal_engine.schema import GoalPlan, GoalStep, Verdict, new_id

    async def plan_fn(ws, goal):
        return GoalPlan(id=new_id(), goal=goal, status="executing", steps=[
            GoalStep(id="s1", intent="check shelby", actuator="check_agent",
                     args={"agent_id": "shelby"}, success_check="0 red"),
            GoalStep(id="s2", intent="deploy", actuator="manual",
                     args={"command": "git push"}, success_check="zach runs it"),
        ])

    def actuate_fn(ws, actuator, args):
        return "red: 0; all green" if actuator == "check_agent" else "(manual)"

    async def judge_fn(ws, step, evidence):
        if step.actuator == "manual":
            return Verdict(step_id=step.id, reasoning="manual", verdict="blocked", next_directive="git push")
        return Verdict(step_id=step.id, reasoning="ok", verdict="pass")

    plan = asyncio.run(run_goal(tmp_path, "smoke", max_iterations=10,
                                plan_fn=plan_fn, judge_fn=judge_fn, actuate_fn=actuate_fn))
    assert plan.steps[0].status == "passed"
    assert plan.steps[1].status == "blocked"
    assert plan.status == "blocked"
    assert ledger.load(tmp_path, plan.id).steps[0].status == "passed"
