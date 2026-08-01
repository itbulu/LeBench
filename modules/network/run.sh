#!/usr/bin/env bash
# modules/network/run.sh - speedtest + China ISP ping + 三网下载测速

_lzy_ping_avg() {
  local host="$1"
  local count="${LZY_NET_PING_COUNT:-4}"
  if [[ -z "${host}" ]]; then
    echo ""
    return 1
  fi
  local out
  out="$(ping -c "${count}" -W 3 "${host}" 2>&1)" || true
  echo "${out}" >>"$(lzy_log_file network)"
  echo "${out}" | awk -F'/' '/rtt|round-trip/{print $5; exit}'
}

_lzy_speedtest() {
  local raw=""
  if lzy_require_cmd speedtest; then
    if raw="$(speedtest --accept-license --accept-gdpr -f json 2>/dev/null)"; then
      echo "${raw}"
      return 0
    fi
    raw="$(speedtest --accept-license --accept-gdpr 2>&1)" || true
    echo "${raw}" >>"$(lzy_log_file network)"
    echo "TEXT:${raw}"
    return 0
  fi
  if lzy_require_cmd speedtest-cli; then
    if raw="$(speedtest-cli --json 2>/dev/null)"; then
      echo "${raw}"
      return 0
    fi
    raw="$(speedtest-cli --simple 2>&1)" || true
    echo "${raw}" >>"$(lzy_log_file network)"
    echo "TEXT:${raw}"
    return 0
  fi
  return 1
}

# Download speed via curl (bytes/sec -> Mbps). Empty url => skip.
_lzy_dl_mbps() {
  local url="$1"
  local max_time="${LZY_NET_CN_DL_TIMEOUT:-25}"
  if [[ -z "${url}" ]] || ! lzy_require_cmd curl; then
    echo ""
    return 1
  fi
  local speed http_code
  # speed_download is bytes/sec average
  local out
  out="$(curl -4 -L -o /dev/null -sS \
    -w '%{http_code} %{speed_download}' \
    --connect-timeout 8 \
    --max-time "${max_time}" \
    "${url}" 2>/dev/null || echo '000 0')"
  echo "DL ${url} => ${out}" >>"$(lzy_log_file network)"
  http_code="$(echo "${out}" | awk '{print $1}')"
  speed="$(echo "${out}" | awk '{print $2}')"
  if [[ "${http_code}" != 2* && "${http_code}" != 3* ]]; then
    echo ""
    return 1
  fi
  awk -v s="${speed:-0}" 'BEGIN{
    if (s+0 <= 0) { print ""; exit }
    printf "%.2f", s*8/1000000
  }'
}

lzy_module_network() {
  local out="${LZY_RUN_DIR}/network.json"
  lzy_log_info "开始网络测试"

  local status="ok" error=""
  local ping_ms="" download_mbps="" upload_mbps="" server_name="" isp=""
  local st_status="skip"

  if [[ "${LZY_NET_SPEEDTEST:-1}" == "1" ]]; then
    lzy_info "执行 Speedtest"
    local st_raw
    if st_raw="$(_lzy_speedtest)"; then
      echo "${st_raw}" >>"$(lzy_log_file network)"
      if [[ "${st_raw}" == TEXT:* ]]; then
        st_status="ok"
        download_mbps="$(echo "${st_raw}" | grep -i Download | grep -oE '[0-9.]+' | head -1)"
        upload_mbps="$(echo "${st_raw}" | grep -i Upload | grep -oE '[0-9.]+' | head -1)"
        ping_ms="$(echo "${st_raw}" | grep -i Ping | grep -oE '[0-9.]+' | head -1)"
      elif lzy_has_jq && [[ "${st_raw}" == \{* ]]; then
        st_status="ok"
        download_mbps="$(echo "${st_raw}" | jq -r '
          if .download.bandwidth then (.download.bandwidth * 8 / 1000000)
          elif .download then (.download / 1000000)
          else empty end
        ' 2>/dev/null | awk '{printf "%.2f", $1}')"
        upload_mbps="$(echo "${st_raw}" | jq -r '
          if .upload.bandwidth then (.upload.bandwidth * 8 / 1000000)
          elif .upload then (.upload / 1000000)
          else empty end
        ' 2>/dev/null | awk '{printf "%.2f", $1}')"
        ping_ms="$(echo "${st_raw}" | jq -r '.ping.latency // .ping // empty' 2>/dev/null)"
        server_name="$(echo "${st_raw}" | jq -r '.server.name // .server.host // empty' 2>/dev/null)"
        isp="$(echo "${st_raw}" | jq -r '.isp // .client.isp // empty' 2>/dev/null)"
      else
        st_status="ok"
      fi
      printf '%s\n' "${st_raw}" >"${LZY_RUN_DIR}/speedtest_raw.json" 2>/dev/null || true
    else
      st_status="skip"
      error="speedtest not available"
      lzy_warn "${error}"
    fi
  fi

  # China ISP pings
  lzy_info "三网 Ping 探测"
  local ping_ct ping_cu ping_cm
  ping_ct="$(_lzy_ping_avg "${LZY_NET_PING_CT:-}")"
  ping_cu="$(_lzy_ping_avg "${LZY_NET_PING_CU:-}")"
  ping_cm="$(_lzy_ping_avg "${LZY_NET_PING_CM:-}")"

  # China download speed (curl) — configurable mirrors / CDN nodes
  local cn_ct_mbps="" cn_cu_mbps="" cn_cm_mbps="" cn_intl_mbps=""
  local url_ct="${LZY_NET_DL_CT_URL:-https://mirrors.cloud.tencent.com/ubuntu/ls-lR.gz}"
  local url_cu="${LZY_NET_DL_CU_URL:-https://mirrors.aliyun.com/ubuntu/ls-lR.gz}"
  local url_cm="${LZY_NET_DL_CM_URL:-https://mirrors.tuna.tsinghua.edu.cn/ubuntu/ls-lR.gz}"
  local url_intl="${LZY_NET_DL_INTL_URL:-https://speed.cloudflare.com/__down?bytes=25000000}"

  if [[ "${LZY_NET_CN_SPEED:-1}" == "1" ]]; then
    lzy_info "三网 / CDN 下载测速（curl，可配置 URL）"
    lzy_info "  电信节点: ${url_ct}"
    cn_ct_mbps="$(_lzy_dl_mbps "${url_ct}" || true)"
    lzy_info "  联通节点: ${url_cu}"
    cn_cu_mbps="$(_lzy_dl_mbps "${url_cu}" || true)"
    lzy_info "  移动节点: ${url_cm}"
    cn_cm_mbps="$(_lzy_dl_mbps "${url_cm}" || true)"
    if [[ -n "${url_intl}" ]]; then
      lzy_info "  国际基准: ${url_intl}"
      cn_intl_mbps="$(_lzy_dl_mbps "${url_intl}" || true)"
    fi
    lzy_info "三网下载 Mbps: CT=${cn_ct_mbps:-n/a} CU=${cn_cu_mbps:-n/a} CM=${cn_cm_mbps:-n/a} INTL=${cn_intl_mbps:-n/a}"
  fi

  cat >"${out}" <<EOF
{
  "module": "network",
  "status": "${status}",
  "timestamp": "$(lzy_now_iso)",
  "error": "$(lzy_json_escape "${error}")",
  "speedtest": {
    "status": "${st_status}",
    "ping_ms": $(lzy_json_num_or_null "${ping_ms}"),
    "download_mbps": $(lzy_json_num_or_null "${download_mbps}"),
    "upload_mbps": $(lzy_json_num_or_null "${upload_mbps}"),
    "server": "$(lzy_json_escape "${server_name}")",
    "isp": "$(lzy_json_escape "${isp}")"
  },
  "china_ping": {
    "telecom_ms": $(lzy_json_num_or_null "${ping_ct}"),
    "unicom_ms": $(lzy_json_num_or_null "${ping_cu}"),
    "mobile_ms": $(lzy_json_num_or_null "${ping_cm}"),
    "targets": {
      "telecom": "$(lzy_json_escape "${LZY_NET_PING_CT:-}")",
      "unicom": "$(lzy_json_escape "${LZY_NET_PING_CU:-}")",
      "mobile": "$(lzy_json_escape "${LZY_NET_PING_CM:-}")"
    }
  },
  "china_download": {
    "enabled": $( [[ "${LZY_NET_CN_SPEED:-1}" == "1" ]] && echo true || echo false ),
    "telecom_mbps": $(lzy_json_num_or_null "${cn_ct_mbps}"),
    "unicom_mbps": $(lzy_json_num_or_null "${cn_cu_mbps}"),
    "mobile_mbps": $(lzy_json_num_or_null "${cn_cm_mbps}"),
    "intl_mbps": $(lzy_json_num_or_null "${cn_intl_mbps}"),
    "urls": {
      "telecom": "$(lzy_json_escape "${url_ct}")",
      "unicom": "$(lzy_json_escape "${url_cu}")",
      "mobile": "$(lzy_json_escape "${url_cm}")",
      "intl": "$(lzy_json_escape "${url_intl}")"
    },
    "note": "curl download average Mbps; override LZY_NET_DL_*_URL for true ISP nodes"
  }
}
EOF

  lzy_info "已写入 ${out}"
  return 0
}
