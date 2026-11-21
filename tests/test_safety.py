from __future__ import annotations

import pytest

from lebench.core.safety import (
    assert_safe_temp_file,
    is_blocked_write_path,
    redact_mapping,
)


def test_block_device_paths():
    assert is_blocked_write_path("/dev/sda")
    assert is_blocked_write_path("/dev/nvme0n1")
    assert is_blocked_write_path("/proc/self")
    assert not is_blocked_write_path("/tmp/lebench-test.bin")


def test_assert_safe_temp_file_rejects_dev():
    with pytest.raises(PermissionError):
        assert_safe_temp_file("/dev/sda")


def test_redact_sensitive_keys():
    data = {
        "public_ip": "203.0.113.10",
        "cpu_model": "Test CPU",
        "note": "server 203.0.113.10 online",
        "hostname_redacted": "h****t",
        "hostname": "secret-host",
    }
    out = redact_mapping(data, allow_sensitive=False)
    assert out["public_ip"] == "<redacted>"
    assert out["cpu_model"] == "Test CPU"
    assert "<ip>" in out["note"]
    assert out["hostname"] == "<redacted>"
    assert out["hostname_redacted"] == "h****t"
