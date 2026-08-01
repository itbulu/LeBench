#!/usr/bin/env bash
# modules/streaming/run.sh - streaming / AI unlock heuristic checks (curl-based)

_lzy_curl_code() {
  # Print HTTP code; body discarded unless LZY_STREAM_DEBUG=1
  local url="$1"
  shift
  local code
  code="$(curl -4 -sS -o /tmp/lzy-stream-body.txt -w '%{http_code}' \
    --connect-timeout "${LZY_STREAM_TIMEOUT:-8}" \
    --max-time "${LZY_STREAM_TIMEOUT:-8}" \
    -A 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36' \
    "$@" "${url}" 2>/dev/null || echo "000")"
  if [[ "${LZY_STREAM_DEBUG:-0}" == "1" ]]; then
    echo "URL=${url} CODE=${code}" >>"$(lzy_log_file streaming)"
    head -c 500 /tmp/lzy-stream-body.txt >>"$(lzy_log_file streaming)" 2>/dev/null || true
    echo "" >>"$(lzy_log_file streaming)"
  fi
  printf '%s' "${code}"
}

_lzy_curl_body() {
  cat /tmp/lzy-stream-body.txt 2>/dev/null || true
}

_lzy_stream_result() {
  # name status detail
  printf '%s\t%s\t%s\n' "$1" "$2" "$3"
}

# Netflix — CDN self-check style
_lzy_check_netflix() {
  local code body
  code="$(_lzy_curl_code 'https://www.netflix.com/title/81280792')"
  body="$(_lzy_curl_body)"
  if [[ "${code}" == "000" ]]; then
    _lzy_stream_result "Netflix" "fail" "connection failed"
    return
  fi
  if echo "${body}" | grep -qiE 'Not Available|unavailable|不在您目前所在的国家'; then
    _lzy_stream_result "Netflix" "no" "geo restricted"
  elif [[ "${code}" == 2* || "${code}" == 3* ]]; then
    _lzy_stream_result "Netflix" "yes" "http ${code}"
  else
    _lzy_stream_result "Netflix" "unknown" "http ${code}"
  fi
}

_lzy_check_disney() {
  local code body
  code="$(_lzy_curl_code 'https://www.disneyplus.com')"
  body="$(_lzy_curl_body)"
  if [[ "${code}" == "000" ]]; then
    _lzy_stream_result "Disney+" "fail" "connection failed"
    return
  fi
  if echo "${body}" | grep -qiE 'not available|unavailable in your|目前无法'; then
    _lzy_stream_result "Disney+" "no" "geo restricted"
  elif [[ "${code}" == 2* || "${code}" == 3* ]]; then
    _lzy_stream_result "Disney+" "yes" "http ${code}"
  else
    _lzy_stream_result "Disney+" "unknown" "http ${code}"
  fi
}

_lzy_check_openai() {
  local code body
  code="$(_lzy_curl_code 'https://chatgpt.com' -L)"
  body="$(_lzy_curl_body)"
  if [[ "${code}" == "000" ]]; then
    # fallback api
    code="$(_lzy_curl_code 'https://api.openai.com/v1/models')"
    body="$(_lzy_curl_body)"
  fi
  if [[ "${code}" == "000" ]]; then
    _lzy_stream_result "OpenAI" "fail" "connection failed"
    return
  fi
  if echo "${body}" | grep -qiE 'unsupported_country|not available in your country|Access denied'; then
    _lzy_stream_result "OpenAI" "no" "geo/restricted"
  elif [[ "${code}" == "403" ]]; then
    _lzy_stream_result "OpenAI" "no" "http 403"
  elif [[ "${code}" == 2* || "${code}" == 3* ]]; then
    _lzy_stream_result "OpenAI" "yes" "http ${code}"
  else
    _lzy_stream_result "OpenAI" "unknown" "http ${code}"
  fi
}

_lzy_check_claude() {
  local code body
  code="$(_lzy_curl_code 'https://claude.ai' -L)"
  body="$(_lzy_curl_body)"
  if [[ "${code}" == "000" ]]; then
    _lzy_stream_result "Claude" "fail" "connection failed"
    return
  fi
  if echo "${body}" | grep -qiE 'not available|unavailable|unsupported|Access denied'; then
    _lzy_stream_result "Claude" "no" "restricted"
  elif [[ "${code}" == "403" ]]; then
    _lzy_stream_result "Claude" "no" "http 403"
  elif [[ "${code}" == 2* || "${code}" == 3* ]]; then
    _lzy_stream_result "Claude" "yes" "http ${code}"
  else
    _lzy_stream_result "Claude" "unknown" "http ${code}"
  fi
}

_lzy_check_gemini() {
  local code body
  code="$(_lzy_curl_code 'https://gemini.google.com' -L)"
  body="$(_lzy_curl_body)"
  if [[ "${code}" == "000" ]]; then
    _lzy_stream_result "Gemini" "fail" "connection failed"
    return
  fi
  if echo "${body}" | grep -qiE 'not available|unavailable|CountryNotSupported'; then
    _lzy_stream_result "Gemini" "no" "restricted"
  elif [[ "${code}" == 2* || "${code}" == 3* ]]; then
    _lzy_stream_result "Gemini" "yes" "http ${code}"
  else
    _lzy_stream_result "Gemini" "unknown" "http ${code}"
  fi
}

_lzy_check_tiktok() {
  local code body
  code="$(_lzy_curl_code 'https://www.tiktok.com' -L)"
  body="$(_lzy_curl_body)"
  if [[ "${code}" == "000" ]]; then
    _lzy_stream_result "TikTok" "fail" "connection failed"
    return
  fi
  if echo "${body}" | grep -qiE 'is not available|not available in your'; then
    _lzy_stream_result "TikTok" "no" "geo restricted"
  elif [[ "${code}" == 2* || "${code}" == 3* ]]; then
    _lzy_stream_result "TikTok" "yes" "http ${code}"
  else
    _lzy_stream_result "TikTok" "unknown" "http ${code}"
  fi
}

_lzy_check_youtube() {
  local code body
  code="$(_lzy_curl_code 'https://www.youtube.com' -L)"
  body="$(_lzy_curl_body)"
  if [[ "${code}" == "000" ]]; then
    _lzy_stream_result "YouTube" "fail" "connection failed"
    return
  fi
  if echo "${body}" | grep -qiE 'not available|unusual traffic|consent\.youtube'; then
    # consent page still means reachable
    if echo "${body}" | grep -qiE 'not available in your country|is not available'; then
      _lzy_stream_result "YouTube" "no" "geo restricted"
    else
      _lzy_stream_result "YouTube" "yes" "http ${code}"
    fi
  elif [[ "${code}" == 2* || "${code}" == 3* ]]; then
    _lzy_stream_result "YouTube" "yes" "http ${code}"
  else
    _lzy_stream_result "YouTube" "unknown" "http ${code}"
  fi
}

_lzy_check_twitter() {
  local code body
  code="$(_lzy_curl_code 'https://twitter.com' -L)"
  body="$(_lzy_curl_body)"
  if [[ "${code}" == "000" ]]; then
    code="$(_lzy_curl_code 'https://x.com' -L)"
    body="$(_lzy_curl_body)"
  fi
  if [[ "${code}" == "000" ]]; then
    _lzy_stream_result "Twitter/X" "fail" "connection failed"
    return
  fi
  if [[ "${code}" == "403" ]] || echo "${body}" | grep -qiE 'not available|has been blocked'; then
    _lzy_stream_result "Twitter/X" "no" "restricted"
  elif [[ "${code}" == 2* || "${code}" == 3* ]]; then
    _lzy_stream_result "Twitter/X" "yes" "http ${code}"
  else
    _lzy_stream_result "Twitter/X" "unknown" "http ${code}"
  fi
}

_lzy_check_chatgpt_api() {
  # OpenAI geo via chatgpt CDN/api hint
  local code body
  code="$(_lzy_curl_code 'https://ios.chat.openai.com/cdn-cgi/trace')"
  body="$(_lzy_curl_body)"
  if [[ "${code}" == "000" ]]; then
    _lzy_stream_result "ChatGPT-Trace" "fail" "connection failed"
    return
  fi
  local loc
  loc="$(echo "${body}" | awk -F= '/^loc=/{print $2; exit}')"
  if [[ -n "${loc}" ]]; then
    _lzy_stream_result "ChatGPT-Trace" "yes" "loc=${loc}"
  elif [[ "${code}" == 2* ]]; then
    _lzy_stream_result "ChatGPT-Trace" "yes" "http ${code}"
  else
    _lzy_stream_result "ChatGPT-Trace" "unknown" "http ${code}"
  fi
}

lzy_module_streaming() {
  local out="${LZY_RUN_DIR}/streaming.json"
  lzy_log_info "开始流媒体 / AI 解锁检测"

  if ! lzy_require_cmd curl; then
    cat >"${out}" <<EOF
{
  "module": "streaming",
  "status": "skip",
  "error": "curl not installed",
  "timestamp": "$(lzy_now_iso)"
}
EOF
    return 1
  fi

  local results=()
  local line name status detail
  local yes=0 no=0 fail=0 unknown=0 total=0

  lzy_info "检测 Netflix / Disney+ / YouTube / OpenAI / Claude / Gemini / TikTok / X / ChatGPT-Trace"
  while IFS=$'\t' read -r name status detail; do
    [[ -z "${name}" ]] && continue
    results+=("${name}|${status}|${detail}")
    total=$((total + 1))
    case "${status}" in
      yes) yes=$((yes + 1)) ;;
      no) no=$((no + 1)) ;;
      fail) fail=$((fail + 1)) ;;
      *) unknown=$((unknown + 1)) ;;
    esac
    lzy_info "  ${name}: ${status} (${detail})"
  done < <(
    _lzy_check_netflix
    _lzy_check_disney
    _lzy_check_youtube
    _lzy_check_openai
    _lzy_check_claude
    _lzy_check_gemini
    _lzy_check_tiktok
    _lzy_check_twitter
    _lzy_check_chatgpt_api
  )

  # Build JSON services array
  local services_json="["
  local first=1
  for line in "${results[@]}"; do
    name="${line%%|*}"
    rest="${line#*|}"
    status="${rest%%|*}"
    detail="${rest#*|}"
    if [[ ${first} -eq 1 ]]; then first=0; else services_json+=","; fi
    services_json+="{\"name\":\"$(lzy_json_escape "${name}")\",\"status\":\"$(lzy_json_escape "${status}")\",\"detail\":\"$(lzy_json_escape "${detail}")\"}"
  done
  services_json+="]"

  # Unlock score 0-10: yes count / total * 10 (fail/unknown count as 0)
  local unlock_score="0"
  if [[ ${total} -gt 0 ]]; then
    unlock_score="$(awk -v y="${yes}" -v t="${total}" 'BEGIN{printf "%.1f", (y/t)*10}')"
  fi

  cat >"${out}" <<EOF
{
  "module": "streaming",
  "status": "ok",
  "timestamp": "$(lzy_now_iso)",
  "summary": {
    "total": ${total},
    "yes": ${yes},
    "no": ${no},
    "fail": ${fail},
    "unknown": ${unknown},
    "unlock_score": ${unlock_score}
  },
  "services": ${services_json},
  "notes": "Heuristic HTTP checks only; not equivalent to full app unlock verification."
}
EOF

  rm -f /tmp/lzy-stream-body.txt 2>/dev/null || true
  lzy_info "已写入 ${out}"
  return 0
}
