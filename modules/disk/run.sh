#!/usr/bin/env bash
# modules/disk/run.sh - disk benchmarks via fio

_lzy_fio_run() {
  # Args: name rw bs
  local name="$1" rw="$2" bs="$3"
  local testdir="${LZY_DISK_TEST_DIR:-/tmp/lzy-bench-disk}"
  local size="${LZY_DISK_FILE_SIZE:-1G}"
  local runtime="${LZY_DISK_RUNTIME:-30}"
  local iodepth="${LZY_DISK_IODEPTH:-64}"
  local numjobs="${LZY_DISK_NUMJOBS:-1}"
  local outfile="${testdir}/${name}.json"

  mkdir -p "${testdir}"

  fio --name="${name}" \
    --directory="${testdir}" \
    --filename="${name}.bin" \
    --rw="${rw}" \
    --bs="${bs}" \
    --size="${size}" \
    --runtime="${runtime}" \
    --time_based=1 \
    --iodepth="${iodepth}" \
    --numjobs="${numjobs}" \
    --direct=1 \
    --group_reporting=1 \
    --output-format=json \
    --output="${outfile}" \
    >>"$(lzy_log_file disk)" 2>&1
}

_lzy_fio_extract() {
  # Extract bw_bytes (MiB/s) and iops from fio JSON via jq or python/grep fallback
  local file="$1"
  local metric="$2" # bw or iops
  if [[ ! -f "${file}" ]]; then
    echo ""
    return 0
  fi
  if lzy_has_jq; then
    if [[ "${metric}" == "bw" ]]; then
      # bytes/s -> MiB/s
      jq -r '
        .jobs[0].read.bw_bytes // .jobs[0].write.bw_bytes //
        ((.jobs[0].read.bw // .jobs[0].write.bw // 0) * 1024)
        | . / 1048576
      ' "${file}" 2>/dev/null | awk '{printf "%.2f", $1}'
    else
      jq -r '.jobs[0].read.iops // .jobs[0].write.iops // 0' "${file}" 2>/dev/null | \
        awk '{printf "%.2f", $1}'
    fi
  else
    # crude fallback
    if [[ "${metric}" == "iops" ]]; then
      grep -oE '"iops"[[:space:]]*:[[:space:]]*[0-9.]+' "${file}" | head -1 | grep -oE '[0-9.]+$'
    else
      grep -oE '"bw_bytes"[[:space:]]*:[[:space:]]*[0-9.]+' "${file}" | head -1 | grep -oE '[0-9.]+$' | \
        awk '{printf "%.2f", $1/1048576}'
    fi
  fi
}

lzy_module_disk() {
  local out="${LZY_RUN_DIR}/disk.json"
  local testdir="${LZY_DISK_TEST_DIR:-/tmp/lzy-bench-disk}"
  lzy_log_info "开始磁盘测试"

  local status="ok" error=""
  local seq_read_bw="" seq_write_bw=""
  local rand_read_bw="" rand_write_bw=""
  local rand_read_iops="" rand_write_iops=""
  local dd_write_mibs="" dd_read_mibs="" dd_status="skip"

  mkdir -p "${testdir}"

  # --- Optional dd quick test (lemonbench-style, fast) ---
  if [[ "${LZY_DISK_DD:-1}" == "1" ]]; then
    lzy_info "dd 快测（${LZY_DISK_DD_COUNT:-1024} x ${LZY_DISK_DD_BS:-1M}）"
    local dd_file="${testdir}/dd_test.bin"
    local dd_out
    if dd_out="$(dd if=/dev/zero of="${dd_file}" bs="${LZY_DISK_DD_BS:-1M}" \
        count="${LZY_DISK_DD_COUNT:-1024}" conv=fdatasync oflag=direct 2>&1)"; then
      echo "${dd_out}" >>"$(lzy_log_file disk)"
      # "1024+0 records out" / "1073741824 bytes (1.1 GB, 1.0 GiB) copied, 2.5 s, 400 MB/s"
      dd_write_mibs="$(echo "${dd_out}" | awk '
        /copied/ {
          for (i=1;i<=NF;i++) if ($i ~ /MB\/s|GB\/s|MiB\/s|GiB\/s/) {
            v=$(i-1); u=$i;
            if (u ~ /^GB/ || u ~ /^GiB/) v=v*1024;
            printf "%.2f", v; exit
          }
        }')"
      if dd_out="$(dd if="${dd_file}" of=/dev/null bs="${LZY_DISK_DD_BS:-1M}" iflag=direct 2>&1)"; then
        echo "${dd_out}" >>"$(lzy_log_file disk)"
        dd_read_mibs="$(echo "${dd_out}" | awk '
          /copied/ {
            for (i=1;i<=NF;i++) if ($i ~ /MB\/s|GB\/s|MiB\/s|GiB\/s/) {
              v=$(i-1); u=$i;
              if (u ~ /^GB/ || u ~ /^GiB/) v=v*1024;
              printf "%.2f", v; exit
            }
          }')"
        dd_status="ok"
        lzy_ok "dd write≈${dd_write_mibs} MiB/s  read≈${dd_read_mibs} MiB/s"
      else
        dd_status="fail"
        echo "${dd_out}" >>"$(lzy_log_file disk)"
        lzy_warn "dd read failed"
      fi
    else
      dd_status="fail"
      echo "${dd_out}" >>"$(lzy_log_file disk)"
      lzy_warn "dd write failed (可忽略，继续 fio)"
    fi
    rm -f "${dd_file}" 2>/dev/null || true
  fi

  # --- fio ---
  if [[ "${LZY_DISK_FIO:-1}" == "1" ]]; then
    if ! lzy_require_cmd fio; then
      lzy_warn "未安装 fio，跳过 fio 测试（仍保留 dd 结果）"
      LZY_DISK_FIO=0
    fi
  fi

  if [[ "${LZY_DISK_FIO:-1}" == "1" ]]; then
    lzy_info "fio sequential read"
    if ! _lzy_fio_run "seq_read" "read" "1M"; then
      status="fail"; error="seq_read failed"; lzy_warn "${error}"
    else
      seq_read_bw="$(_lzy_fio_extract "${testdir}/seq_read.json" bw)"
    fi

    lzy_info "fio sequential write"
    if ! _lzy_fio_run "seq_write" "write" "1M"; then
      status="fail"; error="${error}; seq_write failed"; lzy_warn "seq_write failed"
    else
      seq_write_bw="$(_lzy_fio_extract "${testdir}/seq_write.json" bw)"
    fi

    local bs="${LZY_DISK_BLOCKSIZE:-4k}"
    lzy_info "fio random read (${bs})"
    if ! _lzy_fio_run "rand_read" "randread" "${bs}"; then
      status="fail"; error="${error}; rand_read failed"; lzy_warn "rand_read failed"
    else
      rand_read_bw="$(_lzy_fio_extract "${testdir}/rand_read.json" bw)"
      rand_read_iops="$(_lzy_fio_extract "${testdir}/rand_read.json" iops)"
    fi

    lzy_info "fio random write (${bs})"
    if ! _lzy_fio_run "rand_write" "randwrite" "${bs}"; then
      status="fail"; error="${error}; rand_write failed"; lzy_warn "rand_write failed"
    else
      rand_write_bw="$(_lzy_fio_extract "${testdir}/rand_write.json" bw)"
      rand_write_iops="$(_lzy_fio_extract "${testdir}/rand_write.json" iops)"
    fi

    if [[ "${LZY_KEEP_TEMP:-0}" != "1" ]]; then
      rm -f "${testdir}"/*.bin 2>/dev/null || true
    fi
    mkdir -p "${LZY_RUN_DIR}/fio"
    cp -f "${testdir}"/*.json "${LZY_RUN_DIR}/fio/" 2>/dev/null || true
  else
    lzy_info "已跳过 fio（LZY_DISK_FIO=0）"
    bs="${LZY_DISK_BLOCKSIZE:-4k}"
  fi

  cat >"${out}" <<EOF
{
  "module": "disk",
  "status": "${status}",
  "timestamp": "$(lzy_now_iso)",
  "error": "$(lzy_json_escape "${error}")",
  "config": {
    "test_dir": "$(lzy_json_escape "${testdir}")",
    "file_size": "$(lzy_json_escape "${LZY_DISK_FILE_SIZE:-1G}")",
    "runtime_sec": $(lzy_json_num_or_null "${LZY_DISK_RUNTIME:-30}"),
    "iodepth": $(lzy_json_num_or_null "${LZY_DISK_IODEPTH:-64}"),
    "blocksize_rand": "$(lzy_json_escape "${bs:-4k}")",
    "dd_enabled": $( [[ "${LZY_DISK_DD:-1}" == "1" ]] && echo true || echo false ),
    "fio_enabled": $( [[ "${LZY_DISK_FIO:-1}" == "1" ]] && echo true || echo false )
  },
  "dd": {
    "status": "${dd_status}",
    "write_mib_s": $(lzy_json_num_or_null "${dd_write_mibs}"),
    "read_mib_s": $(lzy_json_num_or_null "${dd_read_mibs}")
  },
  "sequential": {
    "read_mib_s": $(lzy_json_num_or_null "${seq_read_bw}"),
    "write_mib_s": $(lzy_json_num_or_null "${seq_write_bw}")
  },
  "random": {
    "read_mib_s": $(lzy_json_num_or_null "${rand_read_bw}"),
    "write_mib_s": $(lzy_json_num_or_null "${rand_write_bw}"),
    "read_iops": $(lzy_json_num_or_null "${rand_read_iops}"),
    "write_iops": $(lzy_json_num_or_null "${rand_write_iops}")
  }
}
EOF

  lzy_info "已写入 ${out}"
  [[ "${status}" == "ok" || "${dd_status}" == "ok" ]] && return 0 || return 1
}
