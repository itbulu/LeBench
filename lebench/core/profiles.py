"""Product profiles and intensity defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence


PRODUCT_TYPES = ("vps", "dedicated", "gpu", "lightweight", "bare_metal")
INTENSITIES = ("quick", "standard", "deep")

# Site-required modules for future Schema contract (not all executed in S0).
SITE_REQUIRED_MODULES: Dict[str, List[str]] = {
    "vps": ["system"],
    "dedicated": ["system", "physical"],
    "gpu": ["system", "gpu"],
    "lightweight": ["system", "app_perf"],
    "bare_metal": ["system", "physical", "cloud_delivery"],
}


@dataclass(frozen=True)
class IntensityPlan:
    name: str
    default_modules: List[str]
    description: str
    notes: List[str] = field(default_factory=list)


INTENSITY_PLANS: Dict[str, IntensityPlan] = {
    "quick": IntensityPlan(
        name="quick",
        default_modules=["system", "cpu", "memory"],
        description="system + 短时 CPU + 轻量内存；磁盘/网络可选",
        notes=["尽量少写盘；缺依赖的模块记 not_run"],
    ),
    "standard": IntensityPlan(
        name="standard",
        default_modules=["system", "cpu", "memory", "disk_dd", "disk_fio", "network", "ping"],
        description="公共本机性能 + 有界网络/Ping",
        notes=["运行前显示预算；缺工具/空间则跳过并保留其他模块"],
    ),
    "deep": IntensityPlan(
        name="deep",
        default_modules=[
            "system",
            "cpu",
            "memory",
            "disk_dd",
            "disk_fio",
            "network",
            "ping",
            "routes",
            "ip_quality",
            "compatibility",
            "stability",
        ],
        description="standard + 增强模块（高风险需确认）",
        notes=["不默认执行破坏性测试；--yes 不能绕过高风险确认"],
    ),
}


@dataclass(frozen=True)
class Profile:
    name: str
    product_type: str
    description: str
    focus_modules: List[str]
    site_required: List[str]
    unsuitable_auto: List[str] = field(default_factory=list)


PROFILES: Dict[str, Profile] = {
    "vps": Profile(
        name="vps",
        product_type="vps",
        description="VPS 公共性能评测",
        focus_modules=["system", "cpu", "memory", "disk_fio", "network", "ping"],
        site_required=SITE_REQUIRED_MODULES["vps"],
        unsuitable_auto=["商家标称配置", "优化线路结论"],
    ),
    "dedicated": Profile(
        name="dedicated",
        product_type="dedicated",
        description="独立服务器（含物理硬件探测）",
        focus_modules=["system", "physical", "cpu", "memory", "disk_fio"],
        site_required=SITE_REQUIRED_MODULES["dedicated"],
        unsuitable_auto=["IPMI/KVM/救援等产品能力"],
    ),
    "gpu": Profile(
        name="gpu",
        product_type="gpu",
        description="GPU 服务器",
        focus_modules=["system", "gpu", "cpu", "memory"],
        site_required=SITE_REQUIRED_MODULES["gpu"],
        unsuitable_auto=["未经模型基准的推理吞吐"],
    ),
    "lightweight": Profile(
        name="lightweight",
        product_type="lightweight",
        description="轻量应用云服务器",
        focus_modules=["system", "app_perf", "cpu", "memory", "disk_fio"],
        site_required=SITE_REQUIRED_MODULES["lightweight"],
        unsuitable_auto=["控制台镜像/快照/备份能力"],
    ),
    "bare_metal": Profile(
        name="bare_metal",
        product_type="bare_metal",
        description="裸金属云（注意：bare_metal 不是 baremetal）",
        focus_modules=["system", "physical", "cloud_delivery"],
        site_required=SITE_REQUIRED_MODULES["bare_metal"],
        unsuitable_auto=["云 API 创建→SSH/重装/销毁耗时"],
    ),
}


def get_profile(name: str) -> Profile:
    key = name.strip().lower()
    if key == "baremetal":
        raise KeyError("invalid_profile:baremetal; use bare_metal")
    if key not in PROFILES:
        raise KeyError(f"unknown_profile:{name}")
    return PROFILES[key]


def get_intensity(name: str) -> IntensityPlan:
    key = name.strip().lower()
    if key not in INTENSITY_PLANS:
        raise KeyError(f"unknown_intensity:{name}")
    return INTENSITY_PLANS[key]


def resolve_modules(
    profile: Profile,
    intensity: IntensityPlan,
    *,
    include: Sequence[str] | None = None,
    skip: Sequence[str] | None = None,
) -> List[str]:
    """Resolve module list. ``include`` replaces defaults (no silent high-risk append)."""
    if include:
        selected = [m.strip() for m in include if m.strip()]
    else:
        # Profile focus ∪ intensity defaults, preserve order, ensure site_required present as keys later
        selected = list(dict.fromkeys(intensity.default_modules + profile.focus_modules))
        # For quick intensity keep it minimal: intensity defaults only + site_required markers via runner
        if intensity.name == "quick":
            selected = list(dict.fromkeys(intensity.default_modules + profile.site_required))

    skip_set = {m.strip() for m in (skip or []) if m.strip()}
    return [m for m in selected if m not in skip_set]
