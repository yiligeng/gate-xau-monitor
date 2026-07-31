const $ = (id) => document.getElementById(id);

const CLASSIFICATION_LABELS = {
  persistent: "持续反转",
  faded: "假反转",
  delayed: "延迟反转",
  no_reversal: "未反转",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function rate(value) {
  return Number.isFinite(value) ? `${value.toFixed(1)}%` : "--";
}

function signed(value, suffix = "") {
  if (!Number.isFinite(value)) return "--";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}${suffix}`;
}

function resultClass(value) {
  if (!Number.isFinite(value) || Math.abs(value) < 0.0001) return "neutral";
  return value > 0 ? "positive" : "negative";
}

function localTime(value) {
  if (!value) return "--";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function setText(id, value) {
  const target = $(id);
  if (target) target.textContent = value;
}

function setBar(id, value) {
  const target = $(id);
  if (!target) return;
  const width = Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0;
  target.style.width = `${width}%`;
}

function renderEvidence(data) {
  const target = $("evidence-status");
  const evidence = data.evidence || { code: "collecting", label: "采集中" };
  target.className = `evidence-status ${evidence.code}`;
  target.querySelector("strong").textContent = evidence.label;
  const samples = data.summary?.selected?.sample_count || 0;
  const note = samples < 30
    ? `还需 ${30 - samples} 个有效样本进入初步判断`
    : "已与同一6分钟节奏的对照时点比较";
  setText("evidence-note", note);
}

function renderSummary(data) {
  const selected = data.summary?.selected || {};
  const control = data.summary?.grid_control || {};
  setText("sample-count", String(selected.sample_count || 0));
  setText("candidate-count", `候选 ${selected.candidate_count || 0}`);
  setText("rate-5", rate(selected.reversal_rate_5));
  setText("record-5", `${selected.reversal_5 || 0} / ${selected.sample_count || 0}`);
  setText("rate-15", rate(selected.reversal_rate_15));
  setText("record-15", `${selected.reversal_15 || 0} / ${selected.sample_count || 0}`);
  setText("persistent-rate", rate(selected.persistent_rate));
  setText("persistent-count", `${selected.persistent || 0} 次持续反转`);
  setText("lift-5", signed(data.summary?.lift_5, "pp"));
  setText("lift-15", signed(data.summary?.lift_15, "pp"));

  setBar("selected-bar-5", selected.reversal_rate_5);
  setBar("control-bar-5", control.reversal_rate_5);
  setBar("selected-bar-15", selected.reversal_rate_15);
  setBar("control-bar-15", control.reversal_rate_15);
  setText("selected-label-5", rate(selected.reversal_rate_5));
  setText("control-label-5", rate(control.reversal_rate_5));
  setText("selected-label-15", rate(selected.reversal_rate_15));
  setText("control-label-15", rate(control.reversal_rate_15));
}

function renderMinuteGrid(rows) {
  const target = $("minute-grid");
  target.innerHTML = (rows || []).map((row) => {
    const value = row.reversal_rate_5;
    const alpha = Number.isFinite(value) ? 0.08 + (value / 100) * 0.54 : 0;
    const background = Number.isFinite(value)
      ? `rgba(50, 210, 150, ${alpha.toFixed(3)})`
      : "#111416";
    const minute = String(row.minute).padStart(2, "0");
    const title = `${minute}分：${rate(value)}，有效样本 ${row.sample_count || 0}`;
    return `
      <div class="minute-cell ${escapeHtml(row.group)}" style="background:${background}" title="${escapeHtml(title)}">
        <strong>${minute}</strong>
        <small>${rate(value)} · n=${row.sample_count || 0}</small>
      </div>
    `;
  }).join("");
}

function renderAnchors(rows) {
  const target = $("anchor-body");
  if (!rows?.length) {
    target.innerHTML = '<tr><td colspan="7">还没有可用样本。</td></tr>';
    return;
  }
  target.innerHTML = rows.map((row) => `
    <tr>
      <td><strong>${String(row.minute).padStart(2, "0")}</strong></td>
      <td>${row.sample_count || 0}</td>
      <td>${rate(row.reversal_rate_5)}</td>
      <td>${rate(row.reversal_rate_15)}</td>
      <td>${rate(row.persistent_rate)}</td>
      <td class="${resultClass(row.average_return_5_atr)}">${signed(row.average_return_5_atr, " ATR")}</td>
      <td class="${resultClass(row.average_return_15_atr)}">${signed(row.average_return_15_atr, " ATR")}</td>
    </tr>
  `).join("");
}

function renderAudit(rows) {
  const target = $("audit-body");
  if (!rows?.length) {
    target.innerHTML = '<tr><td colspan="7">还没有走满15分钟的有效样本。</td></tr>';
    return;
  }
  target.innerHTML = rows.map((row) => {
    const direction = row.trade_direction === "long" ? "准备做多" : "准备做空";
    const signal = row.signal_direction === "up" ? "上涨" : "下跌";
    return `
      <tr>
        <td>${escapeHtml(localTime(row.event_at))}</td>
        <td>${String(row.minute).padStart(2, "0")}</td>
        <td>${signal} · ${Number(row.signal_body_atr || 0).toFixed(2)} ATR</td>
        <td>${direction}</td>
        <td class="${resultClass(row.return_5_atr)}">${signed(row.return_5_atr, " ATR")}</td>
        <td class="${resultClass(row.return_15_atr)}">${signed(row.return_15_atr, " ATR")}</td>
        <td>${escapeHtml(CLASSIFICATION_LABELS[row.classification] || row.classification)}</td>
      </tr>
    `;
  }).join("");
}

function renderCoverage(coverage) {
  const count = coverage?.total_candles || 0;
  if (!count) {
    setText("coverage-text", "K线数据正在积累");
    return;
  }
  setText(
    "coverage-text",
    `数据库 ${count.toLocaleString("zh-CN")} 根 · ${localTime(coverage.first_opened_at)} 起`,
  );
}

function render(data) {
  renderEvidence(data);
  renderSummary(data);
  renderMinuteGrid(data.minute_stats);
  renderAnchors(data.anchors);
  renderAudit(data.recent);
  renderCoverage(data.coverage);
}

async function loadData() {
  const refresh = $("refresh-button");
  refresh.disabled = true;
  const days = $("days-filter").value;
  try {
    const response = await fetch(`/api/hypotheses/reversal?market=xau&days=${days}`, {
      cache: "no-store",
      credentials: "same-origin",
    });
    if (response.status === 401) {
      window.location.assign("/login");
      return;
    }
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || "统计读取失败");
    }
    render(data);
  } catch (error) {
    const status = $("evidence-status");
    status.className = "evidence-status not_supported";
    status.querySelector("strong").textContent = "读取失败";
    setText("evidence-note", error.message || "请稍后重试");
  } finally {
    refresh.disabled = false;
  }
}

$("days-filter").addEventListener("change", loadData);
$("refresh-button").addEventListener("click", loadData);
loadData();
