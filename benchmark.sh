#!/usr/bin/env bash
# LZY Bench - LeZaiYun Benchmark Toolkit
# Entry point: ./benchmark.sh [command] [args...]
set -euo pipefail

LZY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export LZY_ROOT

# shellcheck source=/dev/null
source "${LZY_ROOT}/core/common.sh"
# shellcheck source=/dev/null
source "${LZY_ROOT}/core/config.sh"
# shellcheck source=/dev/null
source "${LZY_ROOT}/core/logger.sh"
# shellcheck source=/dev/null
source "${LZY_ROOT}/core/deps.sh"
# shellcheck source=/dev/null
source "${LZY_ROOT}/core/task.sh"
# shellcheck source=/dev/null
source "${LZY_ROOT}/core/report.sh"

lzy_load_config

lzy_usage() {
  cat <<EOF
${LZY_NAME} (${LZY_BRAND}) v${LZY_VERSION}

用法:
  ./benchmark.sh [command]

命令:
  (无参数) / all     运行默认全量评测（含应用测试与评分）
  system             系统信息采集
  cpu                CPU 测试
  memory             内存测试
  disk               磁盘测试
  network            网络测试
  route              线路检测（ASN / CN2 / 9929 / CMI / 带宽类型）
  streaming          流媒体 / AI 解锁检测
  ipquality          IP 质量（代理/机房/DNSBL/邮件端口）
  docker             Docker：Nginx / Redis / MySQL 启动耗时
  wordpress          WordPress Compose（WP+MariaDB+Redis）部署与 TTFB
  score [run_id]     仅对已有结果重新评分并刷新报告
  upload [run_id]    将结果上报到 Platform API（Phase 4）
  report [run_id]    生成 Markdown + HTML 报告（默认最近一次）
  version            显示版本
  help               显示帮助

示例:
  sudo ./benchmark.sh
  sudo ./benchmark.sh ipquality
  sudo ./benchmark.sh docker
  sudo ./benchmark.sh wordpress
  sudo LZY_APP_CLEANUP=0 ./benchmark.sh wordpress
  ./benchmark.sh upload
  ./benchmark.sh report
  ./benchmark.sh version

一键安装:
  bash <(curl -fsSL https://raw.githubusercontent.com/itbulu/LeBench/main/install-run.sh)

理念: Once Test, Multiple Output
EOF
}

lzy_cmd_version() {
  echo "${LZY_NAME} v${LZY_VERSION}"
  echo "Brand: ${LZY_BRAND}"
  echo "Root:  ${LZY_ROOT}"
}

lzy_latest_run_dir() {
  local latest
  latest="$(find "${LZY_RESULTS_DIR}" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort | tail -n 1 || true)"
  printf '%s' "${latest}"
}

lzy_cmd_report() {
  local run_id="${1:-}"
  local run_dir=""
  if [[ -n "${run_id}" ]]; then
    run_dir="${LZY_RESULTS_DIR}/${run_id}"
  else
    run_dir="$(lzy_latest_run_dir)"
  fi
  if [[ -z "${run_dir}" || ! -d "${run_dir}" ]]; then
    lzy_die "未找到评测结果，请先运行 ./benchmark.sh"
  fi
  LZY_RUN_DIR="${run_dir}"
  LZY_RUN_ID="$(basename "${run_dir}")"
  export LZY_RUN_DIR LZY_RUN_ID
  lzy_report_all "${run_dir}"
  lzy_ok "Markdown: ${LZY_REPORTS_DIR}/${LZY_RUN_ID}/report.md"
  lzy_ok "HTML:     ${LZY_REPORTS_DIR}/${LZY_RUN_ID}/report.html"
}

lzy_cmd_run() {
  local modules=("$@")
  if [[ ${#modules[@]} -eq 0 ]]; then
    # shellcheck disable=SC2206
    modules=(${LZY_DEFAULT_MODULES})
  fi

  # report / version do not need root; tests usually do
  lzy_check_root "${modules[*]}"
  lzy_run_init
  lzy_run_modules "${modules[@]}"
  lzy_run_score_engine
  lzy_write_summary
  lzy_report_all "${LZY_RUN_DIR}"
  echo ""
  lzy_ok "全部流程结束。结果: ${LZY_RUN_DIR}"
  lzy_ok "报告: ${LZY_REPORTS_DIR}/${LZY_RUN_ID}/report.md"
  lzy_ok "HTML:  ${LZY_REPORTS_DIR}/${LZY_RUN_ID}/report.html"
}

main() {
  local cmd="${1:-all}"
  shift || true

  case "${cmd}" in
    help|-h|--help)
      lzy_usage
      ;;
    version|-v|--version)
      lzy_cmd_version
      ;;
    report)
      lzy_cmd_report "${1:-}"
      ;;
    score)
      # Re-score latest (or given) run without retesting
      local run_id="${1:-}"
      local run_dir=""
      if [[ -n "${run_id}" ]]; then
        run_dir="${LZY_RESULTS_DIR}/${run_id}"
      else
        run_dir="$(lzy_latest_run_dir)"
      fi
      [[ -d "${run_dir}" ]] || lzy_die "未找到结果目录"
      LZY_RUN_DIR="${run_dir}"
      LZY_RUN_ID="$(basename "${run_dir}")"
      export LZY_RUN_DIR LZY_RUN_ID
      lzy_logger_init
      lzy_run_score_engine
      lzy_report_all "${run_dir}"
      ;;
    upload)
      lzy_cmd_upload "${1:-}"
      ;;
    all)
      lzy_cmd_run
      ;;
    system|cpu|memory|disk|network|route|streaming|ipquality|docker|wordpress)
      lzy_cmd_run "${cmd}"
      ;;
    *)
      lzy_warn "未知命令: ${cmd}"
      lzy_usage
      exit 2
      ;;
  esac
}

lzy_cmd_upload() {
  local run_id="${1:-}"
  local run_dir=""
  if [[ -n "${run_id}" ]]; then
    run_dir="${LZY_RESULTS_DIR}/${run_id}"
  else
    run_dir="$(lzy_latest_run_dir)"
  fi
  [[ -d "${run_dir}" ]] || lzy_die "未找到评测结果，请先运行 ./benchmark.sh"

  local api="${LZY_PLATFORM_API:-http://127.0.0.1:8787}"
  local uploader="${LZY_ROOT}/platform/scripts/upload.py"
  [[ -f "${uploader}" ]] || lzy_die "缺少上报脚本: ${uploader}"

  local py=""
  if command -v python3 >/dev/null 2>&1; then
    py="python3"
  elif command -v python >/dev/null 2>&1; then
    py="python"
  else
    lzy_die "需要 python3 以执行 upload"
  fi

  lzy_info "上报 ${run_dir} → ${api}"
  local args=("${uploader}" "${run_dir}" --api "${api}")
  [[ -n "${LZY_UPLOAD_LABEL:-}" ]] && args+=(--label "${LZY_UPLOAD_LABEL}")
  [[ -n "${LZY_UPLOAD_PROVIDER:-}" ]] && args+=(--provider "${LZY_UPLOAD_PROVIDER}")
  [[ -n "${LZY_UPLOAD_REGION:-}" ]] && args+=(--region "${LZY_UPLOAD_REGION}")
  [[ -n "${LZY_PRICE:-}" ]] && args+=(--price "${LZY_PRICE}")
  [[ -n "${LZY_PLATFORM_TOKEN:-}" ]] && args+=(--token "${LZY_PLATFORM_TOKEN}")

  if ! "${py}" "${args[@]}"; then
    lzy_die "上报失败。请确认 Platform 已启动: cd platform && ./run.sh"
  fi
  lzy_ok "上报完成。打开 Dashboard: ${api}/"
}

main "$@"
