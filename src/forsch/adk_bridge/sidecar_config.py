"""Theme and copy knobs for the ADK Gradio sidecar.

Keep branding here so the sidecar can become a reusable template without
spelunking through callback code. Values are boring strings on purpose: easy to
patch, easy to fork.
"""

from __future__ import annotations

BRAND = {
    "title": "ADK Sidecar",
    "subtitle": "Focused operator chat for the agent graph. Pick an agent, run a task, inspect the tool trace.",
    "surface": "gradio sidecar",
    "agent_note": "Use this as the fast interaction layer. Durable config stays in the graph/control plane.",
    "prompt_placeholder": "Ask the selected agent to run a focused check, explain itself, or draft an eval...",
    "default_agent": "ops",
}

THEME = {
    "bg": "#f7f3ea",
    "panel": "#fffdf7",
    "ink": "#241f1a",
    "muted": "#6d655d",
    "line": "#ded6c8",
    "accent": "#8a5f2d",
    "accent_soft": "#efe2cf",
    "ok": "#287a55",
    "shadow": "rgba(36, 31, 26, 0.08)",
    "max_width": "1180px",
    "radius": "20px",
}

PROMPTS = {
    "Health check": "Run your smallest useful health check. Tell me what passed, what failed, and the next safe move.",
    "Explain this agent": "Explain what this agent is responsible for, what tools it has, and where the risky assumptions are.",
    "Runbook": "Give me a short operator runbook for this agent: normal path, failure signals, and recovery steps.",
    "Eval idea": "Propose three small eval cases for this agent. Keep them concrete and easy to automate.",
}


def build_css() -> str:
    t = THEME
    return f"""
:root {{
  --ff-bg: {t['bg']};
  --ff-panel: {t['panel']};
  --ff-ink: {t['ink']};
  --ff-muted: {t['muted']};
  --ff-line: {t['line']};
  --ff-accent: {t['accent']};
  --ff-accent-soft: {t['accent_soft']};
  --ff-ok: {t['ok']};
  --ff-shadow: {t['shadow']};
  --ff-max-width: {t['max_width']};
  --ff-radius: {t['radius']};
}}
.gradio-container {{
  max-width: none !important;
  min-height: 100vh;
  background:
    radial-gradient(circle at 20% 0%, color-mix(in srgb, var(--ff-accent) 14%, transparent), transparent 28rem),
    var(--ff-bg) !important;
  color: var(--ff-ink);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}}
#ff-sidecar {{ max-width: var(--ff-max-width); margin: 0 auto; padding: 22px; }}
#ff-hero {{
  border: 1px solid var(--ff-line); border-radius: calc(var(--ff-radius) + 2px);
  padding: 18px 20px; background: color-mix(in srgb, var(--ff-panel) 88%, transparent);
  box-shadow: 0 18px 60px var(--ff-shadow);
}}
#ff-hero h1 {{ margin: 0; font-size: 28px; line-height: 32px; letter-spacing: -0.04em; }}
#ff-hero p {{ margin: 6px 0 0; color: var(--ff-muted); font-size: 15px; }}
.ff-status-row {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; }}
.ff-chip {{
  display: inline-flex; align-items: center; gap: 7px; border: 1px solid var(--ff-line);
  border-radius: 999px; padding: 6px 10px; background: color-mix(in srgb, var(--ff-panel) 80%, var(--ff-accent-soft));
  color: var(--ff-muted); font-size: 13px; line-height: 16px;
}}
.ff-dot {{ width: 7px; height: 7px; border-radius: 50%; background: var(--ff-ok); }}
#ff-workspace {{ margin-top: 14px; align-items: stretch; }}
#ff-rail, #ff-compose-card, #ff-chat-card, #ff-trace-card {{
  border: 1px solid var(--ff-line); border-radius: var(--ff-radius);
  background: color-mix(in srgb, var(--ff-panel) 92%, transparent);
  box-shadow: 0 12px 38px color-mix(in srgb, var(--ff-shadow) 75%, transparent);
}}
#ff-rail, #ff-compose-card, #ff-trace-card {{ padding: 14px; }}
#ff-rail .wrap {{ gap: 12px; }}
#ff-chat-card {{ padding: 8px 12px 12px; }}
.ff-section-title {{
  font-size: 12px; line-height: 16px; letter-spacing: 0.12em; text-transform: uppercase;
  color: var(--ff-muted); font-weight: 700; margin-bottom: 8px;
}}
.ff-note {{ color: var(--ff-muted); font-size: 13px; line-height: 18px; }}
#ff-quick .secondary, #ff-quick button {{ border-radius: 14px !important; justify-content: flex-start !important; min-height: 36px !important; }}
#ff-run-btn button {{ background: var(--ff-ink) !important; color: white !important; border-color: var(--ff-ink) !important; }}
#ff-stop-btn button {{ border-color: #c6534a !important; color: #c6534a !important; }}
#ff-chatbot {{ border: 0 !important; background: transparent !important; }}
#ff-chatbot .message {{ border-radius: 16px !important; }}
#ff-chatbot .bot, #ff-chatbot .assistant {{ background: color-mix(in srgb, var(--ff-panel) 82%, var(--ff-accent-soft)) !important; }}
#ff-chatbot .user {{ background: var(--ff-accent-soft) !important; }}
textarea, input, select {{ border-radius: 14px !important; }}
#ff-prompt textarea {{ min-height: 128px !important; font-size: 15px !important; line-height: 21px !important; }}
#ff-tool-trace textarea {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace !important; font-size: 12px !important; }}
@media (max-width: 760px) {{
  #ff-sidecar {{ padding: 12px; }}
  #ff-workspace {{ flex-direction: column !important; }}
  #ff-chatbot {{ height: 60vh !important; }}
}}
footer {{ display: none !important; }}
"""
ENTER_TO_SEND_JS = """
() => {
  function bindEnterToSend() {
    const prompt = document.querySelector('#ff-prompt textarea');
    const run = document.querySelector('#ff-run-btn button');
    if (!prompt || !run || prompt.dataset.ffEnterBound === '1') return;
    prompt.dataset.ffEnterBound = '1';
    prompt.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return;
      event.preventDefault();
      run.click();
    });
  }
  const observer = new MutationObserver(bindEnterToSend);
  observer.observe(document.body, { childList: true, subtree: true });
  document.addEventListener('DOMContentLoaded', bindEnterToSend);
  bindEnterToSend();
}
"""
