"""Reserved adapter for future Lezaiyun Schema v1.0 export.

S0–S4 MUST NOT implement website JSON import/upload here.
Implementation is blocked until website provides formal schema docs and approval (S5).
"""

from __future__ import annotations

from typing import Any, Dict

from lebench.core.result import RunResult


class SiteSchemaNotImplementedError(NotImplementedError):
    """Raised when site schema export is requested before S5 approval."""


def export_site_schema_v1(_result: RunResult) -> Dict[str, Any]:
    raise SiteSchemaNotImplementedError(
        "site_schema_v1 is reserved for S5. "
        "Use adapters.internal_json / adapters.txt_report for S0 outputs."
    )
