const $ = (sel) => document.querySelector(sel);

async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

function fmt(v) {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(1);
  return String(v);
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/* Tabs */
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $(`#panel-${btn.dataset.tab}`).classList.add("active");
  });
});

async function loadHealth() {
  try {
    const h = await api("/api/health");
    const el = $("#health");
    el.textContent = `API ${h.status} · v${h.version}`;
    el.classList.add("ok");
  } catch {
    $("#health").textContent = "API 不可用";
  }
}

async function loadRanking() {
  const metric = $("#metric").value;
  const data = await api(`/api/ranking?metric=${encodeURIComponent(metric)}&limit=30`);
  const body = $("#rank-body");
  if (!data.items.length) {
    body.innerHTML = `<tr><td colspan="8">暂无数据。请先 upload / ingest 评测结果。</td></tr>`;
    return;
  }
  body.innerHTML = data.items
    .map(
      (it) => `
    <tr data-id="${esc(it.run_id)}">
      <td>${it.rank}</td>
      <td>${esc(it.label || it.run_id)}</td>
      <td>${esc(it.hostname || "—")}</td>
      <td>${esc(it.provider || "—")}</td>
      <td class="score">${fmt(it.overall)}</td>
      <td>${fmt(it.metric_value)}</td>
      <td>${esc(it.route_guess || "—")}</td>
      <td class="mono">${esc((it.cpu_model || "").slice(0, 36))}</td>
    </tr>`
    )
    .join("");
}

async function loadRuns() {
  const data = await api("/api/runs?limit=100&order=created_at");
  const body = $("#runs-body");
  if (!data.items.length) {
    body.innerHTML = `<tr><td colspan="8">暂无结果</td></tr>`;
    return;
  }
  body.innerHTML = data.items
    .map(
      (it) => `
    <tr data-id="${esc(it.run_id)}">
      <td class="mono">${esc(it.run_id)}</td>
      <td>${esc(it.label || "—")}</td>
      <td class="score">${fmt(it.overall)}</td>
      <td>${fmt(it.cpu_score)}</td>
      <td>${fmt(it.disk_score)}</td>
      <td>${fmt(it.network_score)}</td>
      <td>${fmt(it.application_score)}</td>
      <td>${esc(it.created_at || "—")}</td>
    </tr>`
    )
    .join("");

  body.querySelectorAll("tr[data-id]").forEach((tr) => {
    tr.addEventListener("click", async () => {
      const detail = $("#run-detail");
      detail.classList.remove("hidden");
      detail.textContent = "加载详情…";
      try {
        const full = await api(`/api/runs/${encodeURIComponent(tr.dataset.id)}`);
        detail.textContent = JSON.stringify(full, null, 2);
      } catch (e) {
        detail.textContent = String(e);
      }
    });
  });
}

async function runCompare() {
  const ids = $("#compare-ids").value.trim();
  const box = $("#compare-result");
  if (!ids.includes(",")) {
    box.innerHTML = `<div class="card">请输入至少两个 run_id，用逗号分隔。</div>`;
    return;
  }
  box.innerHTML = `<div class="card">对比中…</div>`;
  try {
    const data = await api(`/api/compare?runs=${encodeURIComponent(ids)}`);
    box.innerHTML = data.runs
      .map(
        (r, idx) => `
      <div class="card">
        <h3>${esc(r.label || r.run_id)}${idx === 0 ? "（基准）" : ""}</h3>
        <div class="big">${fmt(r.overall)}</div>
        <dl>
          <dt>CPU / Mem / Disk</dt>
          <dd>${fmt(r.cpu_score)} / ${fmt(r.memory_score)} / ${fmt(r.disk_score)}</dd>
          <dt>Net / Route / App</dt>
          <dd>${fmt(r.network_score)} / ${fmt(r.route_score)} / ${fmt(r.application_score)}</dd>
          <dt>厂商 / 地区 / 月费</dt>
          <dd>${esc(r.provider || "—")} / ${esc(r.region || "—")} / ${fmt(r.price)}</dd>
          <dt>线路</dt>
          <dd>${esc(r.route_guess || "—")}</dd>
          <dt>CPU</dt>
          <dd>${esc(r.cpu_model || "—")}</dd>
        </dl>
      </div>`
      )
      .join("");

    if (data.deltas_vs_first && data.runs.length > 1) {
      const d = data.deltas_vs_first;
      box.innerHTML += `
        <div class="card">
          <h3>相对第一台的差值</h3>
          <dl>
            <dt>overall</dt><dd>${esc(JSON.stringify(d.overall))}</dd>
            <dt>cpu_score</dt><dd>${esc(JSON.stringify(d.cpu_score))}</dd>
            <dt>disk_score</dt><dd>${esc(JSON.stringify(d.disk_score))}</dd>
            <dt>network_score</dt><dd>${esc(JSON.stringify(d.network_score))}</dd>
          </dl>
        </div>`;
    }
  } catch (e) {
    box.innerHTML = `<div class="card">${esc(String(e))}</div>`;
  }
}

$("#btn-refresh-rank").addEventListener("click", () => loadRanking().catch(console.error));
$("#metric").addEventListener("change", () => loadRanking().catch(console.error));
$("#btn-refresh-runs").addEventListener("click", () => loadRuns().catch(console.error));
$("#btn-compare").addEventListener("click", () => runCompare());

loadHealth();
loadRanking().catch(console.error);
loadRuns().catch(console.error);
