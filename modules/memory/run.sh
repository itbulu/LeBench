#!/usr/bin/env bash
# modules/memory/run.sh - memory benchmarks via sysbench

lzy_module_memory() {
  local out="${LZY_RUN_DIR}/memory.json"
  lzy_log_info "开始内存测试"

  local size="${LZY_MEM_SYSBENCH_SIZE:-1G}"
  local threads="${LZY_MEM_SYSBENCH_THREADS:-1}"
  local read_ops="" write_ops="" read_bw="" write_bw=""
  local status="ok" error=""

  lzy_info "sysbench memory read (size=${size})"
  local read_raw
  if read_raw="$(sysbench memory --memory-block-size=1K --memory-total-size="${size}" \
      --memory-oper=read --threads="${threads}" run 2>&1)"; then
    echo "${read_raw}" >>"$(lzy_log_file memory)"
    read_ops="$(echo "${read_raw}" | awk '/Total operations:/{print $3; exit}' | tr -d '()')"
    read_bw="$(echo "${read_raw}" | grep -oE '[0-9]+(\.[0-9]+)? MiB/sec' | head -1 | awk '{print $1}')"
  else
    status="fail"
    error="memory read failed"
    echo "${read_raw}" >>"$(lzy_log_file memory)"
  fi

  lzy_info "sysbench memory write (size=${size})"
  local write_raw
  if write_raw="$(sysbench memory --memory-block-size=1K --memory-total-size="${size}" \
      --memory-oper=write --threads="${threads}" run 2>&1)"; then
    echo "${write_raw}" >>"$(lzy_log_file memory)"
    write_ops="$(echo "${write_raw}" | awk '/Total operations:/{print $3; exit}' | tr -d '()')"
    write_bw="$(echo "${write_raw}" | grep -oE '[0-9]+(\.[0-9]+)? MiB/sec' | head -1 | awk '{print $1}')"
  else
    status="fail"
    error="${error}; memory write failed"
    echo "${write_raw}" >>"$(lzy_log_file memory)"
  fi

  # Latency: sysbench memory with seq access (best-effort note)
  local latency_note="sysbench memory does not expose explicit latency; use bandwidth as primary metric"

  cat >"${out}" <<EOF
{
  "module": "memory",
  "status": "${status}",
  "timestamp": "$(lzy_now_iso)",
  "error": "$(lzy_json_escape "${error}")",
  "config": {
    "size": "$(lzy_json_escape "${size}")",
    "threads": $(lzy_json_num_or_null "${threads}")
  },
  "read": {
    "ops_per_sec": $(lzy_json_num_or_null "${read_ops}"),
    "mib_per_sec": $(lzy_json_num_or_null "${read_bw}")
  },
  "write": {
    "ops_per_sec": $(lzy_json_num_or_null "${write_ops}"),
    "mib_per_sec": $(lzy_json_num_or_null "${write_bw}")
  },
  "latency": {
    "note": "$(lzy_json_escape "${latency_note}")",
    "value": null
  }
}
EOF

  lzy_info "已写入 ${out}"
  [[ "${status}" == "ok" ]] && return 0 || return 1
}
