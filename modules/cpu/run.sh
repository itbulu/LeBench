#!/usr/bin/env bash
# modules/cpu/run.sh - CPU benchmarks (sysbench required; UnixBench/Geekbench optional)

lzy_module_cpu() {
  local out="${LZY_RUN_DIR}/cpu.json"
  lzy_log_info "开始 CPU 测试"

  local threads="${LZY_CPU_SYSBENCH_THREADS:-0}"
  if [[ "${threads}" == "0" || -z "${threads}" ]]; then
    threads="$(nproc 2>/dev/null || echo 1)"
  fi
  local events="${LZY_CPU_SYSBENCH_EVENTS:-10000}"

  local single_eps="" multi_eps=""
  local single_raw="" multi_raw=""
  local sb_status="ok" sb_error=""

  # --- sysbench single core ---
  lzy_info "sysbench CPU 单核 (threads=1, events=${events})"
  if single_raw="$(sysbench cpu --cpu-max-prime=20000 --threads=1 --events="${events}" run 2>&1)"; then
    echo "${single_raw}" >>"$(lzy_log_file cpu)"
    single_eps="$(echo "${single_raw}" | awk '/events per second/{print $4; exit}')"
  else
    sb_status="fail"
    sb_error="sysbench single-core failed"
    lzy_warn "${sb_error}"
    echo "${single_raw}" >>"$(lzy_log_file cpu)"
  fi

  # --- sysbench multi core ---
  lzy_info "sysbench CPU 多核 (threads=${threads}, events=${events})"
  if multi_raw="$(sysbench cpu --cpu-max-prime=20000 --threads="${threads}" --events="${events}" run 2>&1)"; then
    echo "${multi_raw}" >>"$(lzy_log_file cpu)"
    multi_eps="$(echo "${multi_raw}" | awk '/events per second/{print $4; exit}')"
  else
    sb_status="fail"
    sb_error="${sb_error}; sysbench multi-core failed"
    lzy_warn "sysbench multi-core failed"
    echo "${multi_raw}" >>"$(lzy_log_file cpu)"
  fi

  # --- Geekbench optional ---
  local gb_single="" gb_multi="" gb_status="skip" gb_error=""
  if [[ "${LZY_CPU_ENABLE_GEEKBENCH:-1}" == "1" ]]; then
    local gb_bin=""
    for c in geekbench6 geekbench5 geekbench; do
      if lzy_require_cmd "${c}"; then
        gb_bin="${c}"
        break
      fi
    done
    if [[ -n "${gb_bin}" ]]; then
      lzy_info "检测到 ${gb_bin}，开始 Geekbench（可能较久）"
      local gb_out
      if gb_out="$("${gb_bin}" --cpu 2>&1)"; then
        echo "${gb_out}" >>"$(lzy_log_file cpu)"
        gb_single="$(echo "${gb_out}" | awk '/Single-Core Score/{print $NF; exit}')"
        gb_multi="$(echo "${gb_out}" | awk '/Multi-Core Score/{print $NF; exit}')"
        gb_status="ok"
      else
        gb_status="fail"
        gb_error="geekbench execution failed"
        echo "${gb_out}" >>"$(lzy_log_file cpu)"
      fi
    else
      gb_error="geekbench not installed"
    fi
  else
    gb_error="disabled by config"
  fi

  # --- UnixBench optional (detect common paths) ---
  local ub_status="skip" ub_score="" ub_error=""
  if [[ "${LZY_CPU_ENABLE_UNIXBENCH:-1}" == "1" ]]; then
    local ub_bin=""
    for p in /opt/byte-unixbench/UnixBench/Run ./UnixBench/Run /usr/local/bin/unixbench; do
      if [[ -x "${p}" ]]; then
        ub_bin="${p}"
        break
      fi
    done
    if [[ -n "${ub_bin}" ]]; then
      lzy_info "检测到 UnixBench: ${ub_bin}"
      local ub_out
      if ub_out="$("${ub_bin}" -c 1 -c "${threads}" 2>&1)"; then
        echo "${ub_out}" >>"$(lzy_log_file cpu)"
        ub_score="$(echo "${ub_out}" | awk '/System Benchmarks Index Score/{print $NF; exit}')"
        ub_status="ok"
      else
        ub_status="fail"
        ub_error="unixbench failed"
        echo "${ub_out}" >>"$(lzy_log_file cpu)"
      fi
    else
      ub_error="unixbench not found"
    fi
  else
    ub_error="disabled by config"
  fi

  local overall="ok"
  if [[ "${sb_status}" != "ok" ]]; then
    overall="fail"
  fi

  cat >"${out}" <<EOF
{
  "module": "cpu",
  "status": "${overall}",
  "timestamp": "$(lzy_now_iso)",
  "sysbench": {
    "status": "${sb_status}",
    "error": "$(lzy_json_escape "${sb_error}")",
    "threads": $(lzy_json_num_or_null "${threads}"),
    "events": $(lzy_json_num_or_null "${events}"),
    "single_eps": $(lzy_json_num_or_null "${single_eps}"),
    "multi_eps": $(lzy_json_num_or_null "${multi_eps}")
  },
  "geekbench": {
    "status": "${gb_status}",
    "error": "$(lzy_json_escape "${gb_error}")",
    "single": $(lzy_json_num_or_null "${gb_single}"),
    "multi": $(lzy_json_num_or_null "${gb_multi}")
  },
  "unixbench": {
    "status": "${ub_status}",
    "error": "$(lzy_json_escape "${ub_error}")",
    "index_score": $(lzy_json_num_or_null "${ub_score}")
  }
}
EOF

  lzy_info "已写入 ${out}"
  [[ "${overall}" == "ok" ]] && return 0 || return 1
}
