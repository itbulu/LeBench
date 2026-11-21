"""Human-readable TXT report for manual review / article drafts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from lebench.core.result import RunResult
from lebench.core.safety import redact_mapping


COMPARABILITY_NOTE = (
    "可比性限制：CPU 共享争用、缓存、磁盘挂载类型、测速节点、网络方向、测试时间均影响结果；"
    "系统探测值为访客可见参数，不等于商家广告配置。"
)


def _fmt_value(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def render_txt(result: RunResult, *, allow_sensitive: bool = False) -> str:
    data = result.to_dict()
    if not allow_sensitive:
        data = redact_mapping(data, allow_sensitive=False)

    lines: List[str] = []
    lines.append("=" * 72)
    lines.append("LeBench 评测报告（内部 TXT，非网站导入格式）")
    lines.append("=" * 72)
    lines.append(f"工具: {data['tool']['name']} {data['tool']['version']}")
    lines.append(f"Run ID: {data['run_id']}")
    lines.append(f"产品类型(profile): {data['product_type']}")
    lines.append(f"强度: {data['intensity']}")
    lines.append(f"开始: {data['started_at']}")
    lines.append(f"结束: {data.get('finished_at') or 'N/A'}")
    lines.append(f"Dry-run: {data.get('dry_run')}")
    privacy = data.get("privacy") or {}
    lines.append(
        f"隐私脱敏: {'开启' if privacy.get('default_redaction', True) and not allow_sensitive else '已按用户选择导出敏感信息（有风险）'}"
    )
    lines.append("")
    lines.append("--- 环境概要 ---")
    env = data.get("environment") or {}
    for key in (
        "os",
        "kernel",
        "arch",
        "python_version",
        "is_linux",
        "is_root",
        "container_hint",
        "hostname_redacted",
    ):
        if key in env:
            lines.append(f"  {key}: {_fmt_value(env.get(key))}")
    if env.get("budget"):
        budget = env["budget"]
        lines.append(
            "  budget: "
            f"time≈{budget.get('time_sec')}s, "
            f"disk_write≈{budget.get('disk_write_mb')}MB, "
            f"network≈{budget.get('network_mb')}MB"
        )
    lines.append("")
    lines.append(f"选定模块: {', '.join(data.get('selected_modules') or [])}")
    if data.get("skipped_modules"):
        lines.append(f"跳过模块: {', '.join(data['skipped_modules'])}")
    if data.get("warnings"):
        lines.append("")
        lines.append("--- 全局警告 ---")
        for w in data["warnings"]:
            lines.append(f"  - {w}")

    lines.append("")
    lines.append("--- 模块结果 ---")
    modules: Dict[str, Any] = data.get("modules") or {}
    for name, mod in modules.items():
        lines.append("")
        lines.append(f"[{name}] status={mod.get('status')}")
        if mod.get("reason"):
            lines.append(f"  reason: {mod['reason']}")
        if mod.get("duration_sec") is not None:
            lines.append(f"  duration_sec: {mod['duration_sec']}")
        tool = mod.get("tool") or {}
        if tool:
            lines.append(f"  tool: {tool.get('name')} {tool.get('version', '')}".rstrip())
        metrics = mod.get("metrics") or {}
        if metrics:
            lines.append("  metrics:")
            for mk, mv in metrics.items():
                lines.append(f"    {mk}: {_fmt_value(mv)}")
        conditions = mod.get("conditions") or {}
        if conditions:
            lines.append("  conditions:")
            for ck, cv in conditions.items():
                if isinstance(cv, (dict, list)):
                    lines.append(f"    {ck}: {cv}")
                else:
                    lines.append(f"    {ck}: {_fmt_value(cv)}")
        for w in mod.get("warnings") or []:
            lines.append(f"  warning: {w}")
        for e in mod.get("errors") or []:
            lines.append(f"  error: {e}")
        if mod.get("sources"):
            lines.append(f"  sources: {', '.join(mod['sources'])}")

    lines.append("")
    lines.append("--- 说明 ---")
    lines.append(COMPARABILITY_NOTE)
    lines.append("内部格式: lebench-internal-v0（不可直接导入乐在云）。")
    lines.append("=" * 72)
    lines.append("")
    return "\n".join(lines)


def write_txt_report(
    result: RunResult,
    path: str | Path,
    *,
    allow_sensitive: bool = False,
) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_txt(result, allow_sensitive=allow_sensitive), encoding="utf-8")
    return out
