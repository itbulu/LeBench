#!/usr/bin/env bash
# modules/route/run.sh - return path / ASN / CN2·9929·CMI heuristic detection

# Known ASNs (heuristic labels used by many VPS benches)
# AS4809  China Telecom CN2
# AS9929  China Unicom Premium (CUII)
# AS58453 China Mobile International (CMI)
# AS4134  China Telecom 163 backbone
# AS4837  China Unicom 169
# AS9808  China Mobile

_lzy_route_public_ip() {
  local ip=""
  if lzy_require_cmd curl; then
    ip="$(curl -4 -fsS --max-time 8 https://ifconfig.me 2>/dev/null \
      || curl -4 -fsS --max-time 8 https://api.ipify.org 2>/dev/null \
      || curl -4 -fsS --max-time 8 https://ipv4.icanhazip.com 2>/dev/null \
      || true)"
  fi
  printf '%s' "${ip}"
}

_lzy_route_whois_asn() {
  local ip="$1"
  local raw="" asn="" org=""
  if [[ -z "${ip}" ]] || ! lzy_require_cmd whois; then
    echo ""
    return 1
  fi
  raw="$(whois "${ip}" 2>/dev/null || true)"
  echo "${raw}" >>"$(lzy_log_file route)"
  asn="$(echo "${raw}" | awk 'BEGIN{IGNORECASE=1}
    /^origin:|^OriginAS:|^aut-num:/{
      gsub(/origin:|OriginAS:|aut-num:/,"",$0);
      gsub(/^[ \t]+|[ \t]+$/,"",$0);
      print toupper($0); exit
    }')"
  org="$(echo "${raw}" | awk 'BEGIN{IGNORECASE=1}
    /^OrgName:|^org-name:|^descr:|^owner:/{
      sub(/^[^:]+:[ \t]*/,"",$0); print $0; exit
    }')"
  printf '%s|%s' "${asn}" "${org}"
}

_lzy_route_label_asn() {
  local asn="$1"
  asn="$(echo "${asn}" | tr '[:lower:]' '[:upper:]' | tr -d ' ')"
  case "${asn}" in
    AS4809|*4809*) echo "CN2" ;;
    AS9929|*9929*) echo "CU_9929" ;;
    AS58453|*58453*) echo "CMI" ;;
    AS4134|*4134*) echo "CT_163" ;;
    AS4837|*4837*) echo "CU_169" ;;
    AS9808|*9808*|AS56040|*56040*) echo "CM_BACKBONE" ;;
    *) echo "OTHER" ;;
  esac
}

_lzy_route_trace() {
  # Prefer nexttrace / besttrace if present; fallback traceroute
  local target="$1"
  local max_hops="${LZY_ROUTE_MAX_HOPS:-15}"
  local out=""

  if lzy_require_cmd nexttrace; then
    out="$(nexttrace -M "${target}" 2>&1 | head -n 80)" || true
  elif lzy_require_cmd besttrace; then
    out="$(besttrace -q 1 -g cn "${target}" 2>&1 | head -n 80)" || true
  elif lzy_require_cmd mtr; then
    out="$(mtr -rwzc 1 -n -m "${max_hops}" "${target}" 2>&1 | head -n 80)" || true
  elif lzy_require_cmd traceroute; then
    out="$(traceroute -n -w 2 -q 1 -m "${max_hops}" "${target}" 2>&1 | head -n 80)" || true
  else
    return 1
  fi
  echo "${out}" >>"$(lzy_log_file route)"
  printf '%s' "${out}"
}

_lzy_route_detect_in_trace() {
  local trace="$1"
  local found=()
  echo "${trace}" | grep -qiE 'AS4809|[[:space:]]4809[[:space:]]|cn2' && found+=("CN2")
  echo "${trace}" | grep -qiE 'AS9929|[[:space:]]9929[[:space:]]' && found+=("CU_9929")
  echo "${trace}" | grep -qiE 'AS58453|[[:space:]]58453[[:space:]]|cmi' && found+=("CMI")
  echo "${trace}" | grep -qiE 'AS4134|[[:space:]]4134[[:space:]]' && found+=("CT_163")
  echo "${trace}" | grep -qiE 'AS4837|[[:space:]]4837[[:space:]]' && found+=("CU_169")
  echo "${trace}" | grep -qiE 'AS9808|[[:space:]]9808[[:space:]]' && found+=("CM_BACKBONE")

  # IP-range weak hints (common CN2 edge patterns — best-effort)
  echo "${trace}" | grep -qE '59\.43\.' && found+=("CN2_HINT")
  echo "${trace}" | grep -qE '210\.78\.|219\.158\.' && found+=("CU_HINT")
  echo "${trace}" | grep -qE '223\.120\.|223\.118\.' && found+=("CMI_HINT")

  if [[ ${#found[@]} -eq 0 ]]; then
    echo "UNKNOWN"
  else
    # unique
    printf '%s\n' "${found[@]}" | awk '!a[$0]++' | paste -sd',' -
  fi
}

_lzy_route_quality() {
  # Map detected labels to quality tier + numeric score 0-10
  local labels="$1"
  if echo "${labels}" | grep -q 'CN2'; then
    echo "CN2|9.5"
  elif echo "${labels}" | grep -q 'CU_9929'; then
    echo "CU_9929|9.0"
  elif echo "${labels}" | grep -q 'CMI'; then
    echo "CMI|8.5"
  elif echo "${labels}" | grep -qE 'CN2_HINT'; then
    echo "CN2_HINT|8.0"
  elif echo "${labels}" | grep -qE 'CU_HINT|CMI_HINT'; then
    echo "PREMIUM_HINT|7.5"
  elif echo "${labels}" | grep -qE 'CT_163|CU_169|CM_BACKBONE'; then
    echo "BACKBONE|6.0"
  else
    echo "UNKNOWN|5.0"
  fi
}

lzy_module_route() {
  local out="${LZY_RUN_DIR}/route.json"
  lzy_log_info "开始线路检测"

  local public_ip asn_pair asn org asn_label
  public_ip="$(_lzy_route_public_ip)"
  asn_pair="$(_lzy_route_whois_asn "${public_ip}" || true)"
  asn="${asn_pair%%|*}"
  org="${asn_pair#*|}"
  asn_label="$(_lzy_route_label_asn "${asn}")"

  local t_ct="${LZY_ROUTE_TARGET_CT:-202.97.62.1}"
  local t_cu="${LZY_ROUTE_TARGET_CU:-202.106.196.115}"
  local t_cm="${LZY_ROUTE_TARGET_CM:-221.179.155.161}"

  local trace_ct="" trace_cu="" trace_cm=""
  local label_ct="skip" label_cu="skip" label_cm="skip"

  lzy_info "回程探测 电信目标: ${t_ct}"
  if trace_ct="$(_lzy_route_trace "${t_ct}")"; then
    label_ct="$(_lzy_route_detect_in_trace "${trace_ct}")"
  fi

  lzy_info "回程探测 联通目标: ${t_cu}"
  if trace_cu="$(_lzy_route_trace "${t_cu}")"; then
    label_cu="$(_lzy_route_detect_in_trace "${trace_cu}")"
  fi

  lzy_info "回程探测 移动目标: ${t_cm}"
  if trace_cm="$(_lzy_route_trace "${t_cm}")"; then
    label_cm="$(_lzy_route_detect_in_trace "${trace_cm}")"
  fi

  local all_labels="${asn_label},${label_ct},${label_cu},${label_cm}"
  local quality_pair quality score
  quality_pair="$(_lzy_route_quality "${all_labels}")"
  quality="${quality_pair%%|*}"
  score="${quality_pair##*|}"

  # Persist truncated traces
  mkdir -p "${LZY_RUN_DIR}/traces"
  printf '%s\n' "${trace_ct}" >"${LZY_RUN_DIR}/traces/ct.txt"
  printf '%s\n' "${trace_cu}" >"${LZY_RUN_DIR}/traces/cu.txt"
  printf '%s\n' "${trace_cm}" >"${LZY_RUN_DIR}/traces/cm.txt"

  cat >"${out}" <<EOF
{
  "module": "route",
  "status": "ok",
  "timestamp": "$(lzy_now_iso)",
  "public_ip": "$(lzy_json_escape "${public_ip}")",
  "asn": {
    "number": "$(lzy_json_escape "${asn}")",
    "org": "$(lzy_json_escape "${org}")",
    "label": "$(lzy_json_escape "${asn_label}")"
  },
  "return_path": {
    "telecom": {
      "target": "$(lzy_json_escape "${t_ct}")",
      "labels": "$(lzy_json_escape "${label_ct}")"
    },
    "unicom": {
      "target": "$(lzy_json_escape "${t_cu}")",
      "labels": "$(lzy_json_escape "${label_cu}")"
    },
    "mobile": {
      "target": "$(lzy_json_escape "${t_cm}")",
      "labels": "$(lzy_json_escape "${label_cm}")"
    }
  },
  "summary": {
    "best_guess": "$(lzy_json_escape "${quality}")",
    "score": $(lzy_json_num_or_null "${score}"),
    "notes": "Heuristic ASN/traceroute detection; not a guarantee of peering quality."
  }
}
EOF

  lzy_info "线路推断: ${quality} (score=${score})"
  lzy_info "已写入 ${out}"
  return 0
}
