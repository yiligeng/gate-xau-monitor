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

function price(value) {
  return Number.isFinite(value)
    ? Number(value).toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })
    : "--";
}

function money(value) {
  if (!Number.isFinite(value)) return "--";
  return `${value >= 0 ? "+" : "-"}$${Math.abs(value).toFixed(2)}`;
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

function timeOnly(value) {
  if (!value) return "--";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function shiftedTime(value, minutes) {
  const date = new Date(value);
  date.setMinutes(date.getMinutes() + minutes);
  return timeOnly(date);
}

function timeRange(value, startMinutes, endMinutes) {
  return `${shiftedTime(value, startMinutes)}–${shiftedTime(value, endMinutes)}`;
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
  setText("rate-1", rate(selected.reversal_rate_1));
  setText("record-1", `${selected.reversal_1 || 0} / ${selected.sample_count || 0}`);
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

function renderAnchors(rows) {
  const target = $("anchor-body");
  if (!rows?.length) {
    target.innerHTML = '<tr><td colspan="9">还没有可用样本。</td></tr>';
    return;
  }
  target.innerHTML = rows.map((row) => `
    <tr>
      <td><strong>${String(row.minute).padStart(2, "0")}</strong></td>
      <td>${row.sample_count || 0}</td>
      <td>${rate(row.reversal_rate_1)}</td>
      <td>${rate(row.reversal_rate_5)}</td>
      <td>${rate(row.reversal_rate_15)}</td>
      <td>${rate(row.persistent_rate)}</td>
      ${averageOutcome(row, 1)}
      ${averageOutcome(row, 5)}
      ${averageOutcome(row, 15)}
    </tr>
  `).join("");
}

function averageOutcome(row, minutes) {
  const dollarResult = row[`average_return_${minutes}`];
  const atrResult = row[`average_return_${minutes}_atr`];
  return `
    <td class="average-outcome ${resultClass(dollarResult)}">
      <strong>${money(dollarResult)}</strong>
      <small>${signed(atrResult, " ATR")}</small>
    </td>
  `;
}

function renderCandleChart(row) {
  const candles = Array.isArray(row.chart_candles) ? row.chart_candles : [];
  if (!candles.length) return '<p class="chart-empty">这条样本没有完整K线。</p>';

  const width = 960;
  const height = 290;
  const left = 62;
  const right = 22;
  const top = 34;
  const bottom = 36;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const high = Math.max(...candles.map((candle) => Number(candle.high)));
  const low = Math.min(...candles.map((candle) => Number(candle.low)));
  const padding = Math.max((high - low) * 0.08, 0.01);
  const chartHigh = high + padding;
  const chartLow = low - padding;
  const priceSpan = chartHigh - chartLow;
  const step = plotWidth / candles.length;
  const candleWidth = Math.max(5, step * 0.56);
  const y = (value) => top + ((chartHigh - Number(value)) / priceSpan) * plotHeight;
  const xBoundary = (relativeMinute) => left + (relativeMinute + 5) * step;

  const grid = Array.from({ length: 5 }, (_item, index) => {
    const value = chartHigh - (priceSpan * index) / 4;
    const yValue = y(value);
    return `
      <line x1="${left}" y1="${yValue}" x2="${width - right}" y2="${yValue}" class="chart-grid-line" />
      <text x="${left - 8}" y="${yValue + 4}" class="chart-axis-label" text-anchor="end">${price(value)}</text>
    `;
  }).join("");

  const bars = candles.map((candle, index) => {
    const open = Number(candle.open);
    const close = Number(candle.close);
    const x = left + (index + 0.5) * step;
    const bodyTop = y(Math.max(open, close));
    const bodyBottom = y(Math.min(open, close));
    const bodyHeight = Math.max(2, bodyBottom - bodyTop);
    const className = close >= open ? "up" : "down";
    const title = `${timeOnly(candle.opened_at)} · 开 ${price(open)} · 高 ${price(candle.high)} · 低 ${price(candle.low)} · 收 ${price(close)}`;
    return `
      <g class="candle ${className}">
        <title>${escapeHtml(title)}</title>
        <line x1="${x}" y1="${y(candle.high)}" x2="${x}" y2="${y(candle.low)}" />
        <rect x="${x - candleWidth / 2}" y="${bodyTop}" width="${candleWidth}" height="${bodyHeight}" rx="1" />
      </g>
    `;
  }).join("");

  const entryY = y(row.entry_price);
  const markers = [
    { minute: 0, label: "观察点" },
    { minute: 1, label: "+1分" },
    { minute: 5, label: "+5分" },
    { minute: 15, label: "+15分" },
  ].map((marker) => `
    <line x1="${xBoundary(marker.minute)}" y1="${top}" x2="${xBoundary(marker.minute)}" y2="${height - bottom}" class="chart-marker" />
    <text x="${xBoundary(marker.minute)}" y="${height - 12}" class="chart-marker-label" text-anchor="middle">${marker.label}</text>
  `).join("");

  return `
    <div class="chart-panel">
      <div class="chart-summary">
        <strong>${timeRange(row.event_at, -5, 15)} · 20根一分钟K线</strong>
        <span>区间最高 ${price(high)} · 最低 ${price(low)}</span>
      </div>
      <div class="chart-scroll">
        <svg class="candle-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="观察前5分钟至观察后15分钟K线图">
          ${grid}
          <line x1="${left}" y1="${entryY}" x2="${width - right}" y2="${entryY}" class="entry-line" />
          <text x="${width - right}" y="${entryY - 6}" class="entry-label" text-anchor="end">起点 ${price(row.entry_price)}</text>
          ${markers}
          ${bars}
        </svg>
      </div>
      <div class="chart-legend">
        <span><i class="legend-up"></i>上涨K线</span>
        <span><i class="legend-down"></i>下跌K线</span>
        <span><i class="legend-entry"></i>观察起点价</span>
      </div>
    </div>
  `;
}

function renderAudit(rows) {
  const target = $("audit-body");
  if (!rows?.length) {
    target.innerHTML = '<tr><td class="empty-row" colspan="7">还没有走满15分钟的有效样本。</td></tr>';
    return;
  }
  target.innerHTML = rows.map((row, index) => {
    const direction = row.trade_direction === "long" ? "准备做多" : "准备做空";
    const signal = row.signal_direction === "up" ? "上涨" : "下跌";
    const oneMinuteState = row.reversal_1
      ? "已反转"
      : Number(row.return_1 || 0) > 0
        ? "反向但未达标"
        : "未反转";
    const chartId = `sample-chart-${index}`;
    return `
      <tr class="sample-row">
        <td class="audit-time" data-label="观察时点">
          <strong>${escapeHtml(localTime(row.event_at))}</strong>
          <small>${String(row.minute).padStart(2, "0")}分</small>
        </td>
        <td class="price-cell pre-move-cell" data-label="观察前走势">
          <strong>${timeRange(row.event_at, -5, 0)}</strong>
          <small>前5分 ${price(row.pre_5_open_price)} → ${price(row.entry_price)}</small>
          <small>最高 ${price(row.pre_5_high)} · 最低 ${price(row.pre_5_low)}</small>
          <small>前1分 ${price(row.signal_open_price)} → ${price(row.signal_close_price)} · ${signal} ${Number(row.signal_body_atr || 0).toFixed(2)} ATR</small>
        </td>
        <td class="price-cell" data-label="观察起点">
          <strong>${price(row.entry_price)}</strong>
          <small>${timeOnly(row.event_at)} · ${direction}</small>
          <small>ATR $${Number(row.atr || 0).toFixed(2)}</small>
        </td>
        <td class="price-cell one-minute-cell" data-label="后1分钟">
          <small>${timeRange(row.event_at, 0, 1)}</small>
          <strong>${price(row.entry_price)} → ${price(row.price_1)}</strong>
          <small>最高 ${price(row.high_1)} · 最低 ${price(row.low_1)}</small>
          <small class="outcome-line ${resultClass(row.return_1)}">${money(row.return_1)} / ${signed(row.return_1_atr, " ATR")}</small>
          <b class="reversal-state ${row.reversal_1 ? "positive" : "neutral"}">${oneMinuteState}</b>
        </td>
        <td class="price-cell" data-label="5分钟价格">
          <small>${timeRange(row.event_at, 0, 5)}</small>
          <strong>${price(row.entry_price)} → ${price(row.price_5)}</strong>
          <small>最高 ${price(row.high_5)} · 最低 ${price(row.low_5)}</small>
          <small class="outcome-line ${resultClass(row.return_5)}">${money(row.return_5)} / ${signed(row.return_5_atr, " ATR")}</small>
        </td>
        <td class="price-cell" data-label="15分钟价格">
          <small>${timeRange(row.event_at, 0, 15)}</small>
          <strong>${price(row.entry_price)} → ${price(row.price_15)}</strong>
          <small>最高 ${price(row.high_15)} · 最低 ${price(row.low_15)}</small>
          <small class="outcome-line ${resultClass(row.return_15)}">${money(row.return_15)} / ${signed(row.return_15_atr, " ATR")}</small>
        </td>
        <td class="result-cell" data-label="结果">
          <strong>${escapeHtml(CLASSIFICATION_LABELS[row.classification] || row.classification)}</strong>
          <button class="chart-toggle" type="button" data-chart-id="${chartId}" data-row-index="${index}" aria-expanded="false">查看K线</button>
        </td>
      </tr>
      <tr id="${chartId}" class="chart-detail-row" hidden>
        <td class="chart-detail-cell" colspan="7"><div class="chart-host"></div></td>
      </tr>
    `;
  }).join("");
  target.querySelectorAll(".chart-toggle").forEach((button) => {
    button.addEventListener("click", () => {
      const detail = document.getElementById(button.dataset.chartId);
      const opening = detail.hidden;
      detail.hidden = !opening;
      button.setAttribute("aria-expanded", String(opening));
      button.textContent = opening ? "收起K线" : "查看K线";
      const host = detail.querySelector(".chart-host");
      if (opening && !host.dataset.rendered) {
        host.innerHTML = renderCandleChart(rows[Number(button.dataset.rowIndex)]);
        host.dataset.rendered = "true";
      }
    });
  });
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
