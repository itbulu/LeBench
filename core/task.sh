#!/usr/bin/env bash
# core/task.sh - task orchestration; never abort full run on single module failure
# shellcheck source=/dev/null

# Module status tracking (name -> ok|fail|skip)
declare -A LZY_TASK_STATUS=()

lzy_run_init() {
  LZY_RUN_ID="$(lzy_new_run_id)"
  LZY_RUN_DIR="${LZY_RESULTS_DIR}/${LZY_RUN_ID}"
  lzy_ensure_dir "${LZY_RUN_DIR}"
  lzy_ensure_dir "${LZY_REPORTS_DIR}/${LZY_RUN_ID}"
  lzy_logger_init
  export LZY_RUN_ID LZY_RUN_DIR

  cat >"${LZY_RUN_DIR}/meta.json" <<EOF
{
  "tool": "$(lzy_json_escape "${LZY_NAME}")",
  "brand": "$(lzy_json_escape "${LZY_BRAND}")",
  "version": "$(lzy_json_escape "${LZY_VERSION}")",
  "run_id": "$(lzy_json_escape "${LZY_RUN_ID}")",
  "started_at": "$(lzy_now_iso)",
  "hostname": "$(lzy_json_escape "$(hostname 2>/dev/null || echo unknown)")"
}
EOF

  lzy_info "评测开始  run_id=${LZY_RUN_ID}"
  lzy_info "结果目录: ${LZY_RUN_DIR}"
}

lzy_module_script() {
  local module="$1"
  printf '%s/modules/%s/run.sh' "${LZY_ROOT}" "${module}"
}

# Run a single module; returns 0 even on failure (sets LZY_TASK_STATUS)
lzy_run_module() {
  local module="$1"
  local script
  script="$(lzy_module_script "${module}")"

  LZY_CURRENT_MODULE="${module}"
  export LZY_CURRENT_MODULE

  echo ""
  echo "${LZY_C_BOLD}======== 模块: ${module} ========${LZY_C_RESET}"

  if [[ ! -f "${script}" ]]; then
    lzy_warn "模块脚本不存在: ${script} — 跳过"
    lzy_log_warn "模块脚本不存在，跳过"
    LZY_TASK_STATUS["${module}"]="skip"
    _lzy_write_module_stub_json "${module}" "skip" "module script not found"
    return 0
  fi

  if ! lzy_deps_check_module "${module}"; then
    lzy_warn "依赖不足，跳过模块: ${module}"
    LZY_TASK_STATUS["${module}"]="skip"
    _lzy_write_module_stub_json "${module}" "skip" "missing dependencies"
    return 0
  fi

  lzy_deps_list_optional "${module}"

  # shellcheck disable=SC1090
  source "${script}"

  local fn="lzy_module_${module}"
  if ! declare -F "${fn}" >/dev/null 2>&1; then
    lzy_warn "模块未定义入口函数 ${fn} — 跳过"
    LZY_TASK_STATUS["${module}"]="skip"
    _lzy_write_module_stub_json "${module}" "skip" "entry function missing"
    return 0
  fi

  local start_ts end_ts rc=0
  start_ts="$(date +%s)"
  lzy_log_info "开始执行"
  set +e
  "${fn}"
  rc=$?
  set -e
  end_ts="$(date +%s)"
  local elapsed=$((end_ts - start_ts))

  if [[ ${rc} -eq 0 ]]; then
    LZY_TASK_STATUS["${module}"]="ok"
    lzy_ok "模块 [${module}] 完成 (${elapsed}s)"
    lzy_log_info "完成 rc=0 elapsed=${elapsed}s"
  else
    LZY_TASK_STATUS["${module}"]="fail"
    lzy_warn "模块 [${module}] 失败 rc=${rc} (${elapsed}s) — 继续后续测试"
    lzy_log_error "失败 rc=${rc} elapsed=${elapsed}s"
  fi

  LZY_CURRENT_MODULE="main"
  return 0
}

_lzy_write_module_stub_json() {
  local module="$1"
  local status="$2"
  local reason="$3"
  local out="${LZY_RUN_DIR}/${module}.json"
  cat >"${out}" <<EOF
{
  "module": "$(lzy_json_escape "${module}")",
  "status": "$(lzy_json_escape "${status}")",
  "error": "$(lzy_json_escape "${reason}")",
  "timestamp": "$(lzy_now_iso)"
}
EOF
}

lzy_run_modules() {
  local modules=("$@")
  local m
  for m in "${modules[@]}"; do
    lzy_run_module "${m}"
  done
}

lzy_run_score_engine() {
  local script="${LZY_ROOT}/scoring/score.sh"
  if [[ ! -f "${script}" ]]; then
    lzy_warn "评分脚本不存在，跳过"
    return 0
  fi
  if ! lzy_require_cmd jq; then
    lzy_warn "评分需要 jq，未安装 — 跳过评分"
    return 0
  fi
  # shellcheck disable=SC1090
  source "${script}"
  set +e
  lzy_run_scoring
  local rc=$?
  set -e
  if [[ ${rc} -eq 0 ]]; then
    LZY_TASK_STATUS["score"]="ok"
  else
    LZY_TASK_STATUS["score"]="fail"
    lzy_warn "评分失败，不影响已采集结果"
  fi
  return 0
}

lzy_write_summary() {
  local out="${LZY_RUN_DIR}/summary.json"
  local modules_json="["
  local first=1
  local m status
  local order=(system cpu memory disk network route streaming docker wordpress score)
  declare -A lzy_sum_seen=()

  for m in "${order[@]}"; do
    if [[ -n "${LZY_TASK_STATUS[${m}]+x}" ]]; then
      status="${LZY_TASK_STATUS[${m}]}"
      if [[ ${first} -eq 1 ]]; then first=0; else modules_json+=","; fi
      modules_json+="{\"name\":\"$(lzy_json_escape "${m}")\",\"status\":\"$(lzy_json_escape "${status}")\"}"
      lzy_sum_seen["${m}"]=1
    fi
  done
  for m in "${!LZY_TASK_STATUS[@]}"; do
    [[ -n "${lzy_sum_seen[${m}]+x}" ]] && continue
    status="${LZY_TASK_STATUS[${m}]}"
    if [[ ${first} -eq 1 ]]; then first=0; else modules_json+=","; fi
    modules_json+="{\"name\":\"$(lzy_json_escape "${m}")\",\"status\":\"$(lzy_json_escape "${status}")\"}"
  done
  modules_json+="]"

  cat >"${out}" <<EOF
{
  "run_id": "$(lzy_json_escape "${LZY_RUN_ID}")",
  "finished_at": "$(lzy_now_iso)",
  "modules": ${modules_json},
  "results_dir": "$(lzy_json_escape "${LZY_RUN_DIR}")"
}
EOF
  lzy_ok "汇总已写入: ${out}"
}
