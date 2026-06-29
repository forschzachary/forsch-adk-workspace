"""Forsch Tool Palette — a click-to-add tool selector mounted onto ADK Web.

ADK's "Add New Tool" dialog is a bare text field (type the fully-qualified function
name). This mounts a branded, searchable card grid of the Forsch tools beside it at
`/forsch`: pick a target agent, click a tool card, and it's written straight into that
agent's `web_agents/<id>/root_agent.yaml`. Reload the ADK builder to see it; `promote`
folds it back to the manifest.

The catalog is introspected live from `forsch.adk_components.tools` (name, family from
the submodule, one-line docstring, args), so it never drifts. The write-back is a
surgical text insert under the `tools:` block — it preserves the factory's formatting
(literal instruction block, key order) rather than reparsing the whole file.
"""
import inspect
from pathlib import Path

# submodule -> (display family, hue token used by the page CSS)
_FAMILY = {
    "household": ("Household", "green"),
    "email_groceries": ("Groceries · email", "green"),
    "stability_tools": ("Stability · host", "amber"),
    "ops_tools": ("Ops", "amber"),
    "crm_tools": ("CRM", "blue"),
    "wow_tools": ("WoW guild", "violet"),
}
_READ_PREFIXES = ("get_", "list_", "search_", "check_", "validate_", "is_")


def build_catalog() -> list[dict]:
    """Introspect forsch.adk_components.tools into card data (functions only)."""
    import forsch.adk_components.tools as tools

    out: list[dict] = []
    for name in sorted(dir(tools)):
        if name.startswith("_"):
            continue
        fn = getattr(tools, name)
        if not (inspect.isfunction(fn) and getattr(fn, "__module__", "").startswith("forsch")):
            continue  # skips the helper classes (AuthsomeHTTPClient, FrappeClient, ...)
        module = fn.__module__.rsplit(".", 1)[-1]
        family, hue = _FAMILY.get(module, (module, "amber"))
        doc = (inspect.getdoc(fn) or "").strip().split("\n", 1)[0]
        try:
            args = list(inspect.signature(fn).parameters)
        except (TypeError, ValueError):
            args = []
        out.append(
            {
                "name": name,
                "fq": f"forsch.adk_components.tools.{name}",
                "family": family,
                "hue": hue,
                "desc": doc,
                "args": args,
                "kind": "read" if name.startswith(_READ_PREFIXES) else "write",
            }
        )
    return out


def _agent_yaml(web_agents: Path, agent_id: str) -> Path:
    # guard against path traversal — agent_id is a single directory name
    if "/" in agent_id or ".." in agent_id:
        raise ValueError("bad agent id")
    return web_agents / agent_id / "root_agent.yaml"


def _current_tool_fqs(path: Path) -> list[str]:
    if not path.is_file():
        return []
    fqs = []
    for line in path.read_text().splitlines():
        s = line.strip()
        if s.startswith("- name:"):
            fqs.append(s.split("- name:", 1)[1].strip())
    return fqs


def add_tool(path: Path, fq: str) -> str:
    """Surgically insert `- name: <fq>` under the `tools:` block. Returns added|exists."""
    text = path.read_text()
    lines = text.split("\n")
    if any(line.strip() == f"- name: {fq}" for line in lines):
        return "exists"

    out: list[str] = []
    i, inserted = 0, False
    while i < len(lines):
        line = lines[i]
        out.append(line)
        if not inserted and line.rstrip() == "tools:":
            j = i + 1
            while j < len(lines) and lines[j].startswith("  - name:"):
                out.append(lines[j])
                j += 1
            out.append(f"  - name: {fq}")
            inserted = True
            i = j
            continue
        i += 1
    if not inserted:  # no tools: block yet
        if out and out[-1].strip() == "":
            out.pop()
        out += ["tools:", f"  - name: {fq}"]
    path.write_text("\n".join(out))
    return "added"


def mount_palette(app, workspace_root) -> None:
    """Mount the palette page + API onto an existing FastAPI app under /forsch."""
    from fastapi.responses import HTMLResponse, JSONResponse
    from pydantic import BaseModel

    class _AddBody(BaseModel):
        fq: str

    web_agents = Path(workspace_root) / "web_agents"
    catalog = build_catalog()
    valid_fqs = {c["fq"] for c in catalog}

    @app.get("/forsch", response_class=HTMLResponse)
    def _page() -> HTMLResponse:  # noqa: D401
        return HTMLResponse(PALETTE_HTML)

    @app.get("/forsch/api/tools")
    def _tools() -> JSONResponse:
        return JSONResponse(catalog)

    @app.get("/forsch/api/agents")
    def _agents() -> JSONResponse:
        names = [
            d.name
            for d in sorted(web_agents.iterdir())
            if (d / "root_agent.yaml").is_file()
        ]
        return JSONResponse(names)

    @app.get("/forsch/api/agents/{agent_id}/tools")
    def _agent_tools(agent_id: str) -> JSONResponse:
        return JSONResponse(_current_tool_fqs(_agent_yaml(web_agents, agent_id)))

    @app.post("/forsch/api/agents/{agent_id}/tools")
    def _add(agent_id: str, body: _AddBody) -> JSONResponse:
        fq = body.fq
        if fq not in valid_fqs:
            return JSONResponse({"error": f"unknown tool: {fq}"}, status_code=400)
        path = _agent_yaml(web_agents, agent_id)
        if not path.is_file():
            return JSONResponse({"error": f"no such agent: {agent_id}"}, status_code=404)
        status = add_tool(path, fq)
        return JSONResponse({"status": status, "tools": _current_tool_fqs(path)})


PALETTE_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Forsch · Tool Palette</title>
<style>
  :root {
    --bg: oklch(0.17 0.012 65);
    --surface: oklch(0.205 0.014 65);
    --surface-2: oklch(0.255 0.017 65);
    --line: oklch(0.32 0.013 65);
    --text: oklch(0.94 0.006 75);
    --muted: oklch(0.66 0.013 75);
    --accent: oklch(0.81 0.14 73);
    --accent-ink: oklch(0.20 0.04 73);
    --green: oklch(0.78 0.13 150);
    --amber: oklch(0.82 0.14 73);
    --blue: oklch(0.74 0.12 245);
    --violet: oklch(0.75 0.13 300);
    --mono: ui-monospace, "SF Mono", "JetBrains Mono", Menlo, monospace;
    --sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    --r: 0.625rem;
    --ease: cubic-bezier(0.22, 1, 0.36, 1);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text); font-family: var(--sans);
    -webkit-font-smoothing: antialiased; line-height: 1.45;
  }
  header {
    position: sticky; top: 0; z-index: 5; backdrop-filter: blur(8px);
    background: color-mix(in oklch, var(--bg) 86%, transparent);
    border-bottom: 1px solid var(--line);
    display: flex; align-items: center; gap: 1.25rem; flex-wrap: wrap;
    padding: 0.9rem clamp(1rem, 4vw, 2.25rem);
  }
  .brand { font-weight: 680; letter-spacing: -0.01em; font-size: 1.02rem; }
  .brand b { color: var(--accent); font-weight: 680; }
  .brand small { display: block; color: var(--muted); font-weight: 450; font-size: 0.74rem; letter-spacing: 0.02em; }
  .controls { display: flex; gap: 0.6rem; margin-left: auto; flex-wrap: wrap; align-items: center; }
  .field { position: relative; }
  .field label { position: absolute; left: 0.7rem; top: -0.5rem; font-size: 0.62rem; color: var(--muted);
    background: var(--bg); padding: 0 0.3rem; letter-spacing: 0.04em; text-transform: uppercase; }
  select, input {
    font: inherit; font-size: 0.86rem; color: var(--text); background: var(--surface);
    border: 1px solid var(--line); border-radius: var(--r); padding: 0.5rem 0.75rem;
    outline: none; transition: border-color 0.15s var(--ease);
  }
  select:focus, input:focus { border-color: var(--accent); }
  input { min-width: 15rem; }
  main { padding: clamp(1rem, 4vw, 2.25rem); max-width: 1180px; margin: 0 auto; }
  .hint { color: var(--muted); font-size: 0.84rem; margin: 0 0 1.5rem; }
  .hint b { color: var(--text); font-weight: 600; }
  .family { margin-bottom: 2rem; }
  .family h2 {
    display: flex; align-items: center; gap: 0.55rem; font-size: 0.78rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin: 0 0 0.85rem;
  }
  .dot { width: 0.55rem; height: 0.55rem; border-radius: 50%; background: var(--hue, var(--accent)); }
  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(15.5rem, 1fr)); gap: 0.7rem; }
  .card {
    text-align: left; font: inherit; color: inherit; cursor: pointer;
    background: var(--surface); border: 1px solid var(--line); border-radius: var(--r);
    padding: 0.85rem 0.95rem; display: flex; flex-direction: column; gap: 0.4rem;
    transition: transform 0.18s var(--ease), border-color 0.18s var(--ease), background 0.18s var(--ease);
  }
  .card:hover { transform: translateY(-2px); border-color: var(--hue, var(--accent)); background: var(--surface-2); }
  .card:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .card .top { display: flex; align-items: baseline; justify-content: space-between; gap: 0.5rem; }
  .card .name { font-family: var(--mono); font-size: 0.9rem; font-weight: 600; letter-spacing: -0.01em; }
  .card .kind { font-size: 0.62rem; letter-spacing: 0.05em; text-transform: uppercase; color: var(--muted);
    border: 1px solid var(--line); border-radius: 0.35rem; padding: 0.05rem 0.4rem; white-space: nowrap; }
  .card .kind.write { color: var(--amber); border-color: color-mix(in oklch, var(--amber) 45%, var(--line)); }
  .card .desc { font-size: 0.82rem; color: var(--muted); }
  .card .args { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-top: auto; padding-top: 0.2rem; }
  .args code { font-family: var(--mono); font-size: 0.68rem; color: var(--text);
    background: color-mix(in oklch, var(--bg) 60%, var(--surface)); border-radius: 0.3rem; padding: 0.08rem 0.36rem; }
  .card.added { cursor: default; }
  .card.added:hover { transform: none; }
  .card.added .add { color: var(--green); border-color: color-mix(in oklch, var(--green) 50%, var(--line)); }
  .card .add { align-self: flex-start; margin-top: 0.15rem; font-size: 0.7rem; font-weight: 600; letter-spacing: 0.03em;
    color: var(--accent); border: 1px solid color-mix(in oklch, var(--accent) 40%, var(--line));
    border-radius: 0.4rem; padding: 0.18rem 0.5rem; }
  .empty { color: var(--muted); font-size: 0.86rem; padding: 2rem 0; }
  #toast {
    position: fixed; bottom: 1.4rem; left: 50%; transform: translate(-50%, 1.5rem);
    background: var(--accent); color: var(--accent-ink); font-weight: 600; font-size: 0.84rem;
    padding: 0.6rem 1rem; border-radius: var(--r); opacity: 0; pointer-events: none;
    transition: opacity 0.2s var(--ease), transform 0.32s var(--ease); box-shadow: 0 8px 30px oklch(0 0 0 / 0.4);
  }
  #toast.show { opacity: 1; transform: translate(-50%, 0); }
</style>
</head>
<body>
<header>
  <div class="brand"><b>Forsch</b> Tool Palette<small>click a tool to add it to the selected agent</small></div>
  <div class="controls">
    <div class="field"><label>Agent</label><select id="agent"></select></div>
    <input id="search" type="search" placeholder="Search tools…" autocomplete="off" />
  </div>
</header>
<main>
  <p class="hint">Adds the tool to <b id="agentName">…</b>'s <code>root_agent.yaml</code>. Reload the ADK builder to see it, then <b>promote</b> to fold it into the manifest.</p>
  <div id="grid"></div>
</main>
<div id="toast"></div>
<script>
const HUE = { green: "var(--green)", amber: "var(--amber)", blue: "var(--blue)", violet: "var(--violet)" };
let TOOLS = [], AGENT = "", ADDED = new Set();
const $ = (s) => document.querySelector(s);

async function boot() {
  TOOLS = await (await fetch("/forsch/api/tools")).json();
  const agents = await (await fetch("/forsch/api/agents")).json();
  const sel = $("#agent");
  sel.innerHTML = agents.map((a) => `<option>${a}</option>`).join("");
  AGENT = agents[0] || "";
  sel.onchange = async () => { AGENT = sel.value; await loadAgent(); render(); };
  $("#search").oninput = render;
  await loadAgent();
  render();
}

async function loadAgent() {
  $("#agentName").textContent = AGENT || "—";
  if (!AGENT) { ADDED = new Set(); return; }
  ADDED = new Set(await (await fetch(`/forsch/api/agents/${AGENT}/tools`)).json());
}

function render() {
  const q = $("#search").value.trim().toLowerCase();
  const hit = TOOLS.filter((t) =>
    !q || t.name.toLowerCase().includes(q) || t.desc.toLowerCase().includes(q) || t.family.toLowerCase().includes(q)
  );
  const fams = [...new Set(hit.map((t) => t.family))];
  const grid = $("#grid");
  if (!hit.length) { grid.innerHTML = `<p class="empty">No tools match "${q}".</p>`; return; }
  grid.innerHTML = fams.map((fam) => {
    const items = hit.filter((t) => t.family === fam);
    const hue = HUE[items[0].hue] || "var(--accent)";
    return `<section class="family" style="--hue:${hue}">
      <h2><span class="dot"></span>${fam}</h2>
      <div class="cards">${items.map(card).join("")}</div>
    </section>`;
  }).join("");
  grid.querySelectorAll(".card:not(.added)").forEach((el) => {
    el.onclick = () => addTool(el.dataset.fq);
  });
}

function card(t) {
  const added = ADDED.has(t.fq);
  const args = t.args.slice(0, 5).map((a) => `<code>${a}</code>`).join("");
  return `<button class="card ${added ? "added" : ""}" data-fq="${t.fq}" ${added ? "disabled" : ""}>
    <div class="top"><span class="name">${t.name}</span><span class="kind ${t.kind}">${t.kind}</span></div>
    <div class="desc">${t.desc || ""}</div>
    ${args ? `<div class="args">${args}</div>` : ""}
    <span class="add">${added ? "✓ in " + AGENT : "+ add"}</span>
  </button>`;
}

async function addTool(fq) {
  if (!AGENT) return;
  const r = await fetch(`/forsch/api/agents/${AGENT}/tools`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ fq }),
  });
  const data = await r.json();
  if (!r.ok) { toast(data.error || "failed", true); return; }
  ADDED = new Set(data.tools);
  render();
  toast(data.status === "exists" ? "already on " + AGENT : "added to " + AGENT);
}

let toastT;
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg; el.classList.add("show");
  clearTimeout(toastT); toastT = setTimeout(() => el.classList.remove("show"), 1800);
}
boot();
</script>
</body>
</html>
"""
