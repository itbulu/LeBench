#!/usr/bin/env bash
# modules/system/run.sh - system information collection

lzy_module_system() {
  local out="${LZY_RUN_DIR}/system.json"
  lzy_log_info "采集系统信息"

  local os_pretty kernel arch hostname
  local cpu_model cpu_cores cpu_threads cpu_mhz
  local mem_total mem_available
  local disk_summary
  local ipv4 ipv6 default_iface
  local asn_info=""

  os_pretty="$( (grep PRETTY_NAME /etc/os-release 2>/dev/null || true) | cut -d= -f2- | tr -d '"' )"
  [[ -z "${os_pretty}" ]] && os_pretty="$(uname -s)"
  kernel="$(uname -r 2>/dev/null || echo "")"
  arch="$(uname -m 2>/dev/null || echo "")"
  hostname="$(hostname 2>/dev/null || echo "")"

  cpu_model="$(lscpu 2>/dev/null | awk -F: '/Model name/{gsub(/^[ \t]+/,"",$2); print $2; exit}')"
  cpu_cores="$(nproc --all 2>/dev/null || nproc 2>/dev/null || echo 1)"
  cpu_threads="${cpu_cores}"
  cpu_mhz="$(lscpu 2>/dev/null | awk -F: '/CPU MHz/{gsub(/^[ \t]+/,"",$2); print $2; exit}')"

  mem_total="$(free -b 2>/dev/null | awk '/Mem:/{print $2}')"
  mem_available="$(free -b 2>/dev/null | awk '/Mem:/{print $7}')"

  disk_summary="$(lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE -n 2>/dev/null | tr '\n' ';' | sed 's/;$//')"

  default_iface="$(ip route 2>/dev/null | awk '/default/{print $5; exit}')"
  ipv4="$(ip -4 addr show "${default_iface}" 2>/dev/null | awk '/inet /{print $2; exit}')"
  if [[ -z "${ipv4}" ]]; then
    ipv4="$(ip -4 addr show scope global 2>/dev/null | awk '/inet /{print $2; exit}')"
  fi
  ipv6="$(ip -6 addr show scope global 2>/dev/null | awk '/inet6/{print $2; exit}')"

  # ASN via whois on public IP (best-effort)
  local public_ip=""
  if lzy_require_cmd curl; then
    public_ip="$(curl -4 -s --max-time 5 https://ifconfig.me 2>/dev/null || \
                 curl -4 -s --max-time 5 https://api.ipify.org 2>/dev/null || true)"
  fi
  if [[ -n "${public_ip}" ]] && lzy_require_cmd whois; then
    asn_info="$(whois "${public_ip}" 2>/dev/null | awk '
      BEGIN{IGNORECASE=1}
      /originas:|origin:|aut-num:/{print; exit}
      /OrgName:|org-name:|descr:/{if(!d){d=$0}}
      END{if(d) print d}
    ' | head -n 3 | tr '\n' ' ' | sed 's/[[:space:]]\+/ /g')"
  fi

  # Virt / cloud hints
  local virt=""
  if lzy_require_cmd systemd-detect-virt; then
    virt="$(systemd-detect-virt 2>/dev/null || echo "")"
  fi

  cat >"${out}" <<EOF
{
  "module": "system",
  "status": "ok",
  "timestamp": "$(lzy_now_iso)",
  "os": {
    "pretty_name": "$(lzy_json_escape "${os_pretty}")",
    "kernel": "$(lzy_json_escape "${kernel}")",
    "arch": "$(lzy_json_escape "${arch}")",
    "hostname": "$(lzy_json_escape "${hostname}")",
    "virt": "$(lzy_json_escape "${virt}")"
  },
  "cpu": {
    "model": "$(lzy_json_escape "${cpu_model}")",
    "cores": $(lzy_json_num_or_null "${cpu_cores}"),
    "mhz": $(lzy_json_num_or_null "${cpu_mhz}")
  },
  "memory": {
    "total_bytes": $(lzy_json_num_or_null "${mem_total}"),
    "available_bytes": $(lzy_json_num_or_null "${mem_available}")
  },
  "disk": {
    "lsblk_summary": "$(lzy_json_escape "${disk_summary}")"
  },
  "network": {
    "default_iface": "$(lzy_json_escape "${default_iface}")",
    "ipv4": "$(lzy_json_escape "${ipv4}")",
    "ipv6": "$(lzy_json_escape "${ipv6}")",
    "public_ip": "$(lzy_json_escape "${public_ip}")",
    "asn": "$(lzy_json_escape "${asn_info}")"
  }
}
EOF

  lzy_info "已写入 ${out}"
  return 0
}
