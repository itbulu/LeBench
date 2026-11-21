"""Minimal config loader (JSON preferred; simple YAML subset without PyYAML)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


def load_config(path: Union[str, Path]) -> Dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    text = p.read_text(encoding="utf-8")
    suffix = p.suffix.lower()
    if suffix == ".json":
        data = json.loads(text)
    elif suffix in {".yaml", ".yml"}:
        data = _parse_simple_yaml(text)
    else:
        # try json then yaml
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = _parse_simple_yaml(text)
    if not isinstance(data, dict):
        raise ValueError(f"config_root_must_be_mapping:{p}")
    return data


def find_config(
    names: List[str],
    *,
    search_dirs: Optional[List[Union[str, Path]]] = None,
) -> Optional[Path]:
    dirs = search_dirs or ["."]
    for d in dirs:
        base = Path(d)
        for name in names:
            candidate = base / name
            if candidate.is_file():
                return candidate
    return None


def _parse_scalar(raw: str) -> Any:
    s = raw.strip()
    if s.startswith(("'", '"')) and s.endswith(("'", '"')) and len(s) >= 2:
        return s[1:-1]
    if s == "[]":
        return []
    if s == "{}":
        return {}
    if s.lower() in {"true", "yes", "on"}:
        return True
    if s.lower() in {"false", "no", "off"}:
        return False
    if s.lower() in {"null", "~", "none"}:
        return None
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    return s


def _parse_simple_yaml(text: str) -> Dict[str, Any]:
    """Parse a constrained YAML subset used by LeBench example configs."""
    root: Dict[str, Any] = {}
    stack: List[tuple[int, Any]] = [(-1, root)]
    pending_key: Optional[str] = None

    for lineno, raw_line in enumerate(text.splitlines(), 1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        # strip inline comments for simple cases
        line = raw_line.split(" #", 1)[0].rstrip()
        indent = len(line) - len(line.lstrip(" "))
        content = line.lstrip(" ")

        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if content.startswith("- "):
            item_raw = content[2:].strip()
            if not isinstance(parent, list):
                # convert pending mapping value to list
                raise ValueError(f"yaml_list_without_parent:{lineno}")
            if ":" in item_raw and not item_raw.startswith("{"):
                # inline mapping start: "- name: x"
                key, val = item_raw.split(":", 1)
                obj: Dict[str, Any] = {}
                v = val.strip()
                if v:
                    obj[key.strip()] = _parse_scalar(v)
                else:
                    # nested — treat as empty for now; subsequent indented keys need object parent
                    pass
                if v:
                    parent.append(obj)
                    stack.append((indent, obj))
                else:
                    parent.append(obj)
                    stack.append((indent, obj))
                    # put key with empty value expecting nested — uncommon
                    if not v:
                        obj[key.strip()] = None
            else:
                parent.append(_parse_scalar(item_raw))
            continue

        if ":" not in content:
            raise ValueError(f"yaml_invalid_line:{lineno}:{content}")

        key, val = content.split(":", 1)
        key = key.strip()
        val = val.strip()
        if val == "":
            # nested container — peek next? default to dict; list if next is '-'
            # Use a placeholder dict; if first child is list item, replace — hard.
            # Convention in our files: empty value after key means list or dict.
            # We create a list if key ends with common list names, else dict.
            if key in {"nodes", "targets", "checks", "features", "endpoints"}:
                container: Any = []
            else:
                container = {}
            if isinstance(parent, dict):
                parent[key] = container
            elif isinstance(parent, list):
                # key under list item
                raise ValueError(f"yaml_unexpected_key_in_list:{lineno}")
            stack.append((indent, container))
        else:
            if isinstance(parent, dict):
                parent[key] = _parse_scalar(val)
            else:
                raise ValueError(f"yaml_key_under_list:{lineno}")

    _ = pending_key
    return root
