#!/usr/bin/env bash
# scoring/score.sh - automatic scoring engine (no manual scores)
# shellcheck disable=SC2034

# Reference baselines for 10-point scale (tunable via config)
# Values at or above ref => 10; linear scale down to 0.

_lzy_clamp10() {
  awk -v v="$1" 'BEGIN{
    if (v < 0) v=0;
    if (v > 10) v=10;
    printf "%.1f", v
  }'
}

_lzy_ratio_score() {
  # value / ref * 10, clamped
  local value="$1" ref="$2"
  if [[ -z "${value}" || "${value}" == "null" || -z "${ref}" || "${ref}" == "0" ]]; then
    echo ""
    return 1
  fi
  awk -v v="${value}" -v r="${ref}" 'BEGIN{
    if (r <= 0) { print ""; exit }
    s = (v / r) * 10;
    if (s < 0) s=0;
    if (s > 10) s=10;
    printf "%.1f", s
  }'
}

_lzy_inverse_score() {
  # lower is better (e.g. ping): score = 10 * ref / value
  local value="$1" ref="$2"
  if [[ -z "${value}" || "${value}" == "null" || -z "${ref}" ]]; then
    echo ""
    return 1
  fi
  awk -v v="${value}" -v r="${ref}" 'BEGIN{
    if (v <= 0) { print "10.0"; exit }
    s = (r / v) * 10;
    if (s < 0) s=0;
    if (s > 10) s=10;
    printf "%.1f", s
  }'
}

_lzy_json_get() {
  local file="$1" query="$2"
  if [[ ! -f "${file}" ]]; then
    echo ""
    return 1
  fi
  if lzy_has_jq; then
    jq -r "${query} // empty" "${file}" 2>/dev/null
  else
    echo ""
    return 1
  fi
}

_lzy_score_cpu() {
  local f="${LZY_RUN_DIR}/cpu.json"
  local multi single s1 s2
  multi="$(_lzy_json_get "${f}" '.sysbench.multi_eps')"
  single="$(_lzy_json_get "${f}" '.sysbench.single_eps')"
  local ref_multi="${LZY_SCORE_REF_CPU_MULTI:-8000}"
  local ref_single="${LZY_SCORE_REF_CPU_SINGLE:-2000}"
  s1="$(_lzy_ratio_score "${multi}" "${ref_multi}" || true)"
  s2="$(_lzy_ratio_score "${single}" "${ref_single}" || true)"
  if [[ -n "${s1}" && -n "${s2}" ]]; then
    awk -v a="${s1}" -v b="${s2}" 'BEGIN{printf "%.1f", a*0.6+b*0.4}'
  elif [[ -n "${s1}" ]]; then
    echo "${s1}"
  elif [[ -n "${s2}" ]]; then
    echo "${s2}"
  else
    echo ""
  fi
}

_lzy_score_memory() {
  local f="${LZY_RUN_DIR}/memory.json"
  local rb wb s1 s2
  rb="$(_lzy_json_get "${f}" '.read.mib_per_sec')"
  wb="$(_lzy_json_get "${f}" '.write.mib_per_sec')"
  local ref="${LZY_SCORE_REF_MEM_MIB:-8000}"
  s1="$(_lzy_ratio_score "${rb}" "${ref}" || true)"
  s2="$(_lzy_ratio_score "${wb}" "${ref}" || true)"
  if [[ -n "${s1}" && -n "${s2}" ]]; then
    awk -v a="${s1}" -v b="${s2}" 'BEGIN{printf "%.1f", (a+b)/2}'
  elif [[ -n "${s1}" ]]; then
    echo "${s1}"
  elif [[ -n "${s2}" ]]; then
    echo "${s2}"
  else
    echo ""
  fi
}

_lzy_score_disk() {
  local f="${LZY_RUN_DIR}/disk.json"
  local sr sw ri wi ddr ddw
  sr="$(_lzy_json_get "${f}" '.sequential.read_mib_s')"
  sw="$(_lzy_json_get "${f}" '.sequential.write_mib_s')"
  ri="$(_lzy_json_get "${f}" '.random.read_iops')"
  wi="$(_lzy_json_get "${f}" '.random.write_iops')"
  ddr="$(_lzy_json_get "${f}" '.dd.read_mib_s')"
  ddw="$(_lzy_json_get "${f}" '.dd.write_mib_s')"
  local ref_seq="${LZY_SCORE_REF_DISK_SEQ:-500}"
  local ref_iops="${LZY_SCORE_REF_DISK_IOPS:-20000}"
  local a b c d e fsc n=0 sum=0
  a="$(_lzy_ratio_score "${sr}" "${ref_seq}" || true)"
  b="$(_lzy_ratio_score "${sw}" "${ref_seq}" || true)"
  c="$(_lzy_ratio_score "${ri}" "${ref_iops}" || true)"
  d="$(_lzy_ratio_score "${wi}" "${ref_iops}" || true)"
  e="$(_lzy_ratio_score "${ddr}" "${ref_seq}" || true)"
  fsc="$(_lzy_ratio_score "${ddw}" "${ref_seq}" || true)"
  for x in "${a}" "${b}" "${c}" "${d}" "${e}" "${fsc}"; do
    if [[ -n "${x}" ]]; then
      sum="$(awk -v s="${sum}" -v v="${x}" 'BEGIN{print s+v}')"
      n=$((n + 1))
    fi
  done
  if [[ ${n} -eq 0 ]]; then
    echo ""
  else
    awk -v s="${sum}" -v n="${n}" 'BEGIN{printf "%.1f", s/n}'
  fi
}

_lzy_score_network() {
  local f="${LZY_RUN_DIR}/network.json"
  local dl ul ping ct cu cm
  dl="$(_lzy_json_get "${f}" '.speedtest.download_mbps')"
  ul="$(_lzy_json_get "${f}" '.speedtest.upload_mbps')"
  ping="$(_lzy_json_get "${f}" '.speedtest.ping_ms')"
  ct="$(_lzy_json_get "${f}" '.china_download.telecom_mbps')"
  cu="$(_lzy_json_get "${f}" '.china_download.unicom_mbps')"
  cm="$(_lzy_json_get "${f}" '.china_download.mobile_mbps')"
  local ref_dl="${LZY_SCORE_REF_NET_DL:-1000}"
  local ref_ul="${LZY_SCORE_REF_NET_UL:-500}"
  local ref_ping="${LZY_SCORE_REF_NET_PING:-20}"
  local ref_cn="${LZY_SCORE_REF_NET_CN_DL:-500}"
  local a b c d e f n=0 sum=0
  a="$(_lzy_ratio_score "${dl}" "${ref_dl}" || true)"
  b="$(_lzy_ratio_score "${ul}" "${ref_ul}" || true)"
  c="$(_lzy_inverse_score "${ping}" "${ref_ping}" || true)"
  d="$(_lzy_ratio_score "${ct}" "${ref_cn}" || true)"
  e="$(_lzy_ratio_score "${cu}" "${ref_cn}" || true)"
  f="$(_lzy_ratio_score "${cm}" "${ref_cn}" || true)"
  for x in "${a}" "${b}" "${c}" "${d}" "${e}" "${f}"; do
    if [[ -n "${x}" ]]; then
      sum="$(awk -v s="${sum}" -v v="${x}" 'BEGIN{print s+v}')"
      n=$((n + 1))
    fi
  done
  if [[ ${n} -eq 0 ]]; then
    echo ""
  else
    awk -v s="${sum}" -v n="${n}" 'BEGIN{printf "%.1f", s/n}'
  fi
}

_lzy_score_route() {
  local f="${LZY_RUN_DIR}/route.json"
  local s ipq
  s="$(_lzy_json_get "${f}" '.summary.score')"
  ipq="$(_lzy_json_get "${LZY_RUN_DIR}/ipquality.json" '.summary.score')"
  if [[ -n "${s}" && "${s}" != "null" && -n "${ipq}" && "${ipq}" != "null" ]]; then
    awk -v a="${s}" -v b="${ipq}" 'BEGIN{printf "%.1f", (a*0.7+b*0.3)}'
  elif [[ -n "${s}" && "${s}" != "null" ]]; then
    _lzy_clamp10 "${s}"
  elif [[ -n "${ipq}" && "${ipq}" != "null" ]]; then
    _lzy_clamp10 "${ipq}"
  else
    echo ""
  fi
}

_lzy_score_application() {
  local f="${LZY_RUN_DIR}/application.json"
  if [[ ! -f "${f}" ]]; then
    echo ""
    return 1
  fi

  local d_st w_st
  d_st="$(_lzy_json_get "${f}" '.docker.status')"
  w_st="$(_lzy_json_get "${f}" '.wordpress.status')"

  # Lower is better for all timing metrics
  local scores=() s

  if [[ "${d_st}" == "ok" ]]; then
    local nginx redis mysql
    nginx="$(_lzy_json_get "${f}" '.docker.nginx_start_ms')"
    redis="$(_lzy_json_get "${f}" '.docker.redis_start_ms')"
    mysql="$(_lzy_json_get "${f}" '.docker.mysql_start_ms')"
    local ref_nginx="${LZY_SCORE_REF_DOCKER_NGINX_MS:-15000}"
    local ref_redis="${LZY_SCORE_REF_DOCKER_REDIS_MS:-10000}"
    local ref_mysql="${LZY_SCORE_REF_DOCKER_MYSQL_MS:-45000}"
    s="$(_lzy_inverse_score "${nginx}" "${ref_nginx}" || true)"
    [[ -n "${s}" ]] && scores+=("${s}")
    s="$(_lzy_inverse_score "${redis}" "${ref_redis}" || true)"
    [[ -n "${s}" ]] && scores+=("${s}")
    s="$(_lzy_inverse_score "${mysql}" "${ref_mysql}" || true)"
    [[ -n "${s}" ]] && scores+=("${s}")
  fi

  if [[ "${w_st}" == "ok" ]]; then
    local deploy ttfb total
    deploy="$(_lzy_json_get "${f}" '.wordpress.deploy_ms')"
    ttfb="$(_lzy_json_get "${f}" '.wordpress.ttfb_ms')"
    total="$(_lzy_json_get "${f}" '.wordpress.total_ms')"
    local ref_deploy="${LZY_SCORE_REF_WP_DEPLOY_MS:-90000}"
    local ref_ttfb="${LZY_SCORE_REF_TTFB:-200}"
    local ref_total="${LZY_SCORE_REF_WP_TOTAL_MS:-500}"
    s="$(_lzy_inverse_score "${deploy}" "${ref_deploy}" || true)"
    [[ -n "${s}" ]] && scores+=("${s}")
    s="$(_lzy_inverse_score "${ttfb}" "${ref_ttfb}" || true)"
    [[ -n "${s}" ]] && scores+=("${s}")
    s="$(_lzy_inverse_score "${total}" "${ref_total}" || true)"
    [[ -n "${s}" ]] && scores+=("${s}")
  fi

  if [[ ${#scores[@]} -eq 0 ]]; then
    echo ""
    return 1
  fi

  local sum=0 n=0 x
  for x in "${scores[@]}"; do
    sum="$(awk -v s="${sum}" -v v="${x}" 'BEGIN{print s+v}')"
    n=$((n + 1))
  done
  awk -v s="${sum}" -v n="${n}" 'BEGIN{printf "%.1f", s/n}'
}

_lzy_score_price() {
  # Optional: LZY_PRICE monthly USD; lower better. Ref = LZY_SCORE_REF_PRICE (default 5)
  local price="${LZY_PRICE:-}"
  if [[ -z "${price}" ]]; then
    echo ""
    return 1
  fi
  _lzy_inverse_score "${price}" "${LZY_SCORE_REF_PRICE:-5}"
}

_lzy_score_streaming_bonus() {
  # Soft bonus folded into network? Keep separate note only; not in PRD weights.
  # Could mildly boost route — skip for purity.
  true
}

lzy_run_scoring() {
  local out="${LZY_RUN_DIR}/score.json"
  lzy_info "计算综合评分..."

  local cpu mem disk net route app price
  cpu="$(_lzy_score_cpu)"
  mem="$(_lzy_score_memory)"
  disk="$(_lzy_score_disk)"
  net="$(_lzy_score_network)"
  route="$(_lzy_score_route)"
  app="$(_lzy_score_application)"
  price="$(_lzy_score_price || true)"

  local w_cpu="${LZY_WEIGHT_CPU:-20}"
  local w_mem="${LZY_WEIGHT_MEMORY:-10}"
  local w_disk="${LZY_WEIGHT_DISK:-20}"
  local w_net="${LZY_WEIGHT_NETWORK:-20}"
  local w_route="${LZY_WEIGHT_ROUTE:-10}"
  local w_app="${LZY_WEIGHT_APPLICATION:-10}"
  local w_price="${LZY_WEIGHT_PRICE:-10}"

  # Renormalize: drop weights for missing dimensions
  local items=()
  [[ -n "${cpu}" ]] && items+=("cpu:${cpu}:${w_cpu}")
  [[ -n "${mem}" ]] && items+=("memory:${mem}:${w_mem}")
  [[ -n "${disk}" ]] && items+=("disk:${disk}:${w_disk}")
  [[ -n "${net}" ]] && items+=("network:${net}:${w_net}")
  [[ -n "${route}" ]] && items+=("route:${route}:${w_route}")
  [[ -n "${app}" ]] && items+=("application:${app}:${w_app}")
  [[ -n "${price}" ]] && items+=("price:${price}:${w_price}")

  local overall="" tw=0 weighted=0
  local name score weight rest
  local details="{"
  local first=1
  local item

  if [[ ${#items[@]} -eq 0 ]]; then
    cat >"${out}" <<EOF
{
  "module": "score",
  "status": "skip",
  "error": "no scorable metrics",
  "timestamp": "$(lzy_now_iso)",
  "overall": null
}
EOF
    lzy_warn "无可用指标，跳过评分"
    return 0
  fi

  for item in "${items[@]}"; do
    name="${item%%:*}"
    rest="${item#*:}"
    score="${rest%%:*}"
    weight="${rest##*:}"
    tw=$((tw + weight))
    weighted="$(awk -v w="${weighted}" -v s="${score}" -v wt="${weight}" 'BEGIN{print w + s*wt}')"
    if [[ ${first} -eq 1 ]]; then first=0; else details+=","; fi
    details+="\"${name}\":${score}"
  done
  details+="}"

  overall="$(awk -v w="${weighted}" -v t="${tw}" 'BEGIN{printf "%.1f", w/t}')"

  local w_cpu_out w_mem_out w_disk_out w_net_out w_route_out w_app_out w_price_out
  [[ -n "${cpu}" ]] && w_cpu_out="${w_cpu}" || w_cpu_out="null"
  [[ -n "${mem}" ]] && w_mem_out="${w_mem}" || w_mem_out="null"
  [[ -n "${disk}" ]] && w_disk_out="${w_disk}" || w_disk_out="null"
  [[ -n "${net}" ]] && w_net_out="${w_net}" || w_net_out="null"
  [[ -n "${route}" ]] && w_route_out="${w_route}" || w_route_out="null"
  [[ -n "${app}" ]] && w_app_out="${w_app}" || w_app_out="null"
  [[ -n "${price}" ]] && w_price_out="${w_price}" || w_price_out="null"

  local price_out="null"
  [[ -n "${LZY_PRICE:-}" ]] && price_out="${LZY_PRICE}"

  cat >"${out}" <<EOF
{
  "module": "score",
  "status": "ok",
  "timestamp": "$(lzy_now_iso)",
  "overall": ${overall},
  "scores": ${details},
  "weights_used": {
    "cpu": ${w_cpu_out},
    "memory": ${w_mem_out},
    "disk": ${w_disk_out},
    "network": ${w_net_out},
    "route": ${w_route_out},
    "application": ${w_app_out},
    "price": ${w_price_out}
  },
  "na": {
    "cpu": $( [[ -z "${cpu}" ]] && echo true || echo false ),
    "memory": $( [[ -z "${mem}" ]] && echo true || echo false ),
    "disk": $( [[ -z "${disk}" ]] && echo true || echo false ),
    "network": $( [[ -z "${net}" ]] && echo true || echo false ),
    "route": $( [[ -z "${route}" ]] && echo true || echo false ),
    "application": $( [[ -z "${app}" ]] && echo true || echo false ),
    "price": $( [[ -z "${price}" ]] && echo true || echo false )
  },
  "method": "linear_normalize_against_refs_then_weighted_average",
  "price_input": ${price_out}
}
EOF

  lzy_ok "综合评分: ${overall}/10 → ${out}"
  return 0
}
