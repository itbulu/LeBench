#!/usr/bin/env bash
# modules/ipquality/run.sh - IP quality heuristics (inspired by ecs IP checks, self-contained)
# Uses public HTTPS APIs; no third-party shell scripts embedded.

_lzy_ipq_public_ip() {
  local ip=""
  ip="$(curl -4 -fsS --max-time 8 https://api.ipify.org 2>/dev/null \
    || curl -4 -fsS --max-time 8 https://ifconfig.me 2>/dev/null \
    || curl -4 -fsS --max-time 8 https://ipv4.icanhazip.com 2>/dev/null \
    || true)"
  printf '%s' "${ip}"
}

_lzy_ipq_port_open() {
  local host="$1" port="$2" timeout_s="${3:-3}"
  if lzy_require_cmd nc; then
    nc -z -w "${timeout_s}" "${host}" "${port}" >/dev/null 2>&1 && return 0 || return 1
  fi
  # bash /dev/tcp
  if timeout "${timeout_s}" bash -c "echo >/dev/tcp/${host}/${port}" >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

_lzy_ipq_dnsbl() {
  # Reverse IP and query common DNSBLs via dig/host (best-effort)
  local ip="$1"
  local rev a b c d listed=0 checked=0
  IFS=. read -r a b c d <<<"${ip}"
  rev="${d}.${c}.${b}.${a}"
  local zones=("zen.spamhaus.org" "bl.spamcop.net" "dnsbl.sorbs.net")
  local z ans
  local details="["
  local first=1
  for z in "${zones[@]}"; do
    checked=$((checked + 1))
    ans=""
    if lzy_require_cmd dig; then
      ans="$(dig +short +time=2 +tries=1 "${rev}.${z}" A 2>/dev/null | head -1 || true)"
    elif lzy_require_cmd host; then
      ans="$(host -W 2 "${rev}.${z}" 2>/dev/null | awk '/has address/{print $4; exit}' || true)"
    else
      continue
    fi
    local hit="false"
    if [[ -n "${ans}" && "${ans}" =~ ^127\. ]]; then
      hit="true"
      listed=$((listed + 1))
    fi
    if [[ ${first} -eq 1 ]]; then first=0; else details+=","; fi
    details+="{\"zone\":\"${z}\",\"listed\":${hit},\"answer\":\"$(lzy_json_escape "${ans}")\"}"
  done
  details+="]"
  printf '%s|%s|%s' "${listed}" "${checked}" "${details}"
}

lzy_module_ipquality() {
  local out="${LZY_RUN_DIR}/ipquality.json"
  lzy_log_info "开始 IP 质量检测"

  if ! lzy_require_cmd curl; then
    cat >"${out}" <<EOF
{"module":"ipquality","status":"skip","error":"curl not installed","timestamp":"$(lzy_now_iso)"}
EOF
    return 1
  fi

  local ip
  ip="$(_lzy_ipq_public_ip)"
  if [[ -z "${ip}" ]]; then
    cat >"${out}" <<EOF
{"module":"ipquality","status":"fail","error":"cannot detect public IP","timestamp":"$(lzy_now_iso)"}
EOF
    return 1
  fi

  lzy_info "公网 IP: ${ip}"

  # --- ip-api.com (HTTP; fields include proxy/hosting/mobile) ---
  local api_json="" country="" region="" city="" isp="" org="" as_field=""
  local is_mobile="null" is_proxy="null" is_hosting="null"
  api_json="$(curl -4 -fsS --max-time 10 \
    "http://ip-api.com/json/${ip}?fields=status,message,country,regionName,city,isp,org,as,mobile,proxy,hosting,query" \
    2>/dev/null || true)"
  echo "${api_json}" >>"$(lzy_log_file ipquality)"

  if [[ -n "${api_json}" ]] && lzy_has_jq; then
    country="$(echo "${api_json}" | jq -r '.country // empty')"
    region="$(echo "${api_json}" | jq -r '.regionName // empty')"
    city="$(echo "${api_json}" | jq -r '.city // empty')"
    isp="$(echo "${api_json}" | jq -r '.isp // empty')"
    org="$(echo "${api_json}" | jq -r '.org // empty')"
    as_field="$(echo "${api_json}" | jq -r '.as // empty')"
    is_mobile="$(echo "${api_json}" | jq -r 'if .mobile==null then "null" else (.mobile|tostring) end')"
    is_proxy="$(echo "${api_json}" | jq -r 'if .proxy==null then "null" else (.proxy|tostring) end')"
    is_hosting="$(echo "${api_json}" | jq -r 'if .hosting==null then "null" else (.hosting|tostring) end')"
  elif [[ -n "${api_json}" ]]; then
    # crude fallback without jq
    isp="$(echo "${api_json}" | grep -oE '"isp":"[^"]*"' | head -1 | cut -d'"' -f4)"
    org="$(echo "${api_json}" | grep -oE '"org":"[^"]*"' | head -1 | cut -d'"' -f4)"
    as_field="$(echo "${api_json}" | grep -oE '"as":"[^"]*"' | head -1 | cut -d'"' -f4)"
    country="$(echo "${api_json}" | grep -oE '"country":"[^"]*"' | head -1 | cut -d'"' -f4)"
  fi

  # Normalize bool strings for JSON
  _bool_json() {
    local v
    v="$(echo "${1}" | tr '[:upper:]' '[:lower:]')"
    case "${v}" in
      true) echo true ;;
      false) echo false ;;
      *) echo null ;;
    esac
  }
  local mobile_j proxy_j hosting_j
  mobile_j="$(_bool_json "${is_mobile}")"
  proxy_j="$(_bool_json "${is_proxy}")"
  hosting_j="$(_bool_json "${is_hosting}")"

  # Bandwidth / usage type guess
  local bw_type="unknown"
  if [[ "${hosting_j}" == "true" ]]; then
    bw_type="datacenter"
  elif [[ "${mobile_j}" == "true" ]]; then
    bw_type="mobile"
  elif [[ "${proxy_j}" == "true" ]]; then
    bw_type="proxy_vpn"
  elif echo "${org} ${isp}" | grep -qiE 'cloud|vps|hosting|server|datacenter|digitalocean|linode|vultr|aws|azure|gcp|ovh|hetzner|contabo'; then
    bw_type="datacenter"
  elif echo "${org} ${isp}" | grep -qiE 'telecom|unicom|mobile|broadband|comcast|verizon|at&t|bt |orange|residential'; then
    bw_type="isp_residential"
  elif [[ -n "${isp}" || -n "${org}" ]]; then
    bw_type="isp_or_business"
  fi

  # Port 25 (outbound mail) — connect to a public MX-like target is noisy;
  # instead check if local:25 listens OR try connecting outbound to smtp.gmail.com:25 / 587
  local port25="unknown" port587="unknown"
  if _lzy_ipq_port_open "smtp.gmail.com" 25 4; then
    port25="reachable"
  else
    port25="blocked_or_filtered"
  fi
  if _lzy_ipq_port_open "smtp.gmail.com" 587 4; then
    port587="reachable"
  else
    port587="blocked_or_filtered"
  fi

  # DNSBL
  local dnsbl_listed=0 dnsbl_checked=0 dnsbl_details="[]"
  local dnsbl_raw dnsbl_rest
  dnsbl_raw="$(_lzy_ipq_dnsbl "${ip}" || true)"
  if [[ -n "${dnsbl_raw}" ]]; then
    dnsbl_listed="${dnsbl_raw%%|*}"
    dnsbl_rest="${dnsbl_raw#*|}"
    dnsbl_checked="${dnsbl_rest%%|*}"
    dnsbl_details="${dnsbl_rest#*|}"
  fi

  # Score 0-10 (higher = cleaner)
  local score="8.0"
  score="$(awk -v s="${score}" -v proxy="${proxy_j}" -v host="${hosting_j}" -v listed="${dnsbl_listed}" -v p25="${port25}" 'BEGIN{
    if (proxy=="true") s-=3;
    if (listed+0>0) s-= (listed*1.5);
    if (p25=="blocked_or_filtered") s-=0.5;
    if (host=="true") s-=0.5;
    if (s<0) s=0; if (s>10) s=10;
    printf "%.1f", s
  }')"

  local risk="low"
  if awk -v s="${score}" 'BEGIN{exit !(s+0 < 5)}'; then
    risk="high"
  elif awk -v s="${score}" 'BEGIN{exit !(s+0 < 7.5)}'; then
    risk="medium"
  fi

  cat >"${out}" <<EOF
{
  "module": "ipquality",
  "status": "ok",
  "timestamp": "$(lzy_now_iso)",
  "ip": "$(lzy_json_escape "${ip}")",
  "geo": {
    "country": "$(lzy_json_escape "${country}")",
    "region": "$(lzy_json_escape "${region}")",
    "city": "$(lzy_json_escape "${city}")"
  },
  "network": {
    "isp": "$(lzy_json_escape "${isp}")",
    "org": "$(lzy_json_escape "${org}")",
    "as": "$(lzy_json_escape "${as_field}")",
    "mobile": ${mobile_j},
    "proxy": ${proxy_j},
    "hosting": ${hosting_j},
    "bandwidth_type": "$(lzy_json_escape "${bw_type}")"
  },
  "mail": {
    "smtp_25": "$(lzy_json_escape "${port25}")",
    "submission_587": "$(lzy_json_escape "${port587}")",
    "note": "Outbound connect test to smtp.gmail.com; not a full open-relay check"
  },
  "dnsbl": {
    "listed_count": $(lzy_json_num_or_null "${dnsbl_listed}"),
    "checked_count": $(lzy_json_num_or_null "${dnsbl_checked}"),
    "zones": ${dnsbl_details}
  },
  "summary": {
    "score": ${score},
    "risk": "$(lzy_json_escape "${risk}")"
  },
  "notes": "Heuristic multi-source check inspired by common VPS IP quality tests; not legal/compliance advice."
}
EOF

  lzy_info "IP 质量: score=${score} risk=${risk} type=${bw_type}"
  lzy_info "已写入 ${out}"
  return 0
}
