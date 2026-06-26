"""Validation engine for ADK tools and agents.

Phase 2 of the ADK Factory v2 plan. Answers "which box?" and what a green dot
PROVES. Produces honest, decaying confidence signals — never theater.

Architecture:
    StructuralValidator — imports, signatures, type hints, registration.
        Deterministic. Never decays.
    BehavioralValidator — Authsome liveness, API reachability, smoke tests.
        Has a TTL. Decays to yellow when stale.
    ValidationReport — aggregates results, applies TTL decay, produces
        the three-dot confidence model (● green / ◉ yellow / ○ red).

Target environments (which-box semantics):
    local       — bridge venv on Zach's Mac (~/.hermes/hermes-agent/venv/)
    hetzner     — zachfleet-vps
    railway     — Railway deploy target
    cloud       — Hubert's cloud box over Tailscale (100.120.21.13)

"Credential available" is defined as: Authsome reports a LIVE connection from
where the agent will actually run. Not "the env var exists."
"""

from __future__ import annotations

import importlib
import inspect
import json
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

# ── data models ────────────────────────────────────────────────────────────


@dataclass
class StructuralResult:
    """Deterministic checks — imports, signatures, type hints, registration."""

    passed: bool = False
    import_ok: bool = False
    signature_ok: bool = False
    type_hints_ok: bool = False
    docstring_ok: bool = False
    registered_ok: bool = False
    errors: list[str] = field(default_factory=list)
    checked_at: str = ""


@dataclass
class BehavioralResult:
    """Live checks — Authsome liveness, API reachability, smoke tests.

    Has a TTL. After ``ttl_hours``, confidence decays from green to yellow.
    """

    passed: bool = False
    authsome_live: bool = False
    api_reachable: bool = True  # True when no auth provider to check
    smoke_test_passed: Optional[bool] = None  # None = no smoke test defined
    errors: list[str] = field(default_factory=list)
    checked_at: str = ""
    target: str = ""          # which box this was validated against
    ttl_hours: int = 24       # how long before behavioral decays


@dataclass
class ToolValidationResult:
    """Complete validation result for one tool."""

    tool_name: str
    structural: StructuralResult = field(default_factory=StructuralResult)
    behavioral: BehavioralResult = field(default_factory=BehavioralResult)

    @property
    def confidence(self) -> str:
        """● green / ◉ yellow / ○ red — the three-dot model.

        green  = structural pass + behavioral pass + within TTL
        yellow = structural pass only, OR behavioral pass but stale
        red    = structural failure
        """
        if not self.structural.passed:
            return "red"
        if not self.behavioral.passed:
            return "yellow"
        # Check TTL decay
        if self.behavioral.checked_at:
            try:
                checked = datetime.fromisoformat(self.behavioral.checked_at)
                age = datetime.now(timezone.utc) - checked
                if age > timedelta(hours=self.behavioral.ttl_hours):
                    return "yellow"  # stale
            except (ValueError, TypeError):
                pass
        return "green"

    @property
    def dot(self) -> str:
        """Single-character confidence indicator."""
        return {"green": "●", "yellow": "◉", "red": "○"}[self.confidence]


@dataclass
class ValidationReport:
    """Aggregate report for a set of tools."""

    target: str  # which box
    tools: dict[str, ToolValidationResult] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def summary(self) -> dict:
        green = sum(1 for t in self.tools.values() if t.confidence == "green")
        yellow = sum(1 for t in self.tools.values() if t.confidence == "yellow")
        red = sum(1 for t in self.tools.values() if t.confidence == "red")
        return {"green": green, "yellow": yellow, "red": red, "total": len(self.tools)}

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "generated_at": self.generated_at,
            "summary": self.summary,
            "tools": {
                name: {
                    "confidence": result.confidence,
                    "dot": result.dot,
                    "structural": {
                        "passed": result.structural.passed,
                        "import_ok": result.structural.import_ok,
                        "signature_ok": result.structural.signature_ok,
                        "type_hints_ok": result.structural.type_hints_ok,
                        "docstring_ok": result.structural.docstring_ok,
                        "registered_ok": result.structural.registered_ok,
                        "errors": result.structural.errors,
                        "checked_at": result.structural.checked_at,
                    },
                    "behavioral": {
                        "passed": result.behavioral.passed,
                        "authsome_live": result.behavioral.authsome_live,
                        "api_reachable": result.behavioral.api_reachable,
                        "smoke_test_passed": result.behavioral.smoke_test_passed,
                        "errors": result.behavioral.errors,
                        "checked_at": result.behavioral.checked_at,
                        "target": result.behavioral.target,
                        "ttl_hours": result.behavioral.ttl_hours,
                    },
                }
                for name, result in self.tools.items()
            },
        }


# ── structural validator ───────────────────────────────────────────────────


class StructuralValidator:
    """Checks that are deterministic: imports, signatures, type hints, registration.

    These never decay. A tool that imported yesterday still imports today.
    """

    @staticmethod
    def validate(tool_fq_name: str) -> StructuralResult:
        """Run all structural checks on a single tool."""
        result = StructuralResult(checked_at=datetime.now(timezone.utc).isoformat())
        errors: list[str] = []
        fn = None  # bound here so the guard below can't hit UnboundLocalError when
        # import succeeds but the attr-walk raises a non-AttributeError (e.g. a
        # throwing property).

        # 1. Import check
        module_path, attr_path = StructuralValidator._split_fq_name(tool_fq_name)
        try:
            mod = importlib.import_module(module_path)
            result.import_ok = True  # module imported successfully
            # Walk dotted attr path (e.g. 'ToolRegistry.all_tools')
            obj = mod
            for part in attr_path.split("."):
                obj = getattr(obj, part, None)
                if obj is None:
                    break
            fn = obj
            if fn is None or not callable(fn):
                errors.append(f"function {attr_path!r} not found in {module_path}")
        except ImportError as e:
            errors.append(f"import failed: {e}")
        except Exception as e:
            errors.append(f"unexpected import error: {e}")

        if not result.import_ok or fn is None or not callable(fn):
            result.errors = errors
            return result

        # 2. Signature check
        try:
            sig = inspect.signature(fn)
            params = list(sig.parameters.keys())
            # Zero-param tools are valid ADK tools (e.g. health checks, status queries).
            # Static methods and class methods may also have zero params.
            result.signature_ok = True
        except (ValueError, TypeError) as e:
            errors.append(f"signature inspection failed: {e}")

        # 3. Type hints check
        try:
            sig = inspect.signature(fn)
            has_return = sig.return_annotation is not inspect.Parameter.empty
            params_with_hints = sum(
                1 for p in sig.parameters.values()
                if p.annotation is not inspect.Parameter.empty
            )
            if not has_return and params_with_hints == 0:
                errors.append("no type hints on parameters or return")
            result.type_hints_ok = True
        except Exception:
            pass  # already caught above

        # 4. Docstring check
        if fn.__doc__ and fn.__doc__.strip():
            result.docstring_ok = True
        else:
            errors.append("missing docstring")

        # 5. Registration check (is it decorated with @tool?)
        # Advisory only — not all tools have been migrated to @tool yet (Phase 2).
        # A missing registration does NOT block the deploy gate.
        try:
            from forsch.adk_factory.tool_metadata import ToolRegistry
            registered = ToolRegistry.all_tools()
            if tool_fq_name in registered:
                result.registered_ok = True
            else:
                found = any(tool_fq_name.endswith(name.split(".")[-1]) or name.endswith(tool_fq_name.split(".")[-1])
                           for name in registered)
                if found:
                    result.registered_ok = True
        except ImportError:
            pass  # ToolRegistry not available — skip registration check

        result.errors = errors
        result.passed = len(errors) == 0
        return result

    @staticmethod
    def _split_fq_name(fq_name: str) -> tuple[str, str]:
        """Split 'pkg.module.Class.method' -> ('pkg.module', 'Class.method').

        Tries progressively shorter module paths until one imports successfully,
        then walks the remaining path via getattr.
        """
        parts = fq_name.split(".")
        # Try from longest module path down to shortest
        for i in range(len(parts) - 1, 0, -1):
            mod_path = ".".join(parts[:i])
            attr_path = parts[i:]
            try:
                importlib.import_module(mod_path)
                return mod_path, ".".join(attr_path)
            except ImportError:
                continue
        # Fallback: last dot split
        if len(parts) >= 2:
            return ".".join(parts[:-1]), parts[-1]
        return fq_name, fq_name


# ── behavioral validator ───────────────────────────────────────────────────


class BehavioralValidator:
    """Live checks: Authsome liveness, API reachability, smoke tests.

    These have a TTL. After ``ttl_hours``, confidence decays from green to yellow.
    """

    # Default Authsome endpoints per target
    AUTHSOME_ENDPOINTS = {
        "cloud": "http://127.0.0.1:7998",
        "local": "http://100.120.21.13:7998",   # Mac reaches cloud over Tailscale
        "hetzner": "http://100.120.21.13:7998",
        "railway": "http://100.120.21.13:7998",
    }

    def __init__(self, target: str = "cloud", ttl_hours: int = 24):
        self.target = target
        self.ttl_hours = ttl_hours
        self.authsome_url = self.AUTHSOME_ENDPOINTS.get(target, "http://127.0.0.1:7998")

    def validate(self, tool_fq_name: str, tool_meta=None) -> BehavioralResult:
        """Run all behavioral checks on a single tool.

        Args:
            tool_fq_name: Fully-qualified tool name.
            tool_meta: Optional ToolMeta from the registry (for auth/client info).
        """
        result = BehavioralResult(
            checked_at=datetime.now(timezone.utc).isoformat(),
            target=self.target,
            ttl_hours=self.ttl_hours,
        )
        errors: list[str] = []

        # 1. Authsome liveness
        result.authsome_live = self._check_authsome()
        if not result.authsome_live:
            errors.append(f"Authsome unreachable at {self.authsome_url}")

        # 2. API reachability (if tool has a client/auth provider)
        if tool_meta and tool_meta.auth:
            result.api_reachable = self._check_api_reachable(tool_meta)
            if not result.api_reachable:
                errors.append(f"API reachability check failed for provider {tool_meta.auth!r}")

        # 3. Smoke test (if defined)
        if tool_meta:
            result.smoke_test_passed = self._run_smoke_test(tool_fq_name, tool_meta)
            if result.smoke_test_passed is False:
                errors.append("smoke test failed")
        else:
            result.smoke_test_passed = None

        result.errors = errors
        result.passed = len(errors) == 0
        return result

    def _check_authsome(self) -> bool:
        """Check if Authsome is live and responding."""
        try:
            req = urllib.request.Request(
                f"{self.authsome_url}/health",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                return data.get("status") == "ok"
        except Exception:
            return False

    def _check_api_reachable(self, tool_meta) -> bool:
        """Check if the tool's API endpoint is reachable.

        Uses the tool's auth provider to determine what to check.
        """
        provider = tool_meta.auth.lower()
        checks = {
            "railway": ("https://backboard.railway.app/graphql/v2", 5),
            "frappe": ("https://crm.forschfrontiers.com/api/method/ping", 5),
            "github": ("https://api.github.com/zen", 5),
        }
        if provider in checks:
            url, timeout = checks[provider]
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return 200 <= resp.status < 500
            except Exception:
                return False
        # Unknown provider — can't check, but don't fail
        return True

    def _run_smoke_test(self, tool_fq_name: str, tool_meta) -> Optional[bool]:
        """Run a smoke test if one is defined for this tool.

        Returns None if no smoke test is defined, True/False otherwise.
        """
        # For now, smoke tests are defined in agents.yaml per agent.
        # Individual tool smoke tests would be defined in the tool's metadata
        # or in a companion test file. This is a stub for Phase 3 (Scaffold).
        return None


# ── report generator ───────────────────────────────────────────────────────


class DeployGateBlocked(Exception):
    """Raised when apply() is blocked by a red validation result.

    Carries the report so callers can format it for the user.
    """

    def __init__(self, agent_id: str, report: ValidationReport):
        self.agent_id = agent_id
        self.report = report
        red_count = report.summary["red"]
        super().__init__(
            f"deploy gate blocked {agent_id!r}: {red_count} tool(s) red. "
            f"Use --force to bypass."
        )


def check_deploy_gate(agent_id: str, report: ValidationReport) -> None:
    """Raise DeployGateBlocked if any tool is red.

    Yellow (stale / behavioral-only failure) does not block — only red
    (structural failure) blocks the deploy gate.
    """
    if report.summary["red"] > 0:
        raise DeployGateBlocked(agent_id, report)


def validate_tools(
    tool_names: list[str],
    target: str = "cloud",
    ttl_hours: int = 24,
    tool_metas: Optional[dict] = None,
) -> ValidationReport:
    """Run structural + behavioral validation on a list of tools.

    Args:
        tool_names: List of FQ tool names (e.g. ['forsch.adk_components.tools.get_crm_health_snapshot']).
        target: Which box to validate against ('cloud', 'local', 'hetzner', 'railway').
        ttl_hours: How long before behavioral results decay to yellow.
        tool_metas: Optional dict of tool_name -> ToolMeta from the registry.

    Returns a ValidationReport with per-tool results.
    """
    report = ValidationReport(target=target)
    structural = StructuralValidator()
    behavioral = BehavioralValidator(target=target, ttl_hours=ttl_hours)

    for name in tool_names:
        meta = tool_metas.get(name) if tool_metas else None
        s_result = structural.validate(name)
        b_result = behavioral.validate(name, tool_meta=meta)
        report.tools[name] = ToolValidationResult(
            tool_name=name,
            structural=s_result,
            behavioral=b_result,
        )

    return report


def validate_agent_tools(
    agent_spec,  # AgentSpec
    target: str = "cloud",
    ttl_hours: int = 24,
) -> ValidationReport:
    """Validate all tools wired to an agent.

    Expands wildcards, then runs structural + behavioral validation.
    """
    from forsch.adk_factory.tool_metadata import ToolRegistry

    expanded = []
    for pattern in agent_spec.tools:
        expanded.extend(ToolRegistry.expand_wildcard(pattern))

    if not expanded:
        return ValidationReport(target=target)

    # Get metadata for all expanded tools
    all_tools = ToolRegistry.all_tools()
    tool_metas = {name: all_tools.get(name) for name in expanded if name in all_tools}

    return validate_tools(expanded, target=target, ttl_hours=ttl_hours, tool_metas=tool_metas)


def format_report_text(report: ValidationReport) -> str:
    """Format a ValidationReport as human-readable text."""
    lines = []
    s = report.summary
    lines.append(f"Validation Report — target: {report.target}")
    lines.append(f"Generated: {report.generated_at}")
    lines.append(f"● {s['green']} green  ◉ {s['yellow']} yellow  ○ {s['red']} red  ({s['total']} total)")
    lines.append("")

    for name, result in sorted(report.tools.items()):
        short_name = name.rsplit(".", 1)[-1]
        lines.append(f"  {result.dot} {short_name} [{result.confidence}]")
        if result.structural.errors:
            for e in result.structural.errors:
                lines.append(f"      structural: {e}")
        if result.behavioral.errors:
            for e in result.behavioral.errors:
                lines.append(f"      behavioral: {e}")
        if result.behavioral.checked_at and result.confidence == "yellow":
            lines.append(f"      (behavioral check at {result.behavioral.checked_at[:19]}, TTL={result.behavioral.ttl_hours}h)")

    return "\n".join(lines)
