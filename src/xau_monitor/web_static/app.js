const $ = (id) => document.getElementById(id);
const priceFormat = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

let latestPayload = null;
let lastChartSignature = "";
let chartMode = "1m";
const defaultIndicators = {
  ema200: true,
  bollinger: true,
  atr: false,
  psar: true,
  pivots: true,
};
let strategyEnabled = true;
let enabledIndicators = { ...defaultIndicators };

function toneForBias(bias) {
  if (bias === "偏多") return "up";
  if (bias === "偏空") return "down";
  return "neutral";
}

function setText(id, value) {
  const node = $(id);
  if (node) node.textContent = value;
}

function renderFrames(frames) {
  const labels = { "1m": "1分钟", "5m": "5分钟", "15m": "15分钟" };
  $("frames").innerHTML = ["1m", "5m", "15m"].map((key) => {
    const frame = frames[key];
    const tone = toneForBias(frame.bias);
    return `
      <article class="metric-card card">
        <div class="metric-head">
          <span class="period">${labels[key]}</span>
          <span class="bias-pill ${tone}">${frame.bias} · ${frame.score > 0 ? "+" : ""}${frame.score}</span>
        </div>
        <div class="indicator-grid">
          <div><span>EMA 5</span><strong>${priceFormat.format(frame.ema5)}</strong></div>
          <div><span>EMA 20</span><strong>${priceFormat.format(frame.ema20)}</strong></div>
          <div><span>RSI 14</span><strong>${frame.rsi14.toFixed(1)}</strong></div>
          <div><span>ATR 14</span><strong>${frame.atr14.toFixed(2)}</strong></div>
        </div>
      </article>`;
  }).join("");
}

function emaSeries(values, period) {
  const alpha = 2 / (period + 1);
  const output = [values[0]];
  for (let index = 1; index < values.length; index += 1) {
    output.push(values[index] * alpha + output[index - 1] * (1 - alpha));
  }
  return output;
}

function bollingerSeries(values, period = 20, multiplier = 2) {
  return values.map((_, index) => {
    if (index + 1 < period) return null;
    const window = values.slice(index + 1 - period, index + 1);
    const middle = window.reduce((sum, value) => sum + value, 0) / period;
    const variance = window.reduce(
      (sum, value) => sum + (value - middle) ** 2,
      0,
    ) / period;
    const deviation = Math.sqrt(variance) * multiplier;
    return { middle, upper: middle + deviation, lower: middle - deviation };
  });
}

function atrSeries(candles, period = 14) {
  if (!candles.length) return [];
  const trueRanges = candles.map((candle, index) => {
    if (index === 0) return candle.high - candle.low;
    const previousClose = candles[index - 1].close;
    return Math.max(
      candle.high - candle.low,
      Math.abs(candle.high - previousClose),
      Math.abs(candle.low - previousClose),
    );
  });
  const output = [];
  let current = trueRanges[0];
  trueRanges.forEach((value, index) => {
    current = index === 0 ? value : ((current * (period - 1)) + value) / period;
    output.push(current);
  });
  return output;
}

function atrChannelSeries(candles, period = 20, multiplier = 2) {
  const closes = candles.map((candle) => candle.close);
  const middle = emaSeries(closes, period);
  const ranges = atrSeries(candles, 14);
  return middle.map((value, index) => ({
    middle: value,
    upper: value + ranges[index] * multiplier,
    lower: value - ranges[index] * multiplier,
  }));
}

function psarSeries(candles, step = 0.02, maximum = 0.2) {
  if (!candles.length) return [];
  const output = [candles[0].low];
  let rising = candles.length < 2 || candles[1].close >= candles[0].close;
  let extreme = rising ? candles[0].high : candles[0].low;
  let acceleration = step;
  let sar = rising ? candles[0].low : candles[0].high;

  for (let index = 1; index < candles.length; index += 1) {
    sar += acceleration * (extreme - sar);
    if (rising) {
      sar = Math.min(sar, candles[index - 1].low);
      if (index > 1) sar = Math.min(sar, candles[index - 2].low);
      if (candles[index].low < sar) {
        rising = false;
        sar = extreme;
        extreme = candles[index].low;
        acceleration = step;
      } else if (candles[index].high > extreme) {
        extreme = candles[index].high;
        acceleration = Math.min(maximum, acceleration + step);
      }
    } else {
      sar = Math.max(sar, candles[index - 1].high);
      if (index > 1) sar = Math.max(sar, candles[index - 2].high);
      if (candles[index].high > sar) {
        rising = true;
        sar = extreme;
        extreme = candles[index].high;
        acceleration = step;
      } else if (candles[index].low < extreme) {
        extreme = candles[index].low;
        acceleration = Math.min(maximum, acceleration + step);
      }
    }
    output.push(sar);
  }
  return output;
}

function buildIndicators(candles) {
  const closes = candles.map((candle) => candle.close);
  return {
    ema200: emaSeries(closes, 200),
    bollinger: bollingerSeries(closes),
    atr: atrChannelSeries(candles),
    psar: psarSeries(candles),
  };
}

function renderStrategy(candles, indicators, pivots) {
  const result = $("strategy-result");
  const detail = $("strategy-detail");
  if (!strategyEnabled) {
    result.className = "strategy-result neutral";
    setText("strategy-bias", "已关闭");
    setText("strategy-score", "0 / 0");
    detail.textContent = "组合策略已关闭；单项设置会保留。";
    return;
  }

  const close = candles.at(-1)?.close;
  if (!Number.isFinite(close)) return;
  const votes = [];
  const addVote = (name, bullish) => votes.push({
    name,
    score: bullish ? 1 : -1,
    text: bullish ? "多" : "空",
  });
  if (enabledIndicators.ema200 && candles.length >= 200) {
    addVote("EMA200", close >= indicators.ema200.at(-1));
  }
  if (enabledIndicators.bollinger) {
    const latest = indicators.bollinger.at(-1);
    if (latest) addVote("布林", close >= latest.middle);
  }
  if (enabledIndicators.atr) {
    addVote("ATR", close >= indicators.atr.at(-1).middle);
  }
  if (enabledIndicators.psar) {
    addVote("PSAR", close >= indicators.psar.at(-1));
  }
  if (enabledIndicators.pivots && pivots) {
    addVote("枢轴", close >= pivots.p);
  }

  const score = votes.reduce((sum, vote) => sum + vote.score, 0);
  const ratio = votes.length ? score / votes.length : 0;
  const bias = ratio >= 0.4 ? "偏多" : ratio <= -0.4 ? "偏空" : "观望";
  const tone = toneForBias(bias);
  result.className = `strategy-result ${tone}`;
  setText("strategy-bias", bias);
  setText("strategy-score", `${score > 0 ? "+" : ""}${score} / ${votes.length}`);
  detail.textContent = votes.length
    ? votes.map((vote) => `${vote.name}:${vote.text}`).join(" · ")
    : "请至少开启一个指标；EMA200 需要满 200 根 K 线。";
}

function prepareCanvas() {
  const canvas = $("price-chart");
  const empty = $("chart-empty");
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(rect.width * ratio);
  canvas.height = Math.round(rect.height * ratio);
  const context = canvas.getContext("2d");
  context.scale(ratio, ratio);
  return { canvas, empty, context, width: rect.width, height: rect.height };
}

function drawGrid(context, width, height, padding, min, max) {
  const plotHeight = height - padding.top - padding.bottom;
  context.strokeStyle = "#24292b";
  context.fillStyle = "#737c7f";
  context.font = "10px ui-sans-serif, system-ui";
  context.textAlign = "left";
  for (let line = 0; line <= 4; line += 1) {
    const price = max - ((max - min) * line) / 4;
    const yy = padding.top + (plotHeight * line) / 4;
    context.beginPath();
    context.moveTo(padding.left, yy);
    context.lineTo(width - padding.right + 4, yy);
    context.stroke();
    context.fillText(priceFormat.format(price), width - padding.right + 10, yy + 3);
  }
}

function drawLatestPrice(context, width, padding, priceY, price, color) {
  const labelHeight = 22;
  const labelLeft = width - padding.right + 6;
  const labelWidth = padding.right - 10;

  context.save();
  context.setLineDash([4, 4]);
  context.strokeStyle = color;
  context.globalAlpha = 0.6;
  context.beginPath();
  context.moveTo(padding.left, priceY);
  context.lineTo(labelLeft, priceY);
  context.stroke();
  context.restore();

  context.fillStyle = color;
  context.fillRect(
    labelLeft,
    priceY - labelHeight / 2,
    labelWidth,
    labelHeight,
  );
  context.fillStyle = "#090b0c";
  context.font = "700 10px ui-sans-serif, system-ui";
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillText(
    priceFormat.format(price),
    labelLeft + labelWidth / 2,
    priceY,
  );
  context.textBaseline = "alphabetic";
}

function drawCandleChart(allCandles, pivots) {
  if (!allCandles || allCandles.length < 2) return;
  const { empty, context, width, height } = prepareCanvas();
  empty.style.display = "none";
  const padding = { top: 12, right: 65, bottom: 25, left: 8 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const indicators = buildIndicators(allCandles);
  renderStrategy(allCandles, indicators, pivots);
  const visibleCount = chartMode === "1m" ? 64 : 52;
  const startIndex = Math.max(0, allCandles.length - visibleCount);
  const candles = allCandles.slice(startIndex);
  const series = {
    ema200: indicators.ema200.slice(startIndex),
    bollinger: indicators.bollinger.slice(startIndex),
    atr: indicators.atr.slice(startIndex),
    psar: indicators.psar.slice(startIndex),
  };
  const rawCandleMin = Math.min(...candles.map((candle) => candle.low));
  const rawCandleMax = Math.max(...candles.map((candle) => candle.high));
  const candleRange = Math.max(rawCandleMax - rawCandleMin, 0.5);
  const overlayValues = [];
  if (strategyEnabled && enabledIndicators.ema200) overlayValues.push(...series.ema200);
  if (strategyEnabled && enabledIndicators.bollinger) {
    series.bollinger.filter(Boolean).forEach((value) => overlayValues.push(value.upper, value.lower));
  }
  if (strategyEnabled && enabledIndicators.atr) {
    series.atr.forEach((value) => overlayValues.push(value.upper, value.lower));
  }
  if (strategyEnabled && enabledIndicators.psar) overlayValues.push(...series.psar);
  const visiblePivots = strategyEnabled && enabledIndicators.pivots && pivots
    ? ["r2", "r1", "p", "s1", "s2"]
      .map((key) => ({ key, value: pivots[key] }))
      .filter(({ value }) => value >= rawCandleMin - candleRange && value <= rawCandleMax + candleRange)
    : [];
  overlayValues.push(...visiblePivots.map((item) => item.value));
  const finiteOverlays = overlayValues.filter(Number.isFinite);
  const rawMin = Math.min(rawCandleMin, ...finiteOverlays);
  const rawMax = Math.max(rawCandleMax, ...finiteOverlays);
  const margin = Math.max((rawMax - rawMin) * 0.08, 0.5);
  const min = rawMin - margin;
  const max = rawMax + margin;
  const x = (index) => padding.left + ((index + 0.5) / candles.length) * plotWidth;
  const y = (price) => padding.top + ((max - price) / (max - min)) * plotHeight;

  context.clearRect(0, 0, width, height);
  drawGrid(context, width, height, padding, min, max);

  const step = plotWidth / candles.length;
  const bodyWidth = Math.max(2, Math.min(8, step * 0.58));
  candles.forEach((candle, index) => {
    const rising = candle.close >= candle.open;
    const color = rising ? "#2ecb91" : "#ff596d";
    const xx = x(index);
    context.strokeStyle = color;
    context.fillStyle = color;
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(xx, y(candle.high));
    context.lineTo(xx, y(candle.low));
    context.stroke();
    const top = y(Math.max(candle.open, candle.close));
    const bottom = y(Math.min(candle.open, candle.close));
    context.fillRect(xx - bodyWidth / 2, top, bodyWidth, Math.max(1, bottom - top));
  });

  const drawLine = (values, color, widthValue = 1.3, dash = []) => {
    context.save();
    context.strokeStyle = color;
    context.lineWidth = widthValue;
    context.setLineDash(dash);
    context.beginPath();
    let started = false;
    values.forEach((value, index) => {
      if (!Number.isFinite(value)) {
        started = false;
        return;
      }
      if (!started) context.moveTo(x(index), y(value));
      else context.lineTo(x(index), y(value));
      started = true;
    });
    context.stroke();
    context.restore();
  };

  const drawBand = (values, color) => {
    const valid = values
      .map((value, index) => ({ value, index }))
      .filter(({ value }) => value && Number.isFinite(value.upper) && Number.isFinite(value.lower));
    if (valid.length < 2) return;
    context.save();
    context.fillStyle = color;
    context.beginPath();
    valid.forEach(({ value, index }, position) => {
      if (position === 0) context.moveTo(x(index), y(value.upper));
      else context.lineTo(x(index), y(value.upper));
    });
    [...valid].reverse().forEach(({ value, index }) => context.lineTo(x(index), y(value.lower)));
    context.closePath();
    context.fill();
    context.restore();
  };

  if (strategyEnabled && enabledIndicators.bollinger) {
    drawBand(series.bollinger, "rgba(85,168,255,.07)");
    drawLine(series.bollinger.map((value) => value?.upper), "#55a8ff", 1);
    drawLine(series.bollinger.map((value) => value?.middle), "rgba(85,168,255,.65)", 1, [4, 3]);
    drawLine(series.bollinger.map((value) => value?.lower), "#55a8ff", 1);
  }
  if (strategyEnabled && enabledIndicators.atr) {
    drawBand(series.atr, "rgba(183,124,255,.055)");
    drawLine(series.atr.map((value) => value.upper), "#b77cff", 1);
    drawLine(series.atr.map((value) => value.middle), "rgba(183,124,255,.6)", 1, [3, 3]);
    drawLine(series.atr.map((value) => value.lower), "#b77cff", 1);
  }
  if (strategyEnabled && enabledIndicators.ema200) {
    drawLine(series.ema200, "#e9b949", 1.8);
  }
  if (strategyEnabled && enabledIndicators.psar) {
    series.psar.forEach((value, index) => {
      if (!Number.isFinite(value)) return;
      context.fillStyle = value < candles[index].close ? "#2ecb91" : "#ef8fff";
      context.beginPath();
      context.arc(x(index), y(value), 1.8, 0, Math.PI * 2);
      context.fill();
    });
  }
  const pivotColors = {
    r2: "#ff596d",
    r1: "#ff8c55",
    p: "#f2cf66",
    s1: "#50d6a2",
    s2: "#2ecb91",
  };
  visiblePivots.forEach(({ key, value }) => {
    context.save();
    context.strokeStyle = pivotColors[key];
    context.fillStyle = pivotColors[key];
    context.globalAlpha = 0.8;
    context.setLineDash(key === "p" ? [6, 3] : [3, 4]);
    context.beginPath();
    context.moveTo(padding.left, y(value));
    context.lineTo(width - padding.right, y(value));
    context.stroke();
    context.font = "700 9px ui-sans-serif, system-ui";
    context.textAlign = "left";
    context.fillText(key.toUpperCase(), padding.left + 4, y(value) - 3);
    context.restore();
  });

  const latestCandle = candles.at(-1);
  const latestX = x(candles.length - 1);
  const latestY = y(latestCandle.close);
  const latestColor = latestCandle.close >= latestCandle.open ? "#2ecb91" : "#ff596d";
  context.fillStyle = latestColor;
  context.beginPath();
  context.arc(latestX, latestY, 3.5, 0, Math.PI * 2);
  context.fill();
  drawLatestPrice(
    context,
    width,
    padding,
    latestY,
    latestCandle.close,
    latestColor,
  );

  context.fillStyle = "#737c7f";
  context.textAlign = "center";
  const timeIndexes = [0, Math.floor(candles.length / 2), candles.length - 1];
  timeIndexes.forEach((index) => {
    const date = new Date(candles[index].timestamp * 1000);
    context.fillText(
      date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }),
      x(index),
      height - 6,
    );
  });
}

function drawTickChart(ticks) {
  if (!ticks || ticks.length < 2) return;
  const { empty, context, width, height } = prepareCanvas();
  empty.style.display = "none";
  const padding = { top: 12, right: 65, bottom: 25, left: 8 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const prices = ticks.flatMap((tick) => [tick.bid, tick.ask, tick.last]);
  const rawMin = Math.min(...prices);
  const rawMax = Math.max(...prices);
  const margin = Math.max((rawMax - rawMin) * 0.16, 0.08);
  const min = rawMin - margin;
  const max = rawMax + margin;
  const x = (index) => padding.left + (index / Math.max(1, ticks.length - 1)) * plotWidth;
  const y = (price) => padding.top + ((max - price) / (max - min)) * plotHeight;

  context.clearRect(0, 0, width, height);
  drawGrid(context, width, height, padding, min, max);

  const drawLine = (field, color, lineWidth) => {
    context.beginPath();
    ticks.forEach((tick, index) => {
      if (index === 0) context.moveTo(x(index), y(tick[field]));
      else context.lineTo(x(index), y(tick[field]));
    });
    context.strokeStyle = color;
    context.lineWidth = lineWidth;
    context.stroke();
  };
  drawLine("bid", "rgba(46,203,145,.65)", 1);
  drawLine("ask", "rgba(255,89,109,.62)", 1);
  drawLine("last", "#e9b949", 1.8);

  const last = ticks.at(-1);
  context.fillStyle = "#e9b949";
  context.beginPath();
  context.arc(x(ticks.length - 1), y(last.last), 3.5, 0, Math.PI * 2);
  context.fill();
  drawLatestPrice(
    context,
    width,
    padding,
    y(last.last),
    last.last,
    "#e9b949",
  );

  context.fillStyle = "#737c7f";
  context.font = "10px ui-sans-serif, system-ui";
  context.textAlign = "center";
  [0, Math.floor(ticks.length / 2), ticks.length - 1].forEach((index) => {
    context.fillText(
      new Date(ticks[index].timestamp_ms).toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }),
      x(index),
      height - 6,
    );
  });
}

function mergeLiveCandle(candles, ticks, intervalSeconds) {
  const merged = candles.map((candle) => ({ ...candle }));
  if (!merged.length || !ticks?.length) return merged;

  ticks.forEach((tick) => {
    const tickSeconds = Math.floor(tick.timestamp_ms / 1000);
    const bucket = Math.floor(tickSeconds / intervalSeconds) * intervalSeconds;
    let current = merged.at(-1);

    if (bucket > current.timestamp) {
      current = {
        timestamp: bucket,
        open: tick.last,
        high: tick.last,
        low: tick.last,
        close: tick.last,
      };
      merged.push(current);
    } else if (bucket === current.timestamp) {
      current.high = Math.max(current.high, tick.last);
      current.low = Math.min(current.low, tick.last);
      current.close = tick.last;
    }
  });
  return merged;
}

function drawSelectedChart(data, force = false) {
  if (chartMode === "tick") {
    const ticks = data.ticks || [];
    const signature = ticks.length ? `${ticks.at(-1).timestamp_ms}:${ticks.length}` : "";
    if (force || signature !== lastChartSignature) drawTickChart(ticks);
    lastChartSignature = signature;
    return;
  }
  const intervalSeconds = chartMode === "1m" ? 60 : 300;
  const liveCandles = mergeLiveCandle(
    data.candles[chartMode],
    data.ticks,
    intervalSeconds,
  );
  const current = liveCandles.at(-1);
  const settingsSignature = Object.entries(enabledIndicators)
    .map(([key, value]) => `${key}:${value ? 1 : 0}`)
    .join(",");
  const signature = `${chartMode}:${data.feed.sequence}:${current.timestamp}:${current.close}:${current.high}:${current.low}:${strategyEnabled}:${settingsSignature}`;
  if (force || signature !== lastChartSignature) {
    drawCandleChart(liveCandles, data.daily_pivots);
  }
  lastChartSignature = signature;
}

function render(data) {
  latestPayload = data;
  const ticker = data.ticker;
  const tone = ticker.change_percent > 0 ? "up" : ticker.change_percent < 0 ? "down" : "neutral";

  setText("market-status", ticker.status === "open" ? "市场交易中" : ticker.status);
  setText("updated-time", new Date(ticker.timestamp_ms).toLocaleTimeString("zh-CN", { hour12: false }));
  setText("feed-latency", `接口 ${data.feed.latency_ms.toFixed(0)} ms`);
  setText("frequency-badge", `HIGH-FREQ · ${data.feed.quote_hz.toFixed(1)} Hz`);
  setText("last-price", priceFormat.format(ticker.last));
  setText("bid-price", priceFormat.format(ticker.bid));
  setText("ask-price", priceFormat.format(ticker.ask));
  setText("spread", ticker.spread.toFixed(2));
  setText("day-low", priceFormat.format(ticker.low));
  setText("day-high", priceFormat.format(ticker.high));
  setText("day-change", `${ticker.change_percent > 0 ? "+" : ""}${ticker.change_percent.toFixed(2)}%`);
  $("day-change").className = `change ${tone}`;

  const range = Math.max(ticker.high - ticker.low, 0.01);
  const position = Math.max(0, Math.min(100, ((ticker.last - ticker.low) / range) * 100));
  $("range-fill").style.width = `${position}%`;
  $("range-pin").style.left = `${position}%`;

  const overallTone = toneForBias(data.overall.bias);
  $("bias-orb").className = `bias-orb ${overallTone}`;
  setText("overall-bias", data.overall.bias);
  setText("overall-score", `${data.overall.score > 0 ? "+" : ""}${data.overall.score}`);
  setText("bias-title", data.overall.bias === "偏多" ? "多周期动能偏强" : data.overall.bias === "偏空" ? "多周期结构偏弱" : "多空方向尚未统一");
  setText("bias-detail", `1分钟 ${data.frames["1m"].bias}，5分钟 ${data.frames["5m"].bias}，15分钟 ${data.frames["15m"].bias}。`);
  setText("alert-line", data.plan[0] || "等待新的结构提示");

  renderFrames(data.frames);
  drawSelectedChart(data);

  setText("resistance", priceFormat.format(data.frames["1m"].resistance));
  setText("level-current", priceFormat.format(ticker.last));
  setText("support", priceFormat.format(data.frames["1m"].support));
  $("plan-list").innerHTML = data.plan.map((item) => `<li>${item}</li>`).join("");
}

async function refresh() {
  try {
    const response = await fetch("/api/snapshot", { cache: "no-store" });
    const data = await response.json();
    if (!data.ok) throw new Error(data.error || "行情暂不可用");
    render(data);
  } catch (error) {
    setText("market-status", "连接重试中");
    setText("alert-line", error.message);
  }
}

window.addEventListener("resize", () => {
  if (latestPayload) drawSelectedChart(latestPayload, true);
});

document.querySelectorAll(".chart-mode").forEach((button) => {
  button.addEventListener("click", () => {
    chartMode = button.dataset.mode;
    document.querySelectorAll(".chart-mode").forEach((item) => {
      item.classList.toggle("active", item === button);
    });
    setText("chart-title", chartMode === "tick" ? "Tick 实时报价" : `${chartMode === "1m" ? "1分钟" : "5分钟"} K线`);
    lastChartSignature = "";
    if (latestPayload) drawSelectedChart(latestPayload, true);
  });
});

function saveStrategySettings() {
  localStorage.setItem("xau-strategy-settings", JSON.stringify({
    enabled: strategyEnabled,
    indicators: enabledIndicators,
  }));
}

function initializeStrategyControls() {
  try {
    const saved = JSON.parse(localStorage.getItem("xau-strategy-settings") || "null");
    if (saved && typeof saved.enabled === "boolean") strategyEnabled = saved.enabled;
    if (saved?.indicators) {
      enabledIndicators = { ...defaultIndicators, ...saved.indicators };
    }
  } catch (_error) {
    enabledIndicators = { ...defaultIndicators };
  }

  const master = $("strategy-master");
  master.checked = strategyEnabled;
  document.querySelectorAll("[data-indicator]").forEach((input) => {
    input.checked = Boolean(enabledIndicators[input.dataset.indicator]);
    input.addEventListener("change", () => {
      enabledIndicators[input.dataset.indicator] = input.checked;
      saveStrategySettings();
      lastChartSignature = "";
      if (latestPayload) drawSelectedChart(latestPayload, true);
    });
  });
  master.addEventListener("change", () => {
    strategyEnabled = master.checked;
    $("price-chart").closest(".chart-card").querySelector(".strategy-bar")
      .classList.toggle("disabled", !strategyEnabled);
    saveStrategySettings();
    lastChartSignature = "";
    if (latestPayload) drawSelectedChart(latestPayload, true);
  });
  $("price-chart").closest(".chart-card").querySelector(".strategy-bar")
    .classList.toggle("disabled", !strategyEnabled);
}

initializeStrategyControls();
refresh();
const stream = new EventSource("/api/stream");
stream.onmessage = (event) => {
  try {
    const data = JSON.parse(event.data);
    if (data.ok) render(data);
  } catch (error) {
    setText("market-status", "数据解析重试中");
  }
};
stream.onerror = () => {
  setText("market-status", "事件流重连中");
};
