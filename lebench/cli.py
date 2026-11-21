"""LeBench command-line interface."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

from lebench import __version__
from lebench.adapters.internal_json import write_internal_json
from lebench.adapters.txt_report import render_txt, write_txt_report
from lebench.core.profiles import INTENSITIES, PRODUCT_TYPES, PROFILES, get_intensity, get_profile
from lebench.core.runner import Runner, doctor_report
from lebench.modules import REGISTRY


def _setup_logging(verbose: bool, log_file: Optional[Path]) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def _split_csv(value: Optional[str]) -> Optional[List[str]]:
    if value is None or value.strip() == "":
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def cmd_doctor(_args: argparse.Namespace) -> int:
    report = doctor_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    plat = report.get("platform") or {}
    if not plat.get("is_linux"):
        print("\n[warn] 当前非 Linux；S0 以 Linux x86_64 为首要目标。", file=sys.stderr)
        return 0
    return 0


def cmd_profiles(_args: argparse.Namespace) -> int:
    print("LeBench Profiles\n")
    for name in PRODUCT_TYPES:
        p = PROFILES[name]
        print(f"  {p.name}")
        print(f"    product_type : {p.product_type}")
        print(f"    description  : {p.description}")
        print(f"    focus        : {', '.join(p.focus_modules)}")
        print(f"    site_required: {', '.join(p.site_required)}")
        if p.unsuitable_auto:
            print(f"    unsuitable   : {'; '.join(p.unsuitable_auto)}")
        print()
    print("Intensities:", ", ".join(INTENSITIES))
    for name in INTENSITIES:
        plan = get_intensity(name)
        print(f"  {plan.name}: {plan.description}")
        print(f"    default_modules: {', '.join(plan.default_modules)}")
    return 0


def cmd_modules(_args: argparse.Namespace) -> int:
    print("LeBench Modules\n")
    # Probe with light context
    from lebench.core.platform import detect_platform
    from lebench.modules.base import RunContext

    plat = detect_platform()
    ctx = RunContext(
        product_type="vps",
        intensity="quick",
        work_dir=".",
        output_dir=".",
        environment={"is_root": plat.is_root, "arch": plat.arch},
    )
    for name, mod in REGISTRY.items():
        probe = mod.probe(ctx)
        status = "implemented" if mod.implemented else f"planned/{mod.stage}"
        avail = "available" if probe.available else f"unavailable ({probe.reason})"
        print(f"  {name:16} [{status}] {avail}")
        print(f"    {mod.description}")
        if mod.dependencies:
            print(f"    requires: {', '.join(mod.dependencies)}")
        if mod.optional_dependencies:
            print(f"    optional: {', '.join(mod.optional_dependencies)}")
        print()
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    try:
        get_profile(args.profile)
        get_intensity(args.intensity)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = output_dir / f"lebench-{stamp}.log"
    _setup_logging(args.verbose, log_path)

    include = _split_csv(args.modules)
    skip = _split_csv(args.skip) or []

    if args.allow_sensitive:
        print(
            "[warn] 已启用 --allow-sensitive：报告可能包含公网 IP/主机名等敏感信息。",
            file=sys.stderr,
        )

    runner = Runner(
        profile_name=args.profile,
        intensity_name=args.intensity,
        modules=include,
        skip=skip,
        output_dir=str(output_dir),
        yes=args.yes,
        dry_run=args.dry_run,
        allow_sensitive=args.allow_sensitive,
        config_dir=args.config_dir,
        enable_geekbench=args.enable_geekbench,
        enable_app_perf=args.enable_app_perf,
        enable_compatibility=args.enable_compatibility,
        enable_ip_quality=not args.disable_ip_quality,
        confirm_deep=args.confirm_deep,
    )

    try:
        selected = runner.selected_module_names()
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"LeBench {__version__} — profile={args.profile} intensity={args.intensity}")
    print(f"modules: {', '.join(selected)}")
    if args.dry_run:
        print("mode: dry-run（不执行测试）")

    result = runner.run()

    # Terminal summary
    print()
    print(render_txt(result, allow_sensitive=args.allow_sensitive))

    txt_path = output_dir / f"lebench-{args.profile}-{args.intensity}-{stamp}.txt"
    json_path = output_dir / f"lebench-{args.profile}-{args.intensity}-{stamp}.internal.json"
    write_txt_report(result, txt_path, allow_sensitive=args.allow_sensitive)
    write_internal_json(result, json_path, allow_sensitive=args.allow_sensitive)

    print(f"TXT 报告: {txt_path}")
    print(f"内部 JSON: {json_path}  （非网站导入格式）")
    print(f"日志: {log_path}")

    failed = [
        name
        for name, mod in result.modules.items()
        if mod.status == "failed"
    ]
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lebench",
        description="LeBench — Linux 五类服务器统一评测工具",
    )
    parser.add_argument("--version", action="version", version=f"LeBench {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="调试日志")

    sub = parser.add_subparsers(dest="command")

    p_doctor = sub.add_parser("doctor", help="检查系统、权限、依赖与可用空间（不安装）")
    p_doctor.set_defaults(func=cmd_doctor)

    p_profiles = sub.add_parser("profiles", help="列出五种 Profile 与强度默认模块")
    p_profiles.set_defaults(func=cmd_profiles)

    p_modules = sub.add_parser("modules", help="列出模块、依赖与可用性")
    p_modules.set_defaults(func=cmd_modules)

    p_run = sub.add_parser("run", help="按 Profile/强度运行评测")
    p_run.add_argument(
        "--profile",
        required=True,
        choices=list(PRODUCT_TYPES),
        help="产品类型：vps|dedicated|gpu|lightweight|bare_metal",
    )
    p_run.add_argument(
        "--intensity",
        default="quick",
        choices=list(INTENSITIES),
        help="测试强度：quick|standard|deep（默认 quick）",
    )
    p_run.add_argument(
        "--modules",
        default=None,
        help="显式指定模块（逗号分隔）；指定后不再偷偷追加高风险模块",
    )
    p_run.add_argument("--skip", default=None, help="跳过模块（逗号分隔）")
    p_run.add_argument("--output-dir", default="./reports", help="报告输出目录")
    p_run.add_argument("--dry-run", action="store_true", help="仅展示模块/预算/风险，不执行")
    p_run.add_argument(
        "--yes",
        action="store_true",
        help="跳过低风险确认；不能绕过破坏性操作禁令",
    )
    p_run.add_argument(
        "--allow-sensitive",
        action="store_true",
        help="允许在报告中保留敏感信息（默认脱敏）",
    )
    p_run.add_argument(
        "--config-dir",
        default=None,
        help="节点/目标配置目录（speedtest_targets.yaml、ping_targets.yaml 等）",
    )
    p_run.add_argument(
        "--enable-geekbench",
        action="store_true",
        help="若本机已安装 Geekbench 则运行（不下载、不内嵌）",
    )
    p_run.add_argument(
        "--enable-app-perf",
        action="store_true",
        help="显式启用隔离的本地 HTTP 轻量压测",
    )
    p_run.add_argument(
        "--enable-compatibility",
        action="store_true",
        help="显式启用兼容性/可达性探测（deep 默认也会跑）",
    )
    p_run.add_argument(
        "--disable-ip-quality",
        action="store_true",
        help="跳过 IP 质量外部查询",
    )
    p_run.add_argument(
        "--confirm-deep",
        action="store_true",
        help="确认执行 deep 强度（--yes 不能代替本标志）",
    )
    p_run.set_defaults(func=cmd_run)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    # Propagate verbose for non-run commands
    if args.command != "run":
        _setup_logging(getattr(args, "verbose", False), None)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
