#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Render diagram.json to Mermaid .md files.
Reads the intermediate JSON from docs/diagram.json, outputs:
  - architecture.md  (layered dependency graph)
  - flowchart.md     (main.py execution sequence)
  - data_flow.md     (inter-module data flow)

Also supports --format png via mermaid.ink API (zero local deps).
Also supports --format png-local via mermaid-cli (requires Node.js).

Usage:
  python render_diagram_local.py --input docs/diagram.json --output docs/
  python render_diagram_local.py --input docs/diagram.json --output docs/ --format png
  python render_diagram_local.py --input docs/diagram.json --output docs/ --format png-local

Defensive: every field access uses .get() with fallbacks.
Missing or malformed sections are skipped with a stderr warning, never crash.
"""

import argparse
import hashlib
import json
import os
import sys


def safe_get(d, key, default=None):
    """Get key from dict, never raise."""
    try:
        return d.get(key, default)
    except Exception:
        return default


def safe_list(d, key):
    """Get list from dict, always returns a list."""
    try:
        val = d.get(key, [])
        return val if isinstance(val, list) else []
    except Exception:
        return []


def safe_int(d, key, default=0):
    """Get int from dict, returns default on failure."""
    try:
        return int(d.get(key, default))
    except Exception:
        return default


def load_diagram_json(path):
    """Load diagram.json. Returns (data, error)."""
    if not os.path.isfile(path):
        return None, "diagram.json not found: {}".format(path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except json.JSONDecodeError as e:
        return None, "JSON parse error: {}".format(e)
    except Exception as e:
        return None, "read error: {}".format(e)


# ═══════════════════════════════════════════════════════════
#  Layer colours (mermaid-compatible)
# ═══════════════════════════════════════════════════════════

LAYER_STYLES = {
    "entry":  {"fill": "#FFF3E0", "stroke": "#E65100"},
    "task":   {"fill": "#E8F5E9", "stroke": "#2E7D32"},
    "driver": {"fill": "#E3F2FD", "stroke": "#1565C0"},
    "lib":    {"fill": "#F3E5F5", "stroke": "#7B1FA2"},
    "board":  {"fill": "#ECEFF1", "stroke": "#546E7A"},
    "host":   {"fill": "#FFF8E1", "stroke": "#F9A825"},
    "test":   {"fill": "#FBE9E7", "stroke": "#D84315"},
}

safe_mermaid_chars = str.maketrans({'"': "'", "<": "[", ">": "]", "{": "(", "}": ")", "(": "（", ")": "）", ";": "；", "[": "【", "]": "】", "@": "at", "#": "no."})


def mermaid_escape(text):
    """Escape special characters for Mermaid node labels."""
    if not text:
        return ""
    try:
        return str(text).translate(safe_mermaid_chars).replace("\n", " ")
    except Exception:
        return str(text)


def mermaid_edge_label(text, limit=64):
    """Normalize an edge label so mermaid.ink accepts it reliably."""
    if not text:
        return ""
    try:
        cleaned = mermaid_escape(str(text).replace("@", " at "))
        for old, new in (
            ("|", " "),
            ("/", " per "),
            ("\\", " "),
            ("==", " equals "),
            ("=", " equals "),
            ("(", "（"),
            (")", "）"),
        ):
            cleaned = cleaned.replace(old, new)
        cleaned = " ".join(cleaned.split())
        if limit and len(cleaned) > limit:
            cleaned = cleaned[:max(0, limit - 3)].rstrip() + "..."
        return cleaned
    except Exception:
        return mermaid_escape(text)


# ═══════════════════════════════════════════════════════════
#  architecture.md
# ═══════════════════════════════════════════════════════════

def render_architecture(diagram, output_dir):
    """Generate architecture.md with layered Mermaid graph. Returns (filepath, warnings)."""
    warnings = []
    try:
        mermaid_code = _build_architecture_mermaid(diagram)
        if not mermaid_code:
            return None, ["no architecture.layers found"]

        lines = []
        meta = safe_get(diagram, "meta", {})
        project = safe_get(meta, "project", "Unknown Project")
        mode = safe_get(meta, "mode", "timer")

        lines.append("# {} — 软件架构图".format(project))
        lines.append("")
        lines.append("> 调度模式: **{}** | 生成时间: {}".format(
            mode, safe_get(meta, "generated_at", "N/A")))
        lines.append("")
        lines.append("```mermaid")
        lines.append(mermaid_code)
        lines.append("```")
        lines.append("")

        # Diagnostics section
        diag = safe_get(diagram, "diagnostics", {})
        if diag:
            lines.append("## 代码诊断")
            lines.append("")
            try:
                lines.append("- 总模块数: {}".format(safe_int(diag, "total_modules")))
                lines.append("- 总依赖数: {}".format(safe_int(diag, "total_dependencies")))
                lines.append("- 依赖最大深度: {}".format(safe_int(diag, "max_depth")))
            except Exception:
                pass
            circ = safe_list(diag, "circular_deps")
            if circ:
                lines.append("- ⚠️ 循环依赖: {}".format(circ))
            orphans = safe_list(diag, "orphan_modules")
            if orphans:
                lines.append("- 孤立模块: {}".format(", ".join(str(o) for o in orphans)))
            machine_access = safe_list(diag, "machine_direct_access")
            if machine_access:
                lines.append("- ⚠️ 直接 import machine: {}".format(
                    ", ".join(str(m) for m in machine_access)))

        out_path = os.path.join(output_dir, "architecture.md")
        os.makedirs(output_dir, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        return out_path, warnings
    except Exception as e:
        return None, ["architecture render exception: {}".format(e)]


# ═══════════════════════════════════════════════════════════
#  flowchart.md
# ═══════════════════════════════════════════════════════════

PHASE_COLORS = {
    "boot":     "#ECEFF1",
    "init":     "#E8F5E9",
    "scan":     "#E3F2FD",
    "create":   "#FFF3E0",
    "assembly": "#F3E5F5",
    "run":      "#E8F5E9",
    "shutdown": "#FFEBEE",
}


def render_flowchart(diagram, output_dir):
    """Generate flowchart.md with Mermaid sequence diagram. Returns (filepath, warnings)."""
    warnings = []
    try:
        mermaid_code = _build_flowchart_mermaid(diagram)
        if not mermaid_code:
            return None, ["no flow[] data found"]

        lines = []
        meta = safe_get(diagram, "meta", {})
        project = safe_get(meta, "project", "Unknown Project")

        lines.append("# {} — 执行流程图".format(project))
        lines.append("")
        lines.append("```mermaid")
        lines.append(mermaid_code)
        lines.append("```")
        lines.append("")

        out_path = os.path.join(output_dir, "flowchart.md")
        os.makedirs(output_dir, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        return out_path, warnings
    except Exception as e:
        return None, ["flowchart render exception: {}".format(e)]


# ═══════════════════════════════════════════════════════════
#  data_flow.md
# ═══════════════════════════════════════════════════════════

CHANNEL_ARROWS = {
    "function_return": "==>",
    "shared_dict":    "-->",
    "global_var":     "-->",
    "queue":          "-->>",
    "callback_param": "-.->",
}


def render_data_flow(diagram, output_dir):
    """Generate data_flow.md with Mermaid data flow graph. Returns (filepath, warnings)."""
    warnings = []
    try:
        mermaid_code = _build_data_flow_mermaid(diagram)
        if not mermaid_code:
            return None, ["no data_flow[] data found"]

        lines = []
        meta = safe_get(diagram, "meta", {})
        project = safe_get(meta, "project", "Unknown Project")

        lines.append("# {} — 数据流图".format(project))
        lines.append("")
        lines.append("```mermaid")
        lines.append(mermaid_code)
        lines.append("```")
        lines.append("")

        out_path = os.path.join(output_dir, "data_flow.md")
        os.makedirs(output_dir, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        return out_path, warnings
    except Exception as e:
        return None, ["data_flow render exception: {}".format(e)]


# ═══════════════════════════════════════════════════════════
#  PNG via mermaid.ink (zero local deps)
# ═══════════════════════════════════════════════════════════

def render_mermaid_image(mermaid_code, output_path, fmt="svg"):
    """Convert Mermaid code to SVG/PNG via mermaid.ink API. Returns (path, error).

    fmt: "svg" (vector, sharp at any scale) or "png" (raster, may be blurry).
    SVG is the default — produces crisp, scalable output.
    Uses GET /svg/<base64> for SVG, /img/<base64> for PNG.

    SVG output is post-processed to inject CJK-compatible fonts (Microsoft YaHei,
    PingFang SC, Noto Sans SC) so Chinese/Japanese/Korean labels render correctly.
    """
    import base64
    import urllib.request

    try:
        encoded = base64.urlsafe_b64encode(mermaid_code.encode("utf-8")).decode("ascii")
        if fmt == "svg":
            url = "https://mermaid.ink/svg/{}".format(encoded)
        else:
            url = "https://mermaid.ink/img/{}?type={}".format(encoded, fmt)
        req = urllib.request.Request(url, headers={"User-Agent": "upy-diagram/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()

        # Inject CJK font-family into SVG <style> block for Chinese text rendering
        if fmt == "svg":
            try:
                svg_text = data.decode("utf-8")
                svg_text = svg_text.replace(
                    'font-family:"trebuchet ms",verdana,arial,sans-serif',
                    'font-family:"Microsoft YaHei","PingFang SC","Noto Sans SC","trebuchet ms",verdana,arial,sans-serif'
                )
                data = svg_text.encode("utf-8")
            except Exception:
                pass  # If post-processing fails, use original data

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(data)
        return output_path, None
    except Exception as e:
        return None, "mermaid.ink render failed: {}".format(e)


def render_all_to_svg(diagram, output_dir, fmt="svg"):
    """Render all diagram types to SVG (or PNG). Returns (paths_dict, warnings)."""
    warnings = []
    results = {}
    ext = fmt  # svg or png

    # Architecture (light mode: strip styles + badges for mermaid.ink URL limit)
    arch = safe_get(diagram, "architecture", {})
    if arch:
        try:
            mermaid_code = _build_architecture_mermaid(diagram, light=True)
            if mermaid_code:
                out = os.path.join(output_dir, "architecture.{}".format(ext))
                path, err = render_mermaid_image(mermaid_code, out, fmt=fmt)
                if path:
                    results["architecture_" + ext] = path
                if err:
                    warnings.append(err)
        except Exception as e:
            warnings.append("architecture {}: {}".format(ext, e))

    # Flowchart
    flow = safe_list(diagram, "flow")
    if flow:
        try:
            mermaid_code = _build_flowchart_mermaid(diagram)
            if mermaid_code:
                out = os.path.join(output_dir, "flowchart.{}".format(ext))
                path, err = render_mermaid_image(mermaid_code, out, fmt=fmt)
                if path:
                    results["flowchart_" + ext] = path
                if err:
                    warnings.append(err)
        except Exception as e:
            warnings.append("flowchart {}: {}".format(ext, e))

    # Data flow
    data_flows = safe_list(diagram, "data_flow")
    if data_flows:
        try:
            mermaid_code = _build_data_flow_mermaid(diagram)
            if mermaid_code:
                out = os.path.join(output_dir, "data_flow.{}".format(ext))
                path, err = render_mermaid_image(mermaid_code, out, fmt=fmt)
                if path:
                    results["data_flow_" + ext] = path
                if err:
                    warnings.append(err)
        except Exception as e:
            warnings.append("data_flow {}: {}".format(ext, e))

    return results, warnings


def _build_architecture_mermaid(diagram, light=False):
    """Build Mermaid graph TB string for architecture. Returns str or None.

    light=True strips subgraph style directives and node badges to produce a
    smaller Mermaid payload that fits within mermaid.ink's GET URL length limit
    (~7000 chars). Use light=True for SVG/PNG rendering, light=False for .md.
    """
    try:
        arch = safe_get(diagram, "architecture", {})
        layers = safe_list(arch, "layers")
        if not layers:
            return None

        lines = ["graph TB"]
        module_ids = {}

        for layer in layers:
            if not isinstance(layer, dict):
                continue
            lid = safe_get(layer, "id", "?")
            llabel = safe_get(layer, "label", lid)
            style_cfg = LAYER_STYLES.get(lid, LAYER_STYLES["board"])

            lines.append("  subgraph {id}[{label}]".format(id=lid, label=mermaid_escape(llabel)))
            if not light:
                lines.append("    style {id} fill:{fill},stroke:{stroke},color:#333".format(
                    id=lid, fill=style_cfg["fill"], stroke=style_cfg["stroke"]))

            for mod in safe_list(layer, "modules"):
                if not isinstance(mod, dict):
                    continue
                mname = safe_get(mod, "name", "unknown")
                node_id = "m_" + mname.replace(".", "_").replace("-", "_").replace("/", "_")
                mrole = safe_get(mod, "role", "")

                label_parts = [mermaid_escape(mname.split(".")[-1])]
                if mrole:
                    label_parts.append("<br/>{}".format(mermaid_escape(mrole)))

                if not light:
                    depends_machine = safe_get(mod, "depends_on_machine", False)
                    has_mock = safe_get(mod, "has_mock", False)
                    is_generated = safe_get(mod, "is_generated", False)
                    source = safe_get(mod, "source", "")
                    badges = []
                    if depends_machine:
                        badges.append("⚡machine")
                    if has_mock:
                        badges.append("🧪mock")
                    if is_generated:
                        badges.append("🤖gen")
                    if source and source not in ("llm_generated", "scaffold_template"):
                        badges.append(source)
                    if badges:
                        label_parts.append("<br/><i>{}</i>".format(
                            mermaid_escape(" ".join(badges))))

                label = "".join(label_parts)
                lines.append('    {}["{}"]'.format(node_id, label))
                module_ids[mname] = node_id

            lines.append("  end")
            lines.append("")

        # Cross-layer dependencies
        cross_deps = safe_list(arch, "cross_layer_deps")
        dep_lines_added = 0
        for dep in cross_deps:
            if not isinstance(dep, dict):
                continue
            _from = safe_get(dep, "from", "")
            _to = safe_get(dep, "to", "")
            _label = safe_get(dep, "label", "")
            _style = safe_get(dep, "style", "solid")

            from_id = module_ids.get(_from, "m_" + _from.replace(".", "_"))
            to_id = module_ids.get(_to, "m_" + _to.replace(".", "_"))

            arrow = " --> "
            if _style == "dashed":
                arrow = " -.-> "
            elif _style == "dotted":
                arrow = " -.-> "

            if _label:
                arrow_base = arrow.strip()
                arrow_mid = "|{}|".format(mermaid_escape(_label))
                lines.append("  {} {}{} {}".format(from_id, arrow_base, arrow_mid, to_id))
            else:
                lines.append("  {}{}{}".format(from_id, arrow, to_id))
            dep_lines_added += 1

        # Fallback: module-level depends_on
        if dep_lines_added == 0:
            for layer in layers:
                if not isinstance(layer, dict):
                    continue
                for mod in safe_list(layer, "modules"):
                    if not isinstance(mod, dict):
                        continue
                    mname = safe_get(mod, "name", "")
                    node_id = module_ids.get(mname, mname.replace(".", "_"))
                    for dep in safe_list(mod, "depends_on"):
                        if not isinstance(dep, str):
                            continue
                        dep_id = module_ids.get(dep, "m_" + dep.replace(".", "_"))
                        lines.append("  {} --> {}".format(node_id, dep_id))

        return "\n".join(lines)
    except Exception:
        return None


def _build_flowchart_mermaid(diagram):
    """Build Mermaid sequenceDiagram string. Returns str or None."""
    try:
        lines = ["sequenceDiagram", "  autonumber", "  participant D as Device(MCU)"]
        current_phase = None
        for step in safe_list(diagram, "flow"):
            if not isinstance(step, dict):
                continue
            _seq = safe_int(step, "seq", 0)
            _phase = safe_get(step, "phase", "init")
            _action = safe_get(step, "action", "Step {}".format(_seq))
            _detail = safe_get(step, "detail", "")
            _on_error = safe_get(step, "on_error", "")
            _is_conditional = safe_get(step, "is_conditional", False)
            branches = safe_list(step, "branches")

            if _phase != current_phase:
                current_phase = _phase
                phase_label = {
                    "boot": "── boot ──",
                    "init": "── init ──",
                    "scan": "── scan ──",
                    "create": "── create ──",
                    "assembly": "── assembly ──",
                    "run": "── run loop ──",
                    "shutdown": "── shutdown ──",
                }.get(_phase, "── {} ──".format(_phase))
                lines.append("  Note over D: {}".format(phase_label))

            action_text = mermaid_escape(_action)
            if _detail:
                action_text = "{}<br/>{}".format(
                    action_text, mermaid_escape(_detail))
            lines.append("  D->>D: {}".format(action_text))

            if _on_error:
                lines.append("  opt on_error={}".format(_on_error))
                lines.append("  Note right of D: On failure: {}".format(_on_error))
                lines.append("  end")

            if _is_conditional and branches:
                for br in branches:
                    if not isinstance(br, dict):
                        continue
                    cond = safe_get(br, "condition", "")
                    goto = safe_int(br, "goto_step", 0)
                    cond_text = mermaid_escape(cond)
                    lines.append(
                        "  alt {}".format(cond_text) if cond_text else "  alt branch")
                    lines.append("  Note right of D: → goto step {}".format(goto))
                    lines.append("  end")

        # Task registry
        task_reg = safe_list(diagram, "task_registry")
        if task_reg:
            lines.append("  Note over D: ── task registry ──")
            for tr in task_reg:
                if not isinstance(tr, dict):
                    continue
                tname = safe_get(tr, "name", "?")
                tcb = safe_get(tr, "callback", "?")
                tinterval = safe_int(tr, "interval_ms", 0)
                lines.append("  Note over D: Task '{}': {}() every {}ms".format(
                    mermaid_escape(tname), mermaid_escape(tcb), tinterval))

        return "\n".join(lines)
    except Exception:
        return None


def _build_data_flow_mermaid(diagram):
    """Build Mermaid graph LR string for data flow. Returns str or None."""
    try:
        lines = ["graph LR"]
        node_ids = {}
        counter = [0]

        def nid(name):
            c = "N{}".format(counter[0])
            counter[0] += 1
            node_ids[name] = c
            return c

        for df in safe_list(diagram, "data_flow"):
            if not isinstance(df, dict):
                continue
            try:
                _from = safe_get(df, "from", "?")
                _to = safe_get(df, "to", "?")
                _data = safe_get(df, "data", "?")
                _channel = safe_get(df, "channel", "shared_dict")
                _rate = safe_get(df, "rate", "")

                if _from not in node_ids:
                    fid = nid(_from)
                    lines.append('  {}["{}"]'.format(fid, mermaid_escape(_from)))
                else:
                    fid = node_ids[_from]
                if _to not in node_ids:
                    tid = nid(_to)
                    lines.append('  {}["{}"]'.format(tid, mermaid_escape(_to)))
                else:
                    tid = node_ids[_to]

                arrow = CHANNEL_ARROWS.get(_channel, "-->")
                edge_parts = []
                data_label = mermaid_edge_label(_data, 48)
                if data_label:
                    edge_parts.append(data_label)
                if _rate:
                    rate_label = mermaid_edge_label(_rate, 32)
                    if rate_label:
                        edge_parts.append("rate {}".format(rate_label))
                edge_label = mermaid_edge_label(" - ".join(edge_parts), 80) or "data"
                lines.append("  {} {}|{}| {}".format(fid, arrow, edge_label, tid))
            except Exception:
                continue

        return "\n".join(lines)
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════
#  HTML output — self-contained browser pages (Mermaid.js CDN)
# ═══════════════════════════════════════════════════════════

DIAGRAM_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  :root {{ --bg: #fff; --text: #333; --border: #e0e0e0; --code-bg: #f8f8f8; --tab-active: #1a73e8; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg: #1e1e1e; --text: #ddd; --border: #444; --code-bg: #2d2d2d; --tab-active: #5caeff; }} }}
  body {{ font-family: system-ui, -apple-system, sans-serif; max-width: 1400px; margin: 0 auto; padding: 20px; background: var(--bg); color: var(--text); }}
  h1 {{ font-size: 1.4em; margin-bottom: 4px; }}
  .meta {{ color: #888; font-size: 0.85em; margin-bottom: 16px; }}
  .tabs {{ display: flex; gap: 4px; margin-bottom: 16px; border-bottom: 2px solid var(--border); }}
  .tabs button {{ padding: 8px 20px; border: none; background: transparent; cursor: pointer; font-size: 14px; color: var(--text); border-bottom: 2px solid transparent; margin-bottom: -2px; }}
  .tabs button:hover {{ color: var(--tab-active); }}
  .tabs button.active {{ color: var(--tab-active); border-bottom-color: var(--tab-active); font-weight: 600; }}
  .panel {{ display: none; }}
  .panel.active {{ display: block; }}
  .source {{ background: var(--code-bg); border: 1px solid var(--border); border-radius: 8px; padding: 20px; overflow-x: auto; }}
  .source pre {{ margin: 0; white-space: pre-wrap; font-family: "Cascadia Code", "Fira Code", "JetBrains Mono", monospace; font-size: 13px; line-height: 1.5; }}
  .mermaid {{ text-align: center; padding: 20px 0; }}
  .mermaid svg {{ max-width: 100%; height: auto; }}
  #fallback {{ display: none; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="meta">Project: {project} | Mode: {mode} | Generated: {generated_at}</div>

<div class="tabs">
  <button class="active" onclick="switchTab('diagram')">{tab_diagram}</button>
  <button onclick="switchTab('source')">{tab_source}</button>
</div>

<div id="diagram" class="panel active">
  <div class="mermaid">
{MERMAID_CODE}
  </div>
  <div id="fallback" class="source">
    <p style="color:#f44336">Mermaid.js failed to load. Showing source code instead.</p>
    <pre>{MERMAID_ESCAPED}</pre>
  </div>
</div>

<div id="source" class="panel">
  <div class="source">
    <pre>{MERMAID_ESCAPED}</pre>
  </div>
</div>

<script>
function switchTab(id) {{
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tabs button').forEach(b => b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  event.target.classList.add('active');
}}
</script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>
  mermaid.initialize({{ startOnLoad: true, theme: 'default', securityLevel: 'loose' }});
  window.addEventListener('error', function(e) {{
    if (e.target && e.target.tagName === 'SCRIPT' && e.target.src.includes('mermaid')) {{
      document.getElementById('fallback').style.display = 'block';
    }}
  }}, true);
</script>
</body>
</html>"""


def _mermaid_html_escape(text):
    """Escape Mermaid code for safe embedding in HTML <pre>."""
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _render_one_html(mermaid_code, meta, title, output_path):
    """Render a single HTML file from Mermaid code. Returns (filepath, warnings)."""
    warnings = []
    try:
        project = safe_get(meta, "project", "Unknown Project")
        mode = safe_get(meta, "mode", "timer")
        generated_at = safe_get(meta, "generated_at", "N/A")

        html = DIAGRAM_HTML_TEMPLATE.format(
            title=title,
            project=project,
            mode=mode,
            generated_at=generated_at,
            tab_diagram="图表",
            tab_source="Mermaid 源码",
            MERMAID_CODE=mermaid_code,
            MERMAID_ESCAPED=_mermaid_html_escape(mermaid_code),
        )

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        return output_path, warnings
    except Exception as e:
        return None, ["HTML render exception: {}".format(e)]


def render_all_to_html(diagram, output_dir):
    """Render all diagram types to self-contained HTML pages. Returns (paths_dict, warnings)."""
    warnings = []
    results = {}
    meta = safe_get(diagram, "meta", {})
    project = safe_get(meta, "project", "Unknown Project")

    # Architecture
    arch = safe_get(diagram, "architecture", {})
    if arch:
        try:
            mermaid_code = _build_architecture_mermaid(diagram)
            if mermaid_code:
                out = os.path.join(output_dir, "architecture.html")
                path, err = _render_one_html(
                    mermaid_code, meta,
                    "{} — 软件架构图".format(project), out)
                if path:
                    results["architecture_html"] = path
                if err:
                    warnings.extend(err)
        except Exception as e:
            warnings.append("architecture HTML: {}".format(e))

    # Flowchart
    flow = safe_list(diagram, "flow")
    if flow:
        try:
            mermaid_code = _build_flowchart_mermaid(diagram)
            if mermaid_code:
                out = os.path.join(output_dir, "flowchart.html")
                path, err = _render_one_html(
                    mermaid_code, meta,
                    "{} — 执行流程图".format(project), out)
                if path:
                    results["flowchart_html"] = path
                if err:
                    warnings.extend(err)
        except Exception as e:
            warnings.append("flowchart HTML: {}".format(e))

    # Data flow
    data_flows = safe_list(diagram, "data_flow")
    if data_flows:
        try:
            mermaid_code = _build_data_flow_mermaid(diagram)
            if mermaid_code:
                out = os.path.join(output_dir, "data_flow.html")
                path, err = _render_one_html(
                    mermaid_code, meta,
                    "{} — 数据流图".format(project), out)
                if path:
                    results["data_flow_html"] = path
                if err:
                    warnings.extend(err)
        except Exception as e:
            warnings.append("data_flow HTML: {}".format(e))

    return results, warnings


# ═══════════════════════════════════════════════════════════
#  main
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Render diagram.json to Mermaid .md files")
    parser.add_argument("--input", required=True, help="Path to diagram.json")
    parser.add_argument("--output", required=True, help="Output directory (e.g. docs/)")
    parser.add_argument("--format", default="all",
                        choices=["md", "svg", "png", "html", "all"],
                        help="Output format: md (Mermaid text), svg (mermaid.ink vector), "
                             "png (mermaid.ink raster), html (self-contained browser pages), "
                             "all (md + svg + png + html)")
    parser.add_argument("--json-summary", action="store_true",
                        help="Print machine-readable JSON summary as the final stdout line")
    args = parser.parse_args()

    diagram, err = load_diagram_json(args.input)
    if err:
        print("[FAIL] {}".format(err), file=sys.stderr)
        sys.exit(1)

    all_warnings = []
    ok_count = 0
    generated_paths = []

    # ── Markdown outputs ──
    if args.format in ("md", "all"):
        for render_fn, name in [
            (render_architecture, "architecture.md"),
            (render_flowchart, "flowchart.md"),
            (render_data_flow, "data_flow.md"),
        ]:
            try:
                path, warns = render_fn(diagram, args.output)
                all_warnings.extend(warns)
                if path:
                    print("[OK] {}".format(path))
                    generated_paths.append(path)
                    ok_count += 1
            except Exception as e:
                all_warnings.append("{} render crashed: {}".format(name, e))
                print("[WARN] {} render crashed: {}".format(name, e), file=sys.stderr)

    # ── SVG / PNG outputs via mermaid.ink ──
    if args.format in ("svg", "all"):
        try:
            results, warns = render_all_to_svg(diagram, args.output, fmt="svg")
            all_warnings.extend(warns)
            for name, path in results.items():
                print("[OK] {}".format(path))
                generated_paths.append(path)
                ok_count += 1
        except Exception as e:
            all_warnings.append("svg render crashed: {}".format(e))
            print("[WARN] svg render crashed: {}".format(e), file=sys.stderr)

    # ── PNG outputs via mermaid.ink (raster, may be blurry) ──
    if args.format in ("png", "all"):
        try:
            results, warns = render_all_to_svg(diagram, args.output, fmt="png")
            all_warnings.extend(warns)
            for name, path in results.items():
                print("[OK] {}".format(path))
                generated_paths.append(path)
                ok_count += 1
        except Exception as e:
            all_warnings.append("png render crashed: {}".format(e))
            print("[WARN] png render crashed: {}".format(e), file=sys.stderr)

    # ── HTML outputs (self-contained browser pages) ──
    if args.format in ("html", "all"):
        try:
            results, warns = render_all_to_html(diagram, args.output)
            all_warnings.extend(warns)
            for name, path in results.items():
                print("[OK] {}".format(path))
                generated_paths.append(path)
                ok_count += 1
        except Exception as e:
            all_warnings.append("html render crashed: {}".format(e))
            print("[WARN] html render crashed: {}".format(e), file=sys.stderr)

    # ── Report ──
    if all_warnings:
        print("\n{} warning(s):".format(len(all_warnings)), file=sys.stderr)
        for w in all_warnings:
            print("  - {}".format(w), file=sys.stderr)

    if ok_count > 0:
        print("\nDone. {} file(s) generated.".format(ok_count))
        if args.json_summary:
            files = []
            for path in sorted(set(generated_paths)):
                try:
                    with open(path, "rb") as handle:
                        data = handle.read()
                    files.append({
                        "path": os.path.relpath(path, args.output).replace(os.sep, "/"),
                        "absolute_path": os.path.abspath(path),
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    })
                except Exception as e:
                    all_warnings.append("summary failed for {}: {}".format(path, e))
            print(json.dumps({
                "status": "ok",
                "format": args.format,
                "files": files,
                "warnings": all_warnings,
                "errors": [],
            }, ensure_ascii=False, sort_keys=True))
        sys.exit(0)
    else:
        print("\n[FAIL] No output generated.", file=sys.stderr)
        if args.json_summary:
            print(json.dumps({
                "status": "error",
                "format": args.format,
                "files": [],
                "warnings": all_warnings,
                "errors": [{"code": "DIAGRAM_RENDER_NO_OUTPUT", "message": "No output generated"}],
            }, ensure_ascii=False, sort_keys=True))
        sys.exit(1)


if __name__ == "__main__":
    main()
