"""Module scheduling, dependency checks, cancel, timeout."""

from __future__ import annotations

import logging
import signal
import tempfile
import time
import traceback
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from lebench import __version__
from lebench.core.intensity_params import get_params
from lebench.core.platform import detect_platform, free_space_bytes
from lebench.core.profiles import get_intensity, get_profile, resolve_modules
from lebench.core.result import ModuleResult, RunResult
from lebench.core.safety import CostEstimate, SafetyPolicy, confirm, redact_mapping
from lebench.modules import REGISTRY
from lebench.modules.base import BenchmarkModule, RunContext

logger = logging.getLogger("lebench.runner")


class Runner:
    def __init__(
        self,
        *,
        profile_name: str,
        intensity_name: str = "quick",
        modules: Optional[Sequence[str]] = None,
        skip: Optional[Sequence[str]] = None,
        output_dir: str = "./reports",
        yes: bool = False,
        dry_run: bool = False,
        allow_sensitive: bool = False,
        safety: Optional[SafetyPolicy] = None,
        config_dir: Optional[str] = None,
        enable_geekbench: bool = False,
        enable_app_perf: bool = False,
        enable_compatibility: bool = False,
        enable_ip_quality: bool = True,
        confirm_deep: bool = False,
    ) -> None:
        self.profile = get_profile(profile_name)
        self.intensity = get_intensity(intensity_name)
        self.include = list(modules) if modules else None
        self.skip = list(skip) if skip else []
        self.output_dir = Path(output_dir)
        self.yes = yes
        self.dry_run = dry_run
        self.allow_sensitive = allow_sensitive
        self.safety = safety or SafetyPolicy()
        self.config_dir = config_dir
        self.enable_geekbench = enable_geekbench
        self.enable_app_perf = enable_app_perf
        self.enable_compatibility = enable_compatibility
        self.enable_ip_quality = enable_ip_quality
        self.confirm_deep = confirm_deep
        self._cancel = False
        self._active_children: List[object] = []

    def _install_signal_handlers(self) -> None:
        def _handler(signum: int, _frame: object) -> None:
            logger.warning("signal_received:%s — requesting cancel and cleanup", signum)
            self._cancel = True

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _handler)
            except (ValueError, OSError):
                # Not in main thread or unsupported
                pass

    def selected_module_names(self) -> List[str]:
        names = resolve_modules(
            self.profile,
            self.intensity,
            include=self.include,
            skip=self.skip,
        )
        unknown = [n for n in names if n not in REGISTRY]
        if unknown:
            raise KeyError(f"unknown_modules:{','.join(unknown)}")
        return names

    def estimate_total(self, names: Iterable[str], context: RunContext) -> CostEstimate:
        total = CostEstimate()
        for name in names:
            mod = REGISTRY[name]
            total = total.merge(mod.estimate_cost(context))
        return total

    def run(self) -> RunResult:
        self._install_signal_handlers()
        plat = detect_platform()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        selected = self.selected_module_names()
        result = RunResult(
            product_type=self.profile.product_type,
            intensity=self.intensity.name,
            tool_version=__version__,
            selected_modules=selected,
            skipped_modules=list(self.skip),
            dry_run=self.dry_run,
            environment={
                "os": plat.distro_pretty or plat.os_name,
                "kernel": plat.kernel,
                "arch": plat.arch,
                "python_version": plat.python_version,
                "is_linux": plat.is_linux,
                "is_root": plat.is_root,
                "container_hint": plat.container_hint,
                "hostname_redacted": plat.hostname_redacted,
            },
            privacy={
                "sensitive_export": self.allow_sensitive,
                "default_redaction": not self.allow_sensitive,
            },
            warnings=list(plat.warnings),
        )

        if not plat.is_linux:
            result.warnings.append("non_linux_unverified — 以 Linux 为首要目标")

        params = get_params(self.intensity.name)
        work_dir = tempfile.mkdtemp(prefix="lebench-", dir=str(self.output_dir))
        context = RunContext(
            product_type=self.profile.product_type,
            intensity=self.intensity.name,
            work_dir=work_dir,
            output_dir=str(self.output_dir),
            yes=self.yes,
            dry_run=self.dry_run,
            allow_sensitive=self.allow_sensitive,
            safety=self.safety,
            environment={
                "is_root": plat.is_root,
                "arch": plat.arch,
                "free_space_bytes": free_space_bytes(self.output_dir),
                "config_dir": self.config_dir,
                "enable_geekbench": self.enable_geekbench,
                "enable_app_perf": self.enable_app_perf,
                "enable_compatibility": self.enable_compatibility,
                "enable_ip_quality": self.enable_ip_quality,
                "intensity_params": params.to_dict(),
            },
        )

        budget = self.estimate_total(selected, context)
        result.environment["budget"] = budget.to_dict()
        result.environment["intensity_params"] = params.to_dict()

        # Confirmations:
        # - standard 磁盘/网络：--yes 可跳过（低/中风险）
        # - deep：--yes 不能绕过，需 --confirm-deep 或交互确认
        if not self.dry_run:
            needs_budget_confirm = budget.disk_write_mb >= 256 or budget.network_mb >= 50
            if self.intensity.name == "deep":
                ok = self.confirm_deep or confirm(
                    f"deep 强度高负载：预计写入≈{budget.disk_write_mb}MB，流量≈{budget.network_mb}MB，耗时≈{budget.time_sec}s。继续？",
                    assumed_yes=False,
                    high_risk=True,
                )
                if not ok:
                    result.warnings.append("deep_requires_--confirm-deep_or_interactive_yes")
                    for name in selected:
                        result.modules[name] = ModuleResult.not_run(reason="deep_unconfirmed")
                    self._ensure_site_required(result)
                    result.finish()
                    self._cleanup_work_dir(work_dir)
                    return self._maybe_redact(result)
            elif needs_budget_confirm:
                ok = confirm(
                    f"预计写入≈{budget.disk_write_mb}MB，流量≈{budget.network_mb}MB，耗时≈{budget.time_sec}s。继续？",
                    assumed_yes=self.yes,
                    high_risk=False,
                )
                if not ok:
                    result.warnings.append("aborted_budget_unconfirmed")
                    for name in selected:
                        result.modules[name] = ModuleResult.not_run(reason="budget_unconfirmed")
                    self._ensure_site_required(result)
                    result.finish()
                    self._cleanup_work_dir(work_dir)
                    return self._maybe_redact(result)

        if self.dry_run:
            for name in selected:
                mod = REGISTRY[name]
                probe = mod.probe(context)
                est = mod.estimate_cost(context)
                result.modules[name] = ModuleResult.not_run(
                    reason="dry_run",
                    conditions={
                        "probe": probe.to_dict(),
                        "estimate": est.to_dict(),
                        "implemented": mod.implemented,
                        "stage": mod.stage,
                    },
                    tool={"name": f"lebench.{name}", "version": __version__},
                    duration_sec=0.0,
                )
            # Ensure site-required keys exist
            self._ensure_site_required(result)
            result.finish()
            self._cleanup_work_dir(work_dir)
            return self._maybe_redact(result)

        for name in selected:
            if self._cancel:
                result.modules[name] = ModuleResult.not_run(reason="cancelled")
                result.warnings.append("run_cancelled")
                continue
            mod = REGISTRY[name]
            result.modules[name] = self._run_one(mod, context)

        self._ensure_site_required(result)
        result.finish()
        self._cleanup_work_dir(work_dir)
        return self._maybe_redact(result)

    def _run_one(self, mod: BenchmarkModule, context: RunContext) -> ModuleResult:
        logger.info("module_start:%s", mod.name)
        started = time.monotonic()
        try:
            probe = mod.probe(context)
            if not mod.implemented:
                return ModuleResult.not_run(
                    reason=probe.reason or "not_implemented_in_s0",
                    conditions={"probe": probe.to_dict(), "stage": mod.stage},
                    tool={"name": f"lebench.{mod.name}", "version": __version__},
                    duration_sec=round(time.monotonic() - started, 3),
                )
            if not probe.available:
                status_reason = probe.reason or "probe_unavailable"
                if status_reason.startswith("permission"):
                    return ModuleResult.permission_denied(
                        reason=status_reason,
                        conditions={"probe": probe.to_dict()},
                        duration_sec=round(time.monotonic() - started, 3),
                    )
                return ModuleResult.not_run(
                    reason=status_reason,
                    conditions={"probe": probe.to_dict()},
                    duration_sec=round(time.monotonic() - started, 3),
                )

            context.cancel_requested = self._cancel
            module_result = mod.run(context)
            logger.info("module_done:%s status=%s", mod.name, module_result.status)
            return module_result
        except Exception as exc:  # noqa: BLE001 — isolate module failures
            logger.error("module_failed:%s %s", mod.name, exc)
            logger.debug(traceback.format_exc())
            return ModuleResult.failed(
                reason=f"exception:{type(exc).__name__}",
                errors=[str(exc)],
                duration_sec=round(time.monotonic() - started, 3),
            )

    def _ensure_site_required(self, result: RunResult) -> None:
        for name in self.profile.site_required:
            if name in result.modules:
                continue
            if name in REGISTRY and not REGISTRY[name].implemented:
                result.modules[name] = ModuleResult.not_run(
                    reason="site_required_placeholder_not_implemented_in_s0",
                    conditions={"site_required": True, "stage": REGISTRY[name].stage},
                )
            else:
                result.modules[name] = ModuleResult.not_run(
                    reason="site_required_not_selected",
                    conditions={"site_required": True},
                )

    def _maybe_redact(self, result: RunResult) -> RunResult:
        if self.allow_sensitive:
            return result
        data = result.to_dict()
        redacted = redact_mapping(data, allow_sensitive=False)
        # Rebuild lightly: keep object but replace module metrics via dict round-trip is heavy;
        # apply redaction on nested metrics/conditions for report adapters instead.
        # Still strip obvious sensitive env fields.
        if "hostname" in result.environment:
            result.environment["hostname"] = "<redacted>"
        result.privacy["redacted"] = True
        # Store redacted snapshot hint
        result.environment["_redaction_applied"] = True
        _ = redacted  # adapters re-redact on write
        return result

    @staticmethod
    def _cleanup_work_dir(work_dir: str) -> None:
        path = Path(work_dir)
        try:
            if path.is_dir():
                for child in path.rglob("*"):
                    if child.is_file():
                        child.unlink(missing_ok=True)
                for child in sorted(path.rglob("*"), reverse=True):
                    if child.is_dir():
                        child.rmdir()
                path.rmdir()
        except OSError as exc:
            logger.warning("work_dir_cleanup_failed:%s", exc)


def doctor_report() -> Dict[str, object]:
    """Collect environment diagnostics without mutating the system."""
    from lebench.modules import REGISTRY

    plat = detect_platform()
    modules_info = {}
    # Minimal context for probing
    ctx = RunContext(
        product_type="vps",
        intensity="quick",
        work_dir=".",
        output_dir=".",
        environment={"is_root": plat.is_root, "arch": plat.arch},
    )
    for name, mod in REGISTRY.items():
        probe = mod.probe(ctx)
        modules_info[name] = {
            "implemented": mod.implemented,
            "stage": mod.stage,
            "description": mod.description,
            "dependencies": mod.dependencies,
            "optional_dependencies": mod.optional_dependencies,
            "probe": probe.to_dict(),
        }

    free = free_space_bytes(".")
    return {
        "tool": {"name": "LeBench", "version": __version__},
        "platform": plat.to_dict(),
        "free_space_bytes": free,
        "free_space_gb": round(free / (1024**3), 2) if free is not None else None,
        "modules": modules_info,
        "notes": [
            "doctor 仅检查，不安装软件包",
            "S0 仅 system 模块已实现",
            "兼容性未经验证的发行版/架构不得宣称支持",
        ],
    }
