const $ = (id) => document.getElementById(id);
const priceFormat = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const compactCurrency = new Intl.NumberFormat("zh-CN", {
  notation: "compact",
  maximumFractionDigits: 1,
  style: "currency",
  currency: "USD",
});

const ACTIVE_MARKET_KEY = "xau-monitor-active-market-v1";
const MARKET_CONFIGS = {
  xau: {
    id: "xau",
    symbol: "XAUUSD",
    mark: "Au",
    eyebrow: "GATE TRADFI · LIVE CFD",
    title: "XAUUSD 黄金监控",
    volumeEyebrow: "FREE LIVE VOLUME PROXY",
    volumeTitle: "免费实时黄金量能",
    volumeNote: "零成本实时代理：使用 Gate XAUT/USDT、PAXG/USDT 的真实现货成交。它可判断放量/缩量，但不是 COMEX GC 期货成交量。",
    contractLabel: "每标准手盎司",
    contractUnit: 100,
    contractMin: 1,
    contractStep: 1,
    positionLabel: "参考手数",
    journalPrefix: "xau",
  },
  btc: {
    id: "btc",
    symbol: "BTC_USDT",
    mark: "₿",
    eyebrow: "GATE FUTURES · USDT PERPETUAL",
    title: "BTCUSDT 永续监控",
    volumeEyebrow: "REAL PERPETUAL VOLUME",
    volumeTitle: "BTC 永续实时成交量",
    volumeNote: "使用 Gate BTC_USDT 永续合约真实成交量与逐笔成交方向；主动买卖差按最近60秒主动成交额计算，逐笔列表最多取最新1000笔。",
    contractLabel: "每张 BTC 数量",
    contractUnit: 0.0001,
    contractMin: 0.0001,
    contractStep: 0.0001,
    positionLabel: "参考张数",
    journalPrefix: "btc",
  },
};
const STRATEGY_HELP = {
  strategy: {
    title: "这套策略到底在做什么？",
    body: "它不预测顶部和底部。先用5分钟和15分钟决定只做多、只做空或不交易；再等价格来到支撑/阻力，用1分钟K线确认“假突破后收回”。全部硬条件通过后才允许入场。",
    formula: "方向 → 关键位 → 扫损回收 → 成本/空间 → 量能加分 → 评分≥80",
  },
  score: {
    title: "评分不是胜率",
    body: "分数表示当前规则完成了多少，不代表这笔交易有多少概率盈利。即使达到80分，关键位质量、成本空间、信号时效和禁止追价等硬条件也必须同时通过。",
    formula: "总分 = 趋势25 + 关键位最高25 + 扫损回收30 + 执行10 + 量能0/5/10",
  },
  action: {
    title: "当前动作怎么读？",
    body: "趋势背景只负责筛选方向，当前动作才说明有没有模拟入场。“继续等待”和“计划就绪”都没有入场；只有显示“模拟已触发”才会记录交易。“放弃本次”表示成本、空间或时效不合格。",
    formula: "背景偏多/偏空 ≠ 入场；只有“模拟已触发”＝记录模拟交易",
  },
  trend: {
    title: "多周期趋势（先看人话）",
    body: "系统先问四个问题：价格在短期平均线上面还是下面？短期平均线在长期平均线上面还是下面？短期平均线正在抬头还是低头？15分钟有没有明显反向？四项方向一致，只能说明背景偏多或偏空，不能直接入场。",
    formula: "四项全部通过＝选定趋势背景，不等于发出交易信号",
  },
  direction_terms: {
    title: "方向判断里的名词",
    body: "“收盘价”是刚结束那根K线最后的成交价；EMA20是偏重近期价格的20根平均线；EMA50是更慢的50根平均线；斜率就是EMA20比15分钟前升了还是降了；ATR只表示平常波动多大，不代表涨跌。",
    formula: "短期位置看 EMA20；大致趋势看 EMA20 与 EMA50；方向变化看 EMA20 斜率；15分钟负责防止逆势",
  },
  close_term: {
    title: "什么是5分钟最新收盘价？",
    body: "每5分钟形成一根K线。时间结束时的最后成交价就是收盘价。拿它和EMA20比较，是为了确认价格“现在”确实位于短期平均成本的哪一侧，而不是只依赖已经滞后的均线方向。",
    formula: "刚结束5分钟K线的最后成交价 = C5",
  },
  ema_term: {
    title: "EMA20和EMA50是什么？",
    body: "它们都是平均价格线。EMA20反应较快，EMA50反应较慢。比较两者是为了判断最近一段价格是否整体低于或高于更长时间的价格，过滤单独一两根大涨大跌造成的假方向。",
    formula: "EMA今日 = 当前价格×(2÷(周期+1)) + 前EMA×(1−2÷(周期+1))",
  },
  slope_term: {
    title: "EMA20抬头或低头是什么意思？",
    body: "不是看一瞬间的角度，而是把当前EMA20和15分钟前比较。均线排列描述过去形成的结构，斜率则检查这个结构现在是否还在延续，避免在趋势已经走平或转向时继续追。",
    formula: "斜率变化 = 当前EMA20 − 3根前EMA20；负数=低头，正数=抬头",
  },
  higher_timeframe_term: {
    title: "15分钟没有明显转多/转空",
    body: "5分钟可能只是大趋势里的短暂波动，所以15分钟负责安全检查。例如5分钟偏空，但15分钟已经强劲反弹，此时继续做空容易撞上更大周期的力量。ATR缓冲用于容忍正常噪声，避免轻微越线就反复改变方向。",
    formula: "做空允许：15分钟收盘 ≤ EMA20 + 0.08×ATR15；做多允许：15分钟收盘 ≥ EMA20 − 0.08×ATR15",
  },
  zone: {
    title: "关键位区域",
    body: "系统寻找1/5/15分钟摆动高低点和日枢轴，把价格接近的点聚成区域。至少来自两个不同周期或枢轴，并达到权重要求，才叫高质量区域。",
    formula: "聚类距离 = max(0.22×ATR5，4×点差，0.18)；高质量 = 来源数≥2 且权重≥3.2",
  },
  trigger: {
    title: "扫损回收",
    body: "不是价格一碰支撑就买。做多要求1分钟K线先向下刺入支撑，再收回区域中线上方，并留下明显下影线；做空则先上扫阻力再压回。",
    formula: "做多：收盘≥区域中线，收盘位于K线顶部40%，下影≥max(0.45×实体，0.06×ATR1)；做空反向",
  },
  execution: {
    title: "成本与空间",
    body: "形态正确也可能不值得做。系统会过滤点差太大、止损太宽、前方阻力/支撑太近、信号超过3分钟，以及价格已经跑远的情况。",
    formula: "点差≤max(0.18×ATR1, 0.12)；风险≤1.6×ATR1；目标空间≥1.4R；信号≤180秒；追价距离≤0.35R",
  },
  volume: {
    title: "量能只负责加分",
    body: "量能不会单独触发交易。数据足够新且成交笔数足够时，放量并且主动买卖差与方向一致才加满10分；中性给5分，放量反向给0分。",
    formula: "可用：新鲜度≤20秒且60秒成交≥5笔；放量：RVOL≥1.2；做多差值≥+15%，做空≤−15%",
  },
  gates: {
    title: "五道入场闸门",
    body: "前四项是硬条件：趋势、关键位、扫损回收、成本与空间。任何一项不通过都不应该开仓。第五项量能只是辅助加分，数据稀疏时不会单独否决价格形态。",
    formula: "硬条件 = 趋势 ∧ 高质量区域 ∧ 回收K线 ∧ 可执行；量能 = 辅助",
  },
  entry: {
    title: "触发入场价",
    body: "形成回收K线后还不立刻追。做多要再突破这根触发K线的最高价；做空要再跌破最低价，用第二次确认减少假信号。",
    formula: "做多入场 = 触发K线高点 + max(0.5×点差, 0.02)；做空入场 = 触发K线低点 − 同一缓冲",
  },
  stop: {
    title: "硬止损",
    body: "止损放在触发K线扫出的极值之外。如果行情再次越过那里，说明“假突破后收回”的判断失败，必须退出。",
    formula: "做多止损 = 触发低点 − max(0.1×ATR1, 点差)；做空止损 = 触发高点 + 同一缓冲；最小风险距离=3×点差",
  },
  target: {
    title: "固定止盈",
    body: "R代表入场到止损的距离。目标固定为1.5R，因此盈利一笔理论上可以覆盖一笔止损并多出0.5R，但实际结果仍受点差和成交影响。",
    formula: "风险R = |入场−止损|；做多止盈 = 入场 + 1.5R；做空止盈 = 入场 − 1.5R",
  },
  rr: {
    title: "1.5R 与 8分钟",
    body: "止盈目标是初始风险的1.5倍。超短策略如果8分钟仍未到止盈或止损，就按当时可成交的买卖价退出，避免把超短单拖成长线单。",
    formula: "目标收益/初始风险 = 1.5；持仓时间≥8分钟 → 时间退出",
  },
  balance: {
    title: "账户资金",
    body: "这是用于计算最大允许亏损的资金基数，不是开仓保证金，也不是建议你投入的金额。",
    formula: "允许亏损金额 = 账户资金 × 单笔风险%",
  },
  risk: {
    title: "单笔风险%",
    body: "如果止损被触发，计划最多亏掉账户资金的这个比例。500美元账户、0.25%风险，对应计划亏损1.25美元。",
    formula: "风险金额 = 500 × 0.25% = 1.25美元",
  },
  contract: {
    title: "每手/每张合约单位",
    body: "它表示价格每变动1美元时，一手或一张合约对应多少标的数量。黄金常见标准手是100盎司；当前 Gate BTC_USDT 每张是0.0001 BTC，实际下单前仍要核对平台规格。",
    formula: "每单位价格波动的单份盈亏 = 合约单位 × 1美元",
  },
  position: {
    title: "参考仓位怎么计算？",
    body: "先确定最多允许亏多少钱，再除以一手/一张到止损会亏多少钱。BTC结果按整张向下取整；黄金保留小数手。它不包含手续费、滑点和资金费率。",
    formula: "参考仓位 = (账户资金×风险%) ÷ (|入场−止损|×合约单位)",
  },
  winrate: {
    title: "模拟胜率",
    body: "只统计已经结束的模拟交易；进行中的交易不进入分母。样本很少时胜率没有统计意义。",
    formula: "胜率 = 盈利笔数 ÷ 已完成笔数 × 100%",
  },
  expectancy: {
    title: "平均期望 R",
    body: "把每笔结果先换算成R再求平均。正数表示当前样本平均赚钱，负数表示平均亏损；仍需足够多样本才能判断策略是否稳定。",
    formula: "单笔R = 方向调整后的(退出价−入场价) ÷ 初始风险；平均期望 = Σ单笔R ÷ 已完成笔数",
  },
  totalr: {
    title: "累计结果 R",
    body: "把所有已结束模拟交易的R相加。用R而不是美元，可以比较不同账户资金和不同仓位下的策略表现。",
    formula: "累计R = Σ每笔结果R",
  },
  keylevels: {
    title: "这三个关键位从哪里来？",
    body: "这一块优先使用当前企业微信群会话今天仍在监控中的点位；已触达、取消和过期点位都会排除。没有可用机器人点位时，才回退到1分钟K线的短线边界。",
    formula: "近端阻力 = min(监控中点位中高于当前价的点位)；近端支撑 = max(监控中点位中低于当前价的点位)",
  },
  near_resistance: {
    title: "近端阻力算法",
    body: "优先在当前会话今天仍处于“监控中”的点位里，找高于当前价且距离最近的一个。已触达点位不再参与阻力计算。",
    formula: "Resistance = min(level > 当前价 且 status=active)",
  },
  current_price: {
    title: "当前价格来源",
    body: "直接使用当前品种最新成交价。黄金来自 Gate TradFi XAUUSD CFD；BTC来自 Gate BTC_USDT 永续。它不是均线，也不是预测值。",
    formula: "当前价格 = Gate 最新 ticker.last",
  },
  near_support: {
    title: "近端支撑算法",
    body: "优先在当前会话今天仍处于“监控中”的点位里，找低于当前价且距离最近的一个。已触达点位不再参与支撑计算。",
    formula: "Support = max(level < 当前价 且 status=active)",
  },
  live_notes: {
    title: "当前提示怎么生成？",
    body: "不是AI自由发挥，而是把三类实时计算结果翻译成人话：价格相对EMA20与5分钟方向、5分钟ATR和当前点差、以及当前量能RVOL与主动买卖差。",
    formula: "提示 = 结构判断 + 波动/成本 + 量能状态",
  },
  structure_note: {
    title: "第一条：结构提示",
    body: "如果当前会话有仍在监控中的点位，第一条提示会先展示最近的上方/下方监控位区间；已触达点位不参与。没有机器人点位时，才展示原来的EMA与K线结构提示。",
    formula: "监控区间 = 最近下方active点位 – 最近上方active点位",
  },
  atr_note: {
    title: "第二条：ATR与点差",
    body: "ATR14衡量最近波动，不表示上涨或下跌。它用真实波幅做Wilder平滑；点差则是当前卖价减买价，用来衡量即时交易成本。",
    formula: "TR=max(高−低, |高−前收|, |低−前收|)；ATR14=(前ATR×13+TR)÷14；点差=Ask−Bid",
  },
  volume_note_help: {
    title: "第三条：量能提示",
    body: "RVOL比较当前分钟成交速度与过去20个完整分钟的典型水平；主动买卖差比较最近60秒主动买入和主动卖出成交额。黄金使用XAUT/PAXG代理，BTC使用永续真实成交。",
    formula: "RVOL=当前分钟预计成交额÷近20分钟成交额中位数；主动差=(主动买额−主动卖额)÷总成交额×100%",
  },
};
let activeMarket = localStorage.getItem(ACTIVE_MARKET_KEY) === "btc"
  ? "btc"
  : "xau";
let latestPayload = null;
let latestScalpResult = null;
let lastChartSignature = "";
let chartMode = "1m";
let chartFocusMs = null;
let quoteTimer = null;
let snapshotTimer = null;
let botAlertsTimer = null;
let botSelectedChatId = "";
let botStrategyDirection = "";
let botStrategyDays = 30;
let botStrategyStatus = "";
let botStrategyDay = "";
let botStrategyCursor = "";
let botStrategyNextCursor = "";
let botStrategyPageHistory = [];
let botStrategyPageNumber = 1;
let botStrategyRequestSequence = 0;
let botKeyLevelContext = {
  market: "",
  chatId: "",
  activeAlerts: [],
};
const clientTicks = [];
let paperTrades = loadPaperTrades();
const defaultIndicators = {
  ema200: true,
  bollinger: true,
  atr: false,
  psar: true,
  pivots: true,
};
let strategyEnabled = true;
let enabledIndicators = { ...defaultIndicators };

function stopMarketUpdates() {
  if (quoteTimer) window.clearInterval(quoteTimer);
  if (snapshotTimer) window.clearInterval(snapshotTimer);
  quoteTimer = null;
  snapshotTimer = null;
  if (botAlertsTimer) window.clearInterval(botAlertsTimer);
  botAlertsTimer = null;
}

async function authorizedFetch(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    cache: "no-store",
    credentials: "same-origin",
  });
  if (response.status === 401) {
    window.location.assign("/login");
    throw new Error("登录已过期");
  }
  return response;
}

function toneForBias(bias) {
  if (bias === "偏多") return "up";
  if (bias === "偏空") return "down";
  return "neutral";
}

function setText(id, value) {
  const node = $(id);
  if (node) node.textContent = value;
}

function setScalpExpanded(expanded) {
  const content = $("scalp-content");
  const toggle = $("scalp-toggle");
  if (!content || !toggle) return;
  content.hidden = !expanded;
  toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
  setText("scalp-toggle-label", expanded ? "收起" : "展开");
}

function activeBotLevelsFor(data) {
  if (
    !botKeyLevelContext.chatId
    || botKeyLevelContext.market !== activeMarket
    || data?.market?.id !== activeMarket
  ) {
    return [];
  }
  return botKeyLevelContext.activeAlerts
    .filter((alert) => alert?.status === "active")
    .map((alert) => Number(alert.level))
    .filter(Number.isFinite);
}

function displayKeyLevels(data) {
  const price = Number(data?.ticker?.last);
  const activeLevels = activeBotLevelsFor(data);
  const fallbackSupport = Number(data?.frames?.["1m"]?.support);
  const fallbackResistance = Number(data?.frames?.["1m"]?.resistance);
  if (!Number.isFinite(price) || !activeLevels.length) {
    return {
      source: "candles",
      support: Number.isFinite(fallbackSupport) ? fallbackSupport : null,
      resistance: Number.isFinite(fallbackResistance) ? fallbackResistance : null,
    };
  }
  const below = activeLevels.filter((level) => level < price);
  const above = activeLevels.filter((level) => level > price);
  return {
    source: "bot",
    support: below.length ? Math.max(...below) : null,
    resistance: above.length ? Math.min(...above) : null,
  };
}

function displayPlan(data) {
  const levels = displayKeyLevels(data);
  const basePlan = Array.isArray(data?.plan) ? data.plan : [];
  if (levels.source !== "bot") return basePlan;
  const notes = [];
  if (Number.isFinite(levels.support) && Number.isFinite(levels.resistance)) {
    notes.push(
      `只看监控中点位；观察 ${priceFormat.format(levels.support)}–${priceFormat.format(levels.resistance)} 区间突破`,
    );
  } else if (Number.isFinite(levels.support)) {
    notes.push(
      `只看监控中点位；最近下方支撑 ${priceFormat.format(levels.support)}，上方暂无未触达监控位`,
    );
  } else if (Number.isFinite(levels.resistance)) {
    notes.push(
      `只看监控中点位；最近上方阻力 ${priceFormat.format(levels.resistance)}，下方暂无未触达监控位`,
    );
  } else {
    notes.push("当前会话没有位于现价上下的监控中点位；已触达点位不再参与关键位");
  }
  return [...notes, ...basePlan.slice(1)];
}

function levelZone(center, data) {
  const value = Number(center);
  if (!Number.isFinite(value)) return null;
  const atr1 = Number(data?.frames?.["1m"]?.atr14);
  const spread = Number(data?.ticker?.spread);
  const halfWidth = Math.max(
    Number.isFinite(atr1) ? atr1 * 0.08 : 0,
    Number.isFinite(spread) ? spread * 1.5 : 0,
    0.06,
  );
  return {
    center: value,
    lower: value - halfWidth,
    upper: value + halfWidth,
  };
}

function renderKeyLevelViews(data) {
  const levels = displayKeyLevels(data);
  const ticker = data?.ticker;
  const plan = displayPlan(data);
  setText(
    "resistance",
    Number.isFinite(levels.resistance)
      ? priceFormat.format(levels.resistance)
      : "--",
  );
  setText(
    "level-current",
    Number.isFinite(Number(ticker?.last))
      ? priceFormat.format(ticker.last)
      : "--",
  );
  setText(
    "support",
    Number.isFinite(levels.support)
      ? priceFormat.format(levels.support)
      : "--",
  );
  setText("alert-line", plan[0] || "等待新的结构提示");
  const planHelpKeys = ["structure_note", "atr_note", "volume_note_help"];
  $("plan-list").innerHTML = plan.map((item, index) => `
    <li>
      <span>${escapeHtml(item)}</span>
      <button
        class="info-button"
        type="button"
        data-help-key="${planHelpKeys[index] || "live_notes"}"
        aria-label="查看这条提示的算法"
      >i</button>
    </li>`).join("");
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function formatCalendarDate(value) {
  if (!value) return "--";
  const date = new Date(`${value}T00:00:00+08:00`);
  return date.toLocaleDateString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
  });
}

function eventToneClass(impact) {
  if (impact === "最高+" || impact === "最高") return "critical";
  if (impact === "高") return "high";
  if (impact === "震荡") return "range";
  return "medium";
}

function registerCalendarHelp(kind, item, index) {
  const key = `calendar_${kind}_${index}`;
  const label = kind === "event"
    ? "重大事件"
    : kind === "event_window"
      ? "事件风险窗"
      : kind === "volatility"
        ? "高波动时段"
        : "震荡窗口";
  STRATEGY_HELP[key] = {
    title: item.title || label,
    body: `${item.time_label || "--"}。${item.note || "按北京时间观察价格反应。"}`,
    formula: `${label}类型：${item.impact || "--"}${item.source ? ` · 来源：${item.source}` : ""}`,
    link: item.source_url || "",
    linkLabel: "查看来源",
  };
  return key;
}

const CALENDAR_MIN_CARD_MINUTES = 42;
const CALENDAR_PIXELS_PER_HOUR = 132;
const CALENDAR_CARD_MIN_WIDTH = 132;
const CALENDAR_CARD_MAX_WIDTH = 230;
const CALENDAR_CARD_GAP = 8;
const CALENDAR_LANE_HEIGHT = 52;
const CALENDAR_CARD_TOP_OFFSET = 4;

function calendarStartMs(item) {
  const value = item?.start || item?.time;
  const parsed = Date.parse(value || "");
  return Number.isFinite(parsed) ? parsed : null;
}

function calendarEndMs(item) {
  const startMs = calendarStartMs(item);
  if (startMs === null) return null;
  const parsedEnd = Date.parse(item?.end || "");
  if (Number.isFinite(parsedEnd) && parsedEnd > startMs) return parsedEnd;
  return startMs + 30 * 60 * 1000;
}

function floorHour(ms) {
  const date = new Date(ms);
  date.setMinutes(0, 0, 0);
  return date.getTime();
}

function ceilHour(ms) {
  const date = new Date(ms);
  date.setMinutes(0, 0, 0);
  if (date.getTime() < ms) date.setHours(date.getHours() + 1);
  return date.getTime();
}

function toTimelineItem(kind, item, index) {
  const startMs = calendarStartMs(item);
  const endMs = calendarEndMs(item);
  if (startMs === null || endMs === null) return null;
  return { kind, item, index, startMs, endMs };
}

function itemContainsMs(timelineItem, ms) {
  return Number.isFinite(ms)
    && timelineItem.startMs <= ms
    && timelineItem.endMs >= ms;
}

function shanghaiMinuteOfDay(ms) {
  if (!Number.isFinite(ms)) return null;
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Shanghai",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(new Date(ms));
  const hour = Number(parts.find((part) => part.type === "hour")?.value);
  const minute = Number(parts.find((part) => part.type === "minute")?.value);
  return Number.isFinite(hour) && Number.isFinite(minute) ? hour * 60 + minute : null;
}

function itemContainsShanghaiMinute(timelineItem, ms) {
  const focusMinute = shanghaiMinuteOfDay(ms);
  const startMinute = shanghaiMinuteOfDay(timelineItem.startMs);
  const endMinute = shanghaiMinuteOfDay(timelineItem.endMs);
  if (focusMinute === null || startMinute === null || endMinute === null) return false;
  return startMinute <= endMinute
    ? focusMinute >= startMinute && focusMinute <= endMinute
    : focusMinute >= startMinute || focusMinute <= endMinute;
}

function timelineItemHasFocus(timelineItem, ms) {
  return itemContainsMs(timelineItem, ms) || itemContainsShanghaiMinute(timelineItem, ms);
}

function timelineBounds(items) {
  const validItems = items.filter(Boolean);
  if (!validItems.length) return null;
  const startMs = floorHour(Math.min(...validItems.map((item) => item.startMs)));
  const endMs = ceilHour(Math.max(...validItems.map((item) => item.endMs)));
  return { startMs, endMs: Math.max(endMs, startMs + 60 * 60 * 1000) };
}

function timelineWidthPx(bounds) {
  const hours = Math.max(
    (bounds.endMs - bounds.startMs) / (60 * 60 * 1000),
    1,
  );
  return Math.ceil(hours * CALENDAR_PIXELS_PER_HOUR + CALENDAR_CARD_MAX_WIDTH);
}

function timelineLeftPx(ms, bounds) {
  return ((ms - bounds.startMs) / (60 * 60 * 1000)) * CALENDAR_PIXELS_PER_HOUR;
}

function timelineCardWidthPx(item) {
  const minutes = Math.max((item.endMs - item.startMs) / (60 * 1000), 1);
  const durationWidth = (minutes / 60) * CALENDAR_PIXELS_PER_HOUR;
  return Math.max(
    CALENDAR_CARD_MIN_WIDTH,
    Math.min(CALENDAR_CARD_MAX_WIDTH, durationWidth),
  );
}

function packTimelineItems(items, bounds) {
  const lanes = [];
  return [...items]
    .sort((a, b) => a.startMs - b.startMs || a.endMs - b.endMs)
    .map((item) => {
      const leftPx = timelineLeftPx(item.startMs, bounds);
      const widthPx = Math.max(
        timelineCardWidthPx(item),
        (CALENDAR_MIN_CARD_MINUTES / 60) * CALENDAR_PIXELS_PER_HOUR,
      );
      const rightPx = leftPx + widthPx + CALENDAR_CARD_GAP;
      let lane = lanes.findIndex((laneRightPx) => laneRightPx <= leftPx);
      if (lane === -1) {
        lane = lanes.length;
        lanes.push(rightPx);
      } else {
        lanes[lane] = rightPx;
      }
      return { ...item, lane, leftPx, widthPx };
    });
}

function timelineItemStyle(timelineItem) {
  const top = timelineItem.lane * CALENDAR_LANE_HEIGHT + CALENDAR_CARD_TOP_OFFSET;
  return `--left:${timelineItem.leftPx.toFixed(1)}px;--width:${timelineItem.widthPx.toFixed(1)}px;--top:${top}px;`;
}

function calendarSourceLinkHtml(item) {
  if (!item?.source_url) return "";
  return `
    <a
      class="calendar-source-link"
      href="${escapeHtml(item.source_url)}"
      target="_blank"
      rel="noopener noreferrer"
      aria-label="打开${escapeHtml(item.title || "事件")}来源"
    >来源</a>
  `;
}

function renderTimelineTicks(bounds) {
  if (!bounds) return "";
  const ticks = [];
  for (let ms = bounds.startMs; ms <= bounds.endMs; ms += 60 * 60 * 1000) {
    const left = timelineLeftPx(ms, bounds);
    const label = new Date(ms).toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "Asia/Shanghai",
    });
    ticks.push(`
      <span class="timeline-tick" style="--left:${left.toFixed(1)}px;">
        <i></i>
        <small>${escapeHtml(label)}</small>
      </span>
    `);
  }
  return ticks.join("");
}

function timelineItemHtml(timelineItem, focusMs) {
  const { kind, item, index } = timelineItem;
  const helpKey = registerCalendarHelp(kind, item, index);
  const tone = eventToneClass(item.impact);
  const style = timelineItemStyle(timelineItem);
  const focusClass = timelineItemHasFocus(timelineItem, focusMs) ? "chart-focus" : "";
  if (kind === "event") {
    return `
      <div class="timeline-item event ${tone} ${item.status} ${focusClass}" style="${style}">
        <div class="calendar-chip-top">
          <span>${escapeHtml(item.title)}</span>
          ${calendarSourceLinkHtml(item)}
          <button class="info-button calendar-info" type="button" data-help-key="${helpKey}" aria-label="查看${escapeHtml(item.title)}说明">i</button>
        </div>
        <strong>${escapeHtml(item.time_label)} · ${escapeHtml(item.source)}</strong>
      </div>
    `;
  }
  const typeLabel = kind === "event_window"
    ? "事件风险窗"
    : kind === "volatility"
      ? "高波动时段"
      : "震荡窗口";
  return `
    <div class="timeline-item ${kind} ${tone} ${item.status} ${focusClass}" style="${style}">
      <div class="calendar-chip-top">
        <span>${escapeHtml(item.title)}</span>
        ${calendarSourceLinkHtml(item)}
        <button class="info-button calendar-info" type="button" data-help-key="${helpKey}" aria-label="查看${escapeHtml(item.title)}说明">i</button>
      </div>
      <strong>${escapeHtml(item.time_label)} · ${escapeHtml(item.note)}</strong>
    </div>
  `;
}

function renderTimelineRow(targetId, items, bounds, emptyText, focusMs) {
  const target = $(targetId);
  if (!target) return { laneCount: 1, maxRightPx: 0 };
  if (!items.length || !bounds) {
    target.style.setProperty("--lane-count", "1");
    target.style.height = `${CALENDAR_LANE_HEIGHT}px`;
    target.innerHTML = `<p>${escapeHtml(emptyText)}</p>`;
    return { laneCount: 1, maxRightPx: 0 };
  }
  const packed = packTimelineItems(items, bounds);
  const maxRightPx = Math.max(
    ...packed.map((item) => item.leftPx + item.widthPx + CALENDAR_CARD_GAP),
  );
  const laneCount = Math.max(...packed.map((item) => item.lane)) + 1;
  target.style.setProperty("--lane-count", String(laneCount));
  target.style.height = `${laneCount * CALENDAR_LANE_HEIGHT}px`;
  target.innerHTML = packed.map((item) => timelineItemHtml(item, focusMs)).join("");
  return { laneCount, maxRightPx };
}

function timelineFocusLeft(items, bounds, focusMs = null, viewportWidth = 0) {
  if (!bounds || !items.length) return 0;
  const sorted = [...items].sort((a, b) => a.startMs - b.startMs || a.endMs - b.endMs);
  const targetMs = Number.isFinite(focusMs) ? focusMs : Date.now();
  const active = sorted.find((item) => timelineItemHasFocus(item, targetMs));
  const next = sorted.find((item) => item.startMs >= targetMs);
  const target = active || next || sorted[0];
  const left = timelineLeftPx(target.startMs, bounds);
  const centerOffset = Number.isFinite(viewportWidth) && viewportWidth > 0
    ? Math.min(viewportWidth * 0.36, 260)
    : 80;
  return Math.max(0, left - centerOffset);
}

function renderMarketCalendar(calendar, focusMs = null) {
  const container = $("market-calendar");
  if (!container || !calendar) return;
  setText("calendar-date", `${formatCalendarDate(calendar.date)} · 北京时间`);
  const windows = Array.isArray(calendar.windows) ? calendar.windows : [];
  const volatilityWindows = Array.isArray(calendar.volatility_windows)
    ? calendar.volatility_windows
    : [];
  const eventWindows = Array.isArray(calendar.event_windows) ? calendar.event_windows : [];
  const events = Array.isArray(calendar.events) ? calendar.events : [];
  const topItems = [
    ...volatilityWindows.map((item, index) => toTimelineItem("volatility", item, index)),
    ...eventWindows.map((item, index) => toTimelineItem("event_window", item, index)),
    ...events.map((item, index) => toTimelineItem("event", item, index)),
  ].filter(Boolean);
  const rangeItems = windows
    .map((item, index) => toTimelineItem("window", item, index))
    .filter(Boolean);
  const bounds = timelineBounds([...topItems, ...rangeItems]);
  const timeline = $("calendar-timeline");
  if (timeline && bounds) {
    timeline.style.setProperty("--timeline-width", `${timelineWidthPx(bounds)}px`);
  }
  setText(
    "calendar-event-summary",
    "上轨按北京时间排序；重叠时上下分层，像甘特图一样看事件覆盖。",
  );
  setText(
    "calendar-risk-summary",
    eventWindows.length || events.length
      ? `${calendar.summary || "今日有重大事件。"} 高波动时段只做风险提示。`
      : "无重大事件时，仍把高波动时段作为风险提示。",
  );
  setText(
    "calendar-window-summary",
    "只放吃饭等低流动性时段；绿色=震荡/假突破窗口。",
  );
  $("calendar-ticks").innerHTML = renderTimelineTicks(bounds);
  const riskRow = renderTimelineRow(
    "calendar-events",
    topItems,
    bounds,
    "今日/今夜暂无重大事件或高波动时段。",
    focusMs,
  );
  const rangeRow = renderTimelineRow(
    "calendar-windows",
    rangeItems,
    bounds,
    "今日暂无震荡窗口，仍以实时形态为准。",
    focusMs,
  );
  if (timeline) {
    const contentWidth = Math.ceil(Math.max(
      timelineWidthPx(bounds),
      riskRow.maxRightPx + 28,
      rangeRow.maxRightPx + 28,
    ));
    timeline.style.setProperty("--timeline-width", `${contentWidth}px`);
    timeline.style.setProperty(
      "--tick-height",
      `${56 + riskRow.laneCount * CALENDAR_LANE_HEIGHT + rangeRow.laneCount * CALENDAR_LANE_HEIGHT}px`,
    );
  }
  const scroll = $("calendar-timeline-scroll");
  if (scroll && bounds) {
    const focusBucket = Number.isFinite(focusMs) ? Math.floor(focusMs / 60_000) : "now";
    const focusKey = `${bounds.startMs}:${bounds.endMs}:${topItems.length}:${rangeItems.length}:${focusBucket}`;
    if (container.dataset.timelineFocusKey !== focusKey) {
      scroll.scrollLeft = timelineFocusLeft(
        [...topItems, ...rangeItems],
        bounds,
        focusMs,
        scroll.clientWidth,
      );
      container.dataset.timelineFocusKey = focusKey;
    }
  }
}

function closeStrategyHelp() {
  const popover = $("strategy-help-popover");
  if (!popover) return;
  popover.classList.remove("open");
  popover.setAttribute("aria-hidden", "true");
  const link = $("strategy-help-link");
  if (link) {
    link.hidden = true;
    link.removeAttribute("href");
  }
  delete popover.dataset.helpKey;
}

function openStrategyHelp(key, anchor) {
  const help = STRATEGY_HELP[key];
  const popover = $("strategy-help-popover");
  if (!help || !popover) return;
  if (popover.classList.contains("open") && popover.dataset.helpKey === key) {
    closeStrategyHelp();
    return;
  }
  setText("strategy-help-title", help.title);
  setText("strategy-help-body", help.body);
  setText("strategy-help-formula", help.formula || "");
  const link = $("strategy-help-link");
  if (link) {
    if (help.link) {
      link.href = help.link;
      link.textContent = help.linkLabel || "查看来源";
      link.hidden = false;
    } else {
      link.hidden = true;
      link.removeAttribute("href");
    }
  }
  popover.dataset.helpKey = key;
  popover.classList.add("open");
  popover.setAttribute("aria-hidden", "false");
  const anchorRect = anchor.getBoundingClientRect();
  const popoverRect = popover.getBoundingClientRect();
  const left = Math.max(
    12,
    Math.min(window.innerWidth - popoverRect.width - 12, anchorRect.left - 20),
  );
  const below = anchorRect.bottom + 8;
  const top = below + popoverRect.height <= window.innerHeight - 12
    ? below
    : Math.max(12, anchorRect.top - popoverRect.height - 8);
  popover.style.left = `${left}px`;
  popover.style.top = `${top}px`;
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

function renderVolume(volumeProxy, liveVolume) {
  const markets = volumeProxy?.markets || [];
  const market = liveVolume
    || markets.find((item) => item.symbol === volumeProxy?.active_symbol)
    || markets[0];
  if (!market) {
    setText("volume-state", "暂不可用");
    return;
  }
  const status = market.rvol >= 1.5
    ? "放量"
    : market.rvol > 0 && market.rvol < 0.65
      ? "缩量"
      : "常态";
  const total60s = market.buy_quote_60s + market.sell_quote_60s;
  setText("volume-state", `实时 · ${status}`);
  setText("volume-symbol", market.symbol.replace("_", "/"));
  setText(
    "volume-freshness",
    market.freshness_ms == null
      ? "近60秒暂无成交"
      : `最新成交 ${Math.max(0, market.freshness_ms / 1000).toFixed(1)} 秒前`,
  );
  setText("volume-rvol", `${market.rvol.toFixed(2)}×`);
  setText("volume-turnover", compactCurrency.format(total60s));
  setText("volume-trades", `${market.trade_count_60s} 笔成交`);
  setText(
    "volume-delta",
    `${market.delta_percent >= 0 ? "+" : ""}${market.delta_percent.toFixed(1)}%`,
  );
  const delta = Math.max(-100, Math.min(100, market.delta_percent));
  const bar = $("volume-delta-bar");
  bar.style.left = delta >= 0 ? "50%" : `${50 + delta / 2}%`;
  bar.style.width = `${Math.abs(delta) / 2}%`;
  bar.style.background = delta >= 0 ? "#2ecb91" : "#ff596d";
  $("volume-delta").style.color = delta >= 0 ? "#2ecb91" : "#ff596d";
}

function parseBotLevels(value) {
  const matches = String(value || "").match(/-?\d+(?:,\d{3})*(?:\.\d+)?/g) || [];
  const seen = new Set();
  const levels = [];
  matches.forEach((item) => {
    const valueNumber = Number(item.replace(/,/g, ""));
    if (!Number.isFinite(valueNumber) || valueNumber <= 0) return;
    const normalized = valueNumber.toFixed(2);
    if (seen.has(normalized)) return;
    seen.add(normalized);
    levels.push(Number(normalized));
  });
  return levels;
}

function formatBotExpiry(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function setBotBusy(busy) {
  ["bot-save-levels", "bot-cancel-levels", "bot-refresh", "bot-chat-select", "bot-level-input"]
    .forEach((id) => {
      const node = $(id);
      if (node) node.disabled = busy;
    });
}

const BOT_STRATEGY_STATUS_LABELS = {
  pending: "待触发",
  open: "持仓中",
  win: "胜",
  loss: "负",
  ambiguous: "顺序待复核",
  expired: "未触发",
  replaced: "已停用",
  cancelled: "已取消",
};

function renderBotStrategySummary(strategy = {}) {
  const settled = Number(strategy.settled || 0);
  const winRate = strategy.win_rate == null ? null : Number(strategy.win_rate);
  const expectancy = strategy.expectancy_points == null
    ? null
    : Number(strategy.expectancy_points);
  const netPoints = Number(strategy.net_points || 0);
  setText("bot-strategy-settled", String(settled));
  setText(
    "bot-strategy-win-rate",
    winRate != null && Number.isFinite(winRate) ? `${winRate.toFixed(2)}%` : "--",
  );
  setText(
    "bot-strategy-record",
    `${Number(strategy.wins || 0)} / ${Number(strategy.losses || 0)}`,
  );
  setText(
    "bot-strategy-net",
    `${netPoints >= 0 ? "+" : ""}${netPoints.toFixed(2)}`,
  );
  setText(
    "bot-strategy-expectancy",
    expectancy != null && Number.isFinite(expectancy)
      ? `${expectancy >= 0 ? "+" : ""}${expectancy.toFixed(2)}`
      : "--",
  );
  setText(
    "bot-strategy-live",
    `${Number(strategy.open || 0)} / ${Number(strategy.pending || 0)} / ${Number(strategy.ambiguous || 0)}`,
  );
}

function strategyDayLabel(value) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return value || "--";
  const [, month, day] = value.split("-");
  return `${Number(month)}月${Number(day)}日`;
}

function strategyTimestampLabel(value) {
  if (!value) return "--";
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return "--";
  return timestamp.toLocaleString("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function strategySigned(value) {
  const number = Number(value || 0);
  return `${number >= 0 ? "+" : ""}${number.toFixed(2)}`;
}

function renderBotStrategyChart(daily = []) {
  const target = $("bot-strategy-chart");
  if (!target) return;
  if (!daily.length) {
    target.innerHTML = "<p>所选范围内还没有点位样本。</p>";
    return;
  }
  const settledTotal = daily.reduce((total, row) => total + Number(row.settled || 0), 0);
  if (!settledTotal) {
    const sampleTotal = daily.reduce(
      (total, row) => total + Number(row.pending || 0) + Number(row.open || 0),
      0,
    );
    target.innerHTML = `<p>已有 ${sampleTotal} 个点位样本，但还没有已结算胜负，暂时无法绘制胜率。</p>`;
    return;
  }
  const width = Math.max(640, daily.length * 38);
  const height = 220;
  const padding = { left: 42, right: 18, top: 18, bottom: 32 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const maxSettled = Math.max(1, ...daily.map((row) => Number(row.settled || 0)));
  const step = daily.length > 1 ? plotWidth / (daily.length - 1) : 0;
  const pointX = (index) => daily.length > 1
    ? padding.left + index * step
    : padding.left + plotWidth / 2;
  const rateY = (rate) => padding.top + ((100 - rate) / 100) * plotHeight;
  const barWidth = Math.max(8, Math.min(22, plotWidth / Math.max(daily.length, 1) * 0.55));
  const labelEvery = Math.max(1, Math.ceil(daily.length / 8));
  const settledRows = daily
    .map((row, index) => ({ row, index }))
    .filter(({ row }) => Number(row.settled || 0) > 0 && row.win_rate != null);
  const linePoints = settledRows
    .map(({ row, index }) => `${pointX(index).toFixed(1)},${rateY(Number(row.win_rate)).toFixed(1)}`)
    .join(" ");
  const grid = [0, 50, 100].map((rate) => {
    const y = rateY(rate);
    return `
      <line class="bot-chart-grid" x1="${padding.left}" x2="${width - padding.right}" y1="${y}" y2="${y}"></line>
      <text class="bot-chart-axis" x="${padding.left - 8}" y="${y + 3}" text-anchor="end">${rate}%</text>
    `;
  }).join("");
  const bars = daily.map((row, index) => {
    const settled = Number(row.settled || 0);
    const barHeight = settled / maxSettled * plotHeight;
    const x = pointX(index) - barWidth / 2;
    const y = padding.top + plotHeight - barHeight;
    return `
      <rect class="bot-chart-bar" x="${x.toFixed(1)}" y="${y.toFixed(1)}"
        width="${barWidth.toFixed(1)}" height="${barHeight.toFixed(1)}">
        <title>${row.setup_day}：${settled}笔，胜率${row.win_rate == null ? "--" : `${Number(row.win_rate).toFixed(2)}%`}</title>
      </rect>
    `;
  }).join("");
  const points = settledRows.map(({ row, index }) => `
    <circle class="bot-chart-point" cx="${pointX(index).toFixed(1)}"
      cy="${rateY(Number(row.win_rate)).toFixed(1)}" r="4">
      <title>${row.setup_day}：胜${row.wins}/负${row.losses}，胜率${Number(row.win_rate).toFixed(2)}%</title>
    </circle>
  `).join("");
  const labels = daily.map((row, index) => {
    if (index % labelEvery !== 0 && index !== daily.length - 1) return "";
    return `<text class="bot-chart-axis" x="${pointX(index).toFixed(1)}" y="${height - 10}" text-anchor="middle">${row.setup_day.slice(5)}</text>`;
  }).join("");
  target.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="每日胜率和已结算样本趋势">
      ${grid}
      ${bars}
      ${linePoints ? `<polyline class="bot-chart-line" points="${linePoints}"></polyline>` : ""}
      ${points}
      ${labels}
    </svg>
  `;
}

function renderBotStrategyDaily(daily = []) {
  renderBotStrategyChart(daily);
  const body = $("bot-strategy-daily-body");
  if (!body) return;
  if (!daily.length) {
    body.innerHTML = '<tr><td colspan="7">所选范围内还没有每日样本。</td></tr>';
    return;
  }
  body.innerHTML = [...daily].reverse().map((row) => `
    <tr data-strategy-day="${row.setup_day}" class="${row.setup_day === botStrategyDay ? "active" : ""}">
      <td>${strategyDayLabel(row.setup_day)}</td>
      <td>${Number(row.settled || 0)}</td>
      <td>${Number(row.wins || 0)} / ${Number(row.losses || 0)}</td>
      <td>${row.win_rate == null ? "--" : `${Number(row.win_rate).toFixed(2)}%`}</td>
      <td>${strategySigned(row.net_points)}</td>
      <td>${Number(row.open || 0)} / ${Number(row.pending || 0)} / ${Number(row.ambiguous || 0)}</td>
      <td>${Number(row.expired || 0)}</td>
    </tr>
  `).join("");
}

function renderBotStrategyTrials(trials = []) {
  const target = $("bot-strategy-recent");
  if (!target) return;
  if (!trials.length) {
    target.innerHTML = "<p>当前筛选条件下没有逐笔记录。</p>";
    return;
  }
  target.innerHTML = trials.map((trial) => `
    <div class="bot-trial">
      <div class="${escapeHtml(trial.status || "")}">
        <span>${trial.direction === "long" ? "做多" : "做空"}</span>
        <strong>${BOT_STRATEGY_STATUS_LABELS[trial.status] || trial.status || "-"}</strong>
        <small>${trial.resolution_source === "gate_1s_kline" ? "Gate 1秒K线校验" : "Gate 实时价"}</small>
      </div>
      <div>
        <span>设置日 / 时间</span>
        <strong>${strategyDayLabel(trial.setup_day)}<br>${strategyTimestampLabel(trial.created_at)}</strong>
      </div>
      <div>
        <span>设置时价格</span>
        <strong>${priceFormat.format(trial.initial_price)}</strong>
      </div>
      <div>
        <span>入场点位</span>
        <strong>${priceFormat.format(trial.entry_price)}</strong>
      </div>
      <div>
        <span>止损 / 止盈</span>
        <strong>${priceFormat.format(trial.stop_loss)} / ${priceFormat.format(trial.take_profit)}</strong>
      </div>
      <div>
        <span>触发 / 结算观察价</span>
        <strong>
          ${trial.trigger_observed_price == null ? "--" : priceFormat.format(trial.trigger_observed_price)}
          /
          ${trial.exit_observed_price == null ? "--" : priceFormat.format(trial.exit_observed_price)}
        </strong>
      </div>
    </div>
  `).join("");
}

function renderBotStrategyDashboard(data) {
  renderBotStrategySummary(data.summary || {});
  renderBotStrategyDaily(data.daily || []);
  renderBotStrategyTrials(data.trials || []);
  botStrategyNextCursor = data.page?.next_cursor || "";
  $("bot-strategy-prev").disabled = botStrategyPageHistory.length === 0;
  $("bot-strategy-next").disabled = !data.page?.has_more;
  setText("bot-strategy-page", `第 ${botStrategyPageNumber} 页`);
  setText(
    "bot-strategy-detail-title",
    botStrategyDay
      ? `${strategyDayLabel(botStrategyDay)}逐笔记录`
      : "逐笔记录",
  );
  const clearDay = $("bot-strategy-clear-day");
  if (clearDay) clearDay.hidden = !botStrategyDay;
  const directionLabel = botStrategyDirection === "long"
    ? "只看做多"
    : botStrategyDirection === "short"
      ? "只看做空"
      : "全部方向";
  setText("bot-strategy-scope", `累计指标：全部日期 · ${directionLabel}`);
  setText(
    "bot-strategy-freshness",
    `更新：${strategyTimestampLabel(data.generated_at)} · 每日按北京时间点位设置日归属`,
  );
}

function resetBotStrategyPage() {
  botStrategyCursor = "";
  botStrategyNextCursor = "";
  botStrategyPageHistory = [];
  botStrategyPageNumber = 1;
}

async function refreshBotStrategyDashboard({ resetPage = false } = {}) {
  if (resetPage) resetBotStrategyPage();
  if (!botSelectedChatId) {
    renderBotStrategySummary({});
    renderBotStrategyDaily([]);
    renderBotStrategyTrials([]);
    return;
  }
  const requestSequence = ++botStrategyRequestSequence;
  const query = new URLSearchParams({
    market: activeMarket,
    chat_id: botSelectedChatId,
    days: String(botStrategyDays),
    limit: "20",
  });
  if (botStrategyDirection) query.set("direction", botStrategyDirection);
  if (botStrategyStatus) query.set("status", botStrategyStatus);
  if (botStrategyDay) query.set("setup_day", botStrategyDay);
  if (botStrategyCursor) query.set("cursor", botStrategyCursor);
  try {
    const response = await authorizedFetch(`/api/bot/strategy-stats?${query}`);
    const data = await response.json();
    if (!data.ok) throw new Error(data.error || "策略统计暂不可用");
    if (requestSequence !== botStrategyRequestSequence) return;
    if (data.market !== activeMarket) return;
    renderBotStrategyDashboard(data);
  } catch (error) {
    if (requestSequence !== botStrategyRequestSequence) return;
    const target = $("bot-strategy-chart");
    if (target) target.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
  }
}

function renderBotAlerts(data) {
  if (!data?.ok) return;
  botSelectedChatId = data.selected_chat_id || "";
  setText("bot-current-price", priceFormat.format(data.current_price || 0));
  setText("bot-expires-at", formatBotExpiry(data.expires_at));
  const activeAlerts = data.alerts || [];
  botKeyLevelContext = {
    market: data.market || activeMarket,
    chatId: botSelectedChatId,
    activeAlerts: activeAlerts.filter((alert) => alert.status === "active"),
  };
  const alerts = data.today_alerts || activeAlerts;
  const breachedCount = alerts.filter((alert) => alert.status === "breached").length;
  setText("bot-alert-count", String(alerts.length));
  setText(
    "bot-state",
    botSelectedChatId
      ? `${activeAlerts.length} 条活跃 · ${breachedCount} 条已触达`
      : "等待会话",
  );
  if (!botStrategyDirection) renderBotStrategySummary(data.strategy || {});

  const chatSelect = $("bot-chat-select");
  if (chatSelect) {
    const chats = data.chats || [];
    chatSelect.innerHTML = chats.length
      ? chats.map((chat) => `
          <option value="${escapeHtml(chat.chat_id)}" ${chat.chat_id === botSelectedChatId ? "selected" : ""}>
            ${escapeHtml(chat.label)} · ${chat.active_count}条
          </option>
        `).join("")
      : '<option value="">暂无会话</option>';
    chatSelect.value = botSelectedChatId;
  }

  const list = $("bot-alert-list");
  if (!list) return;
  if (!botSelectedChatId) {
    list.innerHTML = "<p>还没有机器人会话。先在企业微信群里 @机器人 发送“黄金 今日点位 A B C D”，这里就会出现这个群。</p>";
    setText("bot-feedback", "网页会复用企业微信群会话发送主动告警。");
    return;
  }
  if (!alerts.length) {
    list.innerHTML = "<p>当前会话今天还没有点位记录。</p>";
    return;
  }
  const statusLabels = {
    active: "监控中",
    breached: "已触达",
    expired: "已过期",
    replaced: "已停用",
    cancelled: "已取消",
  };
  list.innerHTML = alerts.map((alert) => {
    const distance = Number(alert.distance || Math.abs((data.current_price || 0) - alert.level));
    const sideLabel = alert.side === "above" ? "上方" : alert.side === "below" ? "下方" : "当前";
    const status = statusLabels[alert.status] || alert.status || "未知";
    const statusTime = alert.status === "breached"
      ? strategyTimestampLabel(alert.breached_at)
      : alert.status === "active"
        ? `距离 ${distance.toFixed(2)}`
        : strategyTimestampLabel(alert.created_at);
    const reminderTime = alert.last_alert_at
      ? `最后 ${strategyTimestampLabel(alert.last_alert_at)}`
      : "尚未提醒";
    return `
      <div class="bot-alert-row ${escapeHtml(alert.status || "active")}">
        <div class="${alert.side}">
          <span>${sideLabel}点位</span>
          <strong>${priceFormat.format(alert.level)}</strong>
        </div>
        <div class="bot-alert-status ${escapeHtml(alert.status || "active")}">
          <span>状态</span>
          <strong>${escapeHtml(status)}</strong>
          <small>${escapeHtml(statusTime)}</small>
        </div>
        <div>
          <span>提醒</span>
          <strong>${alert.alerts_sent}/${alert.alert_limit}</strong>
          <small>${escapeHtml(reminderTime)}</small>
        </div>
        <div>
          <span>创建价</span>
          <strong>${priceFormat.format(alert.created_price)}</strong>
        </div>
      </div>`;
  }).join("");
  if (latestPayload) {
    renderKeyLevelViews(latestPayload);
    lastChartSignature = "";
    drawSelectedChart(latestPayload, true);
  }
}

async function refreshBotAlerts(chatId = botSelectedChatId) {
  try {
    const query = new URLSearchParams({ market: activeMarket });
    if (chatId) query.set("chat_id", chatId);
    const response = await authorizedFetch(`/api/bot/alerts?${query}`);
    const data = await response.json();
    if (!data.ok) throw new Error(data.error || "机器人设置暂不可用");
    if (data.market !== activeMarket) return;
    const previousChatId = botSelectedChatId;
    renderBotAlerts(data);
    const chatChanged = previousChatId !== botSelectedChatId;
    if (chatChanged) botStrategyDay = "";
    await refreshBotStrategyDashboard({ resetPage: chatChanged });
  } catch (error) {
    setText("bot-state", "读取失败");
    setText("bot-feedback", error.message);
  }
}

async function saveBotLevels(event) {
  event.preventDefault();
  const levels = parseBotLevels($("bot-level-input")?.value);
  if (!botSelectedChatId) {
    setText("bot-feedback", "还没有企业微信会话，先在群里 @机器人 设置一次点位。");
    return;
  }
  if (!levels.length) {
    setText("bot-feedback", "请输入至少一个有效点位。");
    return;
  }
  setBotBusy(true);
  try {
    const response = await authorizedFetch("/api/bot/alerts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        market: activeMarket,
        chat_id: botSelectedChatId,
        levels,
      }),
    });
    const data = await response.json();
    if (!data.ok) throw new Error(data.error || "保存失败");
    renderBotAlerts(data);
    botStrategyDay = "";
    await refreshBotStrategyDashboard({ resetPage: true });
    setText("bot-feedback", `已保存 ${data.saved_count || levels.length} 条今日点位。`);
  } catch (error) {
    setText("bot-feedback", error.message);
  } finally {
    setBotBusy(false);
  }
}

async function cancelBotLevels() {
  if (!botSelectedChatId) {
    setText("bot-feedback", "还没有可取消的企业微信会话。");
    return;
  }
  if (!window.confirm("确认取消当前会话今天的全部机器人点位？")) return;
  setBotBusy(true);
  try {
    const response = await authorizedFetch("/api/bot/alerts/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        market: activeMarket,
        chat_id: botSelectedChatId,
      }),
    });
    const data = await response.json();
    if (!data.ok) throw new Error(data.error || "取消失败");
    renderBotAlerts(data);
    botStrategyDay = "";
    await refreshBotStrategyDashboard({ resetPage: true });
    setText("bot-feedback", `已取消 ${data.cancelled_count || 0} 条今日点位。`);
  } catch (error) {
    setText("bot-feedback", error.message);
  } finally {
    setBotBusy(false);
  }
}

function paperJournalKey() {
  return `${MARKET_CONFIGS[activeMarket].journalPrefix}-scalp-paper-journal-v1`;
}

function loadPaperTrades() {
  try {
    const saved = JSON.parse(localStorage.getItem(paperJournalKey()) || "[]");
    return Array.isArray(saved) ? saved.slice(-100) : [];
  } catch (_error) {
    return [];
  }
}

function savePaperTrades() {
  try {
    localStorage.setItem(paperJournalKey(), JSON.stringify(paperTrades.slice(-100)));
  } catch (_error) {
    // Browser storage can be unavailable in private browsing; live signals still work.
  }
}

function csvCell(value) {
  const text = value == null ? "" : String(value);
  return /[",\r\n]/u.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function snapshotFrame(frame) {
  if (!frame) return null;
  return {
    close: frame.close,
    ema5: frame.ema5,
    ema10: frame.ema10,
    ema20: frame.ema20,
    ema50: frame.ema50,
    rsi14: frame.rsi14,
    atr14: frame.atr14,
    support: frame.support,
    resistance: frame.resistance,
    bias: frame.bias,
    score: frame.score,
  };
}

function buildTradeAudit(strategy, data) {
  const ticker = data.ticker;
  const triggerCandle = data.candles?.["1m"]?.find(
    (candle) => candle.timestamp === strategy.triggerTimestamp,
  ) || null;
  const proxy = data.volume_proxy;
  const volume = data.live_volume
    || proxy?.markets?.find((item) => item.symbol === proxy.active_symbol)
    || proxy?.markets?.[0]
    || null;
  return {
    schemaVersion: 2,
    market: data.market || {
      id: activeMarket,
      symbol: data.symbol,
    },
    strategyVersion: strategy.version,
    capturedAt: Number(ticker.timestamp_ms) || Date.now(),
    decisionLabel: strategy.label,
    decisionMessage: strategy.message,
    checklist: strategy.checklist.map((check) => ({
      label: check.label,
      pass: Boolean(check.pass),
      neutral: Boolean(check.neutral),
      detail: check.detail,
    })),
    ticker: {
      last: ticker.last,
      bid: ticker.bid,
      ask: ticker.ask,
      spread: ticker.spread,
      dayHigh: ticker.high,
      dayLow: ticker.low,
      changePercent: ticker.change_percent,
      status: ticker.status,
    },
    proposedEntry: strategy.entry,
    proposedStop: strategy.stop,
    proposedTarget: strategy.target,
    proposedRisk: strategy.risk,
    rewardRisk: strategy.rewardRisk,
    triggerCandle,
    trend: strategy.trend,
    supportZone: strategy.zones?.support || null,
    resistanceZone: strategy.zones?.resistance || null,
    volume: volume ? {
      symbol: volume.symbol,
      rvol: volume.rvol,
      deltaPercent: volume.delta_percent,
      tradeCount60s: volume.trade_count_60s,
      buyQuote60s: volume.buy_quote_60s,
      sellQuote60s: volume.sell_quote_60s,
      freshnessMs: volume.freshness_ms,
    } : null,
    frames: {
      "1m": snapshotFrame(data.frames?.["1m"]),
      "5m": snapshotFrame(data.frames?.["5m"]),
      "15m": snapshotFrame(data.frames?.["15m"]),
    },
    marketPlan: Array.isArray(data.plan) ? [...data.plan] : [],
  };
}

function exportPaperJournal() {
  if (!paperTrades.length) {
    window.alert("当前还没有模拟交易记录；策略触发第一笔后即可导出完整验证 CSV。");
    return;
  }
  const baseColumns = [
    ["schema_version", "记录版本"],
    ["market", "市场"],
    ["symbol", "品种"],
    ["signature", "信号编号"],
    ["opened_at", "开仓时间"],
    ["closed_at", "平仓时间"],
    ["direction", "方向"],
    ["decision_label", "策略动作"],
    ["entry_reason", "为什么做多或做空"],
    ["decision_checks", "全部入场判断"],
    ["exit_reason", "为什么退出"],
    ["status", "结果状态"],
    ["result_r", "结果R"],
    ["score", "信号评分"],
    ["duration_seconds", "持仓秒数"],
    ["entry", "入场价"],
    ["stop", "止损价"],
    ["target", "止盈价"],
    ["exit", "退出价"],
    ["proposed_entry", "策略计划入场"],
    ["proposed_stop", "策略计划止损"],
    ["proposed_target", "策略计划止盈"],
    ["risk_distance", "风险距离"],
    ["reward_risk", "计划盈亏比"],
    ["last", "信号时最新价"],
    ["bid", "信号时买价"],
    ["ask", "信号时卖价"],
    ["spread", "信号时点差"],
    ["day_high", "当日最高"],
    ["day_low", "当日最低"],
    ["day_change_percent", "当日涨跌幅%"],
    ["market_status", "市场状态"],
    ["exit_last", "退出时最新价"],
    ["exit_bid", "退出时买价"],
    ["exit_ask", "退出时卖价"],
    ["exit_spread", "退出时点差"],
    ["trigger_time", "触发K线时间"],
    ["trigger_open", "触发K线开盘"],
    ["trigger_high", "触发K线最高"],
    ["trigger_low", "触发K线最低"],
    ["trigger_close", "触发K线收盘"],
    ["trend_bias", "趋势方向"],
    ["trend_detail", "趋势判断原因"],
    ["support_zone", "策略支撑区域"],
    ["support_sources", "支撑依据"],
    ["support_touches", "支撑结构触点"],
    ["resistance_zone", "策略阻力区域"],
    ["resistance_sources", "阻力依据"],
    ["resistance_touches", "阻力结构触点"],
    ["volume_symbol", "量能市场"],
    ["volume_rvol", "相对成交量RVOL"],
    ["volume_delta_percent", "主动买卖差%"],
    ["volume_trade_count_60s", "近60秒成交笔数"],
    ["volume_buy_quote_60s", "近60秒主动买入额"],
    ["volume_sell_quote_60s", "近60秒主动卖出额"],
    ["volume_freshness_ms", "量能新鲜度ms"],
    ["market_plan", "当时行情提示"],
  ];
  const frameFields = [
    ["close", "收盘"],
    ["ema5", "EMA5"],
    ["ema10", "EMA10"],
    ["ema20", "EMA20"],
    ["ema50", "EMA50"],
    ["rsi14", "RSI14"],
    ["atr14", "ATR14"],
    ["support", "近端支撑"],
    ["resistance", "近端阻力"],
    ["bias", "周期方向"],
    ["score", "周期评分"],
  ];
  const frameColumns = ["1m", "5m", "15m"].flatMap((period) =>
    frameFields.map(([field, label]) => [
      `${period}_${field}`,
      `${period} ${label}`,
    ]));
  const columns = [...baseColumns, ...frameColumns];
  const statusLabels = {
    open: "进行中",
    target: "止盈",
    stop: "止损",
    timeout: "时间退出",
  };
  const rows = paperTrades.map((trade) => {
    const audit = trade.audit || {};
    const ticker = audit.ticker || {};
    const trigger = audit.triggerCandle || {};
    const support = audit.supportZone || {};
    const resistance = audit.resistanceZone || {};
    const volume = audit.volume || {};
    const exitSnapshot = trade.exitSnapshot || {};
    const frames = audit.frames || {};
    const values = {
      schema_version: audit.schemaVersion || 1,
      market: audit.market?.display_name || audit.market?.id || activeMarket,
      symbol: audit.market?.symbol || MARKET_CONFIGS[activeMarket].symbol,
      signature: trade.signature,
      opened_at: new Date(trade.openedAt).toISOString(),
      closed_at: trade.closedAt ? new Date(trade.closedAt).toISOString() : "",
      direction: trade.direction === "long" ? "做多" : "做空",
      decision_label: audit.decisionLabel || "",
      entry_reason: audit.decisionMessage || "",
      decision_checks: audit.checklist
        ?.map((check) => `${check.pass ? "通过" : check.neutral ? "中性" : "未通过"}-${check.label}:${check.detail}`)
        .join(" | ") || "",
      exit_reason: trade.exitReason || "",
      status: statusLabels[trade.status] || trade.status,
      result_r: trade.status === "open" ? "" : trade.resultR,
      score: trade.score,
      duration_seconds: trade.closedAt
        ? Math.round((trade.closedAt - trade.openedAt) / 1000)
        : "",
      entry: trade.entry,
      stop: trade.stop,
      target: trade.target,
      exit: trade.exit ?? "",
      proposed_entry: audit.proposedEntry,
      proposed_stop: audit.proposedStop,
      proposed_target: audit.proposedTarget,
      risk_distance: trade.risk,
      reward_risk: audit.rewardRisk,
      last: ticker.last,
      bid: ticker.bid,
      ask: ticker.ask,
      spread: ticker.spread,
      day_high: ticker.dayHigh,
      day_low: ticker.dayLow,
      day_change_percent: ticker.changePercent,
      market_status: ticker.status,
      exit_last: exitSnapshot.last,
      exit_bid: exitSnapshot.bid,
      exit_ask: exitSnapshot.ask,
      exit_spread: exitSnapshot.spread,
      trigger_time: trigger.timestamp
        ? new Date(trigger.timestamp * 1000).toISOString()
        : "",
      trigger_open: trigger.open,
      trigger_high: trigger.high,
      trigger_low: trigger.low,
      trigger_close: trigger.close,
      trend_bias: audit.trend?.bias,
      trend_detail: audit.trend?.detail,
      support_zone: support.lower != null
        ? `${support.lower}-${support.upper}`
        : "",
      support_sources: support.sources?.join("+") || "",
      support_touches: support.touches,
      resistance_zone: resistance.lower != null
        ? `${resistance.lower}-${resistance.upper}`
        : "",
      resistance_sources: resistance.sources?.join("+") || "",
      resistance_touches: resistance.touches,
      volume_symbol: volume.symbol,
      volume_rvol: volume.rvol,
      volume_delta_percent: volume.deltaPercent,
      volume_trade_count_60s: volume.tradeCount60s,
      volume_buy_quote_60s: volume.buyQuote60s,
      volume_sell_quote_60s: volume.sellQuote60s,
      volume_freshness_ms: volume.freshnessMs,
      market_plan: audit.marketPlan?.join(" | ") || "",
    };
    ["1m", "5m", "15m"].forEach((period) => {
      frameFields.forEach(([field]) => {
        values[`${period}_${field}`] = frames[period]?.[field] ?? "";
      });
    });
    return columns.map(([key]) => csvCell(values[key])).join(",");
  });
  const csv = `\uFEFF${columns.map(([, label]) => csvCell(label)).join(",")}\r\n${rows.join("\r\n")}`;
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  const day = new Date().toISOString().slice(0, 10);
  anchor.href = url;
  anchor.download = `${MARKET_CONFIGS[activeMarket].journalPrefix}-scalp-paper-journal-${day}.csv`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function updateRiskCalculator(strategy) {
  const balance = Number($("risk-balance")?.value);
  const riskPercent = Number($("risk-percent")?.value);
  const contractOunces = Number($("contract-ounces")?.value);
  if (
    !Number.isFinite(strategy?.entry)
    || !Number.isFinite(strategy?.stop)
  ) {
    setText("risk-lots", "--");
    setText(
      "risk-usd",
      Number.isFinite(balance) && Number.isFinite(riskPercent)
        ? `风险 $${(balance * riskPercent / 100).toFixed(2)}`
        : "风险 --",
    );
    return;
  }
  const riskUsd = Math.max(0, balance * riskPercent / 100);
  const distance = Math.abs(strategy.entry - strategy.stop);
  const lots = distance > 0 && contractOunces > 0
    ? riskUsd / (distance * contractOunces)
    : 0;
  const sizing = { riskUsd, distance, lots };
  const displaySize = activeMarket === "btc"
    ? Math.floor(sizing.lots)
    : Number(sizing.lots.toFixed(3));
  setText("risk-lots", displaySize > 0 ? String(displaySize) : "--");
  setText(
    "risk-usd",
    `风险 $${sizing.riskUsd.toFixed(2)} · 止损距离 ${sizing.distance.toFixed(2)}`,
  );
}

function renderPaperJournal() {
  const closed = paperTrades.filter((trade) => trade.status !== "open");
  const wins = closed.filter((trade) => trade.resultR > 0);
  const totalR = closed.reduce((sum, trade) => sum + trade.resultR, 0);
  const expectancy = closed.length ? totalR / closed.length : 0;
  setText("journal-count", String(closed.length));
  setText(
    "journal-win-rate",
    closed.length ? `${((wins.length / closed.length) * 100).toFixed(1)}%` : "--",
  );
  setText(
    "journal-expectancy",
    closed.length ? `${expectancy >= 0 ? "+" : ""}${expectancy.toFixed(2)} R` : "-- R",
  );
  setText("journal-total-r", `${totalR >= 0 ? "+" : ""}${totalR.toFixed(2)} R`);
  $("journal-total-r").style.color = totalR > 0
    ? "#2ecb91"
    : totalR < 0
      ? "#ff596d"
      : "";
  const recent = [...paperTrades].reverse().slice(0, 6);
  $("journal-list").innerHTML = recent.length
    ? recent.map((trade) => {
      const time = new Date(trade.openedAt).toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
      });
      const directionText = trade.direction === "long" ? "做多" : "做空";
      const statusText = trade.status === "open"
        ? "持仓模拟"
        : trade.status === "target"
          ? "止盈"
          : trade.status === "stop"
            ? "止损"
            : "时间退出";
      const resultText = trade.status === "open"
        ? "进行中"
        : `${trade.resultR >= 0 ? "+" : ""}${trade.resultR.toFixed(2)} R`;
      const resultClass = trade.status === "open"
        ? ""
        : trade.resultR >= 0
          ? "positive"
          : "negative";
      return `
        <div class="journal-row">
          <span>${time}</span>
          <strong class="${trade.direction}">${directionText}</strong>
          <span>${statusText} · ${priceFormat.format(trade.entry)}</span>
          <strong class="${resultClass}">${resultText}</strong>
        </div>`;
    }).join("")
    : "<p>暂无模拟交易。保持页面打开，触发后将按买卖价、止损、1.5R止盈和8分钟时限自动记录。</p>";
}

function processPaperJournal(strategy, data) {
  const ticker = data?.ticker;
  if (!strategy || !ticker) return;
  const now = Number(ticker.timestamp_ms) || Date.now();
  let changed = false;
  paperTrades.forEach((trade) => {
    if (trade.status !== "open") return;
    const exitPrice = trade.direction === "long" ? ticker.bid : ticker.ask;
    const reachedStop = trade.direction === "long"
      ? exitPrice <= trade.stop
      : exitPrice >= trade.stop;
    const reachedTarget = trade.direction === "long"
      ? exitPrice >= trade.target
      : exitPrice <= trade.target;
    const timedOut = now - trade.openedAt >= trade.timeoutMinutes * 60_000;
    if (!reachedStop && !reachedTarget && !timedOut) return;
    trade.closedAt = now;
    trade.exit = reachedStop
      ? trade.stop
      : reachedTarget
        ? trade.target
        : exitPrice;
    trade.status = reachedStop ? "stop" : reachedTarget ? "target" : "timeout";
    trade.exitReason = reachedStop
      ? "价格触及策略硬止损"
      : reachedTarget
        ? "价格触及1.5R固定止盈"
        : "持仓达到8分钟，按时间规则退出";
    trade.exitSnapshot = {
      timestampMs: now,
      last: ticker.last,
      bid: ticker.bid,
      ask: ticker.ask,
      spread: ticker.spread,
    };
    const rawR = trade.direction === "long"
      ? (trade.exit - trade.entry) / trade.risk
      : (trade.entry - trade.exit) / trade.risk;
    trade.resultR = Number(rawR.toFixed(3));
    changed = true;
  });

  const triggered = strategy.state === "long" || strategy.state === "short";
  const alreadyRecorded = paperTrades.some(
    (trade) => trade.signature === strategy.signature,
  );
  const hasOpenTrade = paperTrades.some((trade) => trade.status === "open");
  if (triggered && !alreadyRecorded && !hasOpenTrade) {
    const direction = strategy.state;
    const entry = direction === "long" ? ticker.ask : ticker.bid;
    const stop = strategy.stop;
    const risk = Math.abs(entry - stop);
    if (risk > 0) {
      paperTrades.push({
        market: activeMarket,
        symbol: data.symbol,
        signature: strategy.signature,
        direction,
        entry,
        stop,
        target: direction === "long"
          ? entry + risk * strategy.rewardRisk
          : entry - risk * strategy.rewardRisk,
        risk,
        openedAt: now,
        timeoutMinutes: strategy.timeoutMinutes,
        score: strategy.score,
        status: "open",
        resultR: 0,
        audit: buildTradeAudit(strategy, data),
      });
      changed = true;
    }
  }
  if (changed) savePaperTrades();
  renderPaperJournal();
}

function renderScalpStrategy(data) {
  const strategy = data.strategy;
  if (!strategy) return;
  latestScalpResult = strategy;
  const card = document.querySelector(".scalp-card");
  card.dataset.direction = strategy.direction || "neutral";
  card.dataset.strategyState = strategy.state || "wait";
  $("scalp-state").className = `scalp-state ${strategy.state}`;
  setText("scalp-label", strategy.label);
  setText("scalp-score", `${strategy.score} / 100`);
  const action = strategy.state === "long"
    ? "做多模拟已触发"
    : strategy.state === "short"
      ? "做空模拟已触发"
      : strategy.state === "armed_long"
        ? "做多计划就绪，尚未入场"
        : strategy.state === "armed_short"
          ? "做空计划就绪，尚未入场"
          : strategy.state === "avoid"
            ? "放弃本次，不入场"
            : strategy.direction === "neutral"
              ? "等待方向，尚未入场"
              : "继续等待，尚未入场";
  setText("scalp-action", action);
  const background = strategy.direction === "short"
    ? "趋势背景偏空"
    : strategy.direction === "long"
      ? "趋势背景偏多"
      : "趋势背景尚未统一";
  setText(
    "scalp-message",
    ["wait", "armed_long", "armed_short"].includes(strategy.state)
      ? `${background}；${strategy.message}。`
      : strategy.message,
  );
  renderDirectionExplanation(strategy.trend);
  setText(
    "scalp-entry",
    Number.isFinite(strategy.entry) ? priceFormat.format(strategy.entry) : "--",
  );
  setText(
    "scalp-stop",
    Number.isFinite(strategy.stop) ? priceFormat.format(strategy.stop) : "--",
  );
  setText(
    "scalp-target",
    Number.isFinite(strategy.target) ? priceFormat.format(strategy.target) : "--",
  );
  setText(
    "scalp-rr",
    `${strategy.rewardRisk.toFixed(1)}R · ${strategy.timeoutMinutes}分钟`,
  );
  $("scalp-checklist").innerHTML = strategy.checklist.map((check) => {
    const tone = check.pass ? "pass" : check.neutral ? "neutral" : "fail";
    return `
      <div class="${tone}">
        <i></i>
        <span class="check-label">
          ${check.label}
          <button class="info-button" type="button" data-help-key="${check.key}" aria-label="查看${check.label}公式">i</button>
        </span>
        <small>${check.detail}</small>
      </div>`;
  }).join("");
  const activeZone = strategy.direction === "short"
    ? strategy.zones.resistance
    : strategy.zones.support;
  setText(
    "scalp-zone",
    activeZone
      ? `${priceFormat.format(activeZone.lower)}–${priceFormat.format(activeZone.upper)}`
      : "--",
  );
  setText(
    "scalp-zone-detail",
    activeZone
      ? `${activeZone.sources.join(" + ")} · ${activeZone.touches}次结构触点`
      : "至少两个周期或枢轴重合才有效",
  );
  updateRiskCalculator(strategy);
  processPaperJournal(strategy, data);
}

function renderDirectionExplanation(trend) {
  const checks = Array.isArray(trend?.checks) ? trend.checks : [];
  const directionText = trend?.bias === "short"
    ? "趋势背景偏空：暂时过滤掉做多形态"
    : trend?.bias === "long"
      ? "趋势背景偏多：暂时过滤掉做空形态"
      : trend?.candidate === "short"
        ? "趋势背景不明确：下面展示较接近的偏空条件"
        : trend?.candidate === "long"
          ? "趋势背景不明确：下面展示较接近的偏多条件"
          : "方向数据还不足";
  setText("direction-readable-title", directionText);
  const persistenceText = trend?.bias === "short"
    ? "为什么可能持续偏空：EMA20 和 EMA50 是慢变量，只要四项仍同时满足，背景就保持偏空。它只过滤方向，不代表现在做空。"
    : trend?.bias === "long"
      ? "为什么可能持续偏多：EMA20 和 EMA50 是慢变量，只要四项仍同时满足，背景就保持偏多。它只过滤方向，不代表现在做多。"
      : "至少一项方向条件尚未统一，所以暂时不选多空；当前不会因为接近某个方向就入场。";
  setText("direction-persistence", persistenceText);
  $("direction-readable-checks").innerHTML = checks.length
    ? checks.map((check) => `
      <div class="${check.pass ? "pass" : "fail"}">
        <b>${check.pass ? "通过" : "未通过"}</b>
        <span>
          ${check.label}
          <button class="info-button" type="button" data-help-key="${check.key}" aria-label="查看${check.label}的名词解释">i</button>
        </span>
        <small>${check.detail}</small>
        <em>为什么要看：${check.why}</em>
      </div>`).join("")
    : "<p>等待足够的已收盘5分钟和15分钟K线。</p>";
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
  context.strokeStyle = color;
  context.lineWidth = 1.5;
  context.beginPath();
  context.moveTo(labelLeft - 9, priceY);
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

function drawSupportZone(context, width, padding, y, zone) {
  if (
    !zone
    || !Number.isFinite(zone.center)
    || !Number.isFinite(zone.lower)
    || !Number.isFinite(zone.upper)
  ) return;
  const top = y(zone.upper);
  const bottom = y(zone.lower);
  context.save();
  context.fillStyle = "rgba(46,203,145,.075)";
  context.fillRect(
    padding.left,
    Math.min(top, bottom),
    width - padding.left - padding.right,
    Math.max(2, Math.abs(bottom - top)),
  );
  context.strokeStyle = "#2ecb91";
  context.fillStyle = "#50d6a2";
  context.lineWidth = 1.4;
  context.setLineDash([7, 5]);
  context.beginPath();
  context.moveTo(padding.left, y(zone.center));
  context.lineTo(width - padding.right, y(zone.center));
  context.stroke();
  context.setLineDash([]);
  context.font = "700 9px ui-sans-serif, system-ui";
  context.textAlign = "left";
  context.fillText(
    `近端支撑 ${priceFormat.format(zone.center)}`,
    padding.left + 5,
    y(zone.center) - 5,
  );
  context.restore();
}

function drawResistanceZone(context, width, padding, y, zone) {
  if (
    !zone
    || !Number.isFinite(zone.center)
    || !Number.isFinite(zone.lower)
    || !Number.isFinite(zone.upper)
  ) return;
  const top = y(zone.upper);
  const bottom = y(zone.lower);
  context.save();
  context.fillStyle = "rgba(255,89,109,.065)";
  context.fillRect(
    padding.left,
    Math.min(top, bottom),
    width - padding.left - padding.right,
    Math.max(2, Math.abs(bottom - top)),
  );
  context.strokeStyle = "#ff596d";
  context.fillStyle = "#ff7a8d";
  context.lineWidth = 1.4;
  context.setLineDash([7, 5]);
  context.beginPath();
  context.moveTo(padding.left, y(zone.center));
  context.lineTo(width - padding.right, y(zone.center));
  context.stroke();
  context.setLineDash([]);
  context.font = "700 9px ui-sans-serif, system-ui";
  context.textAlign = "left";
  context.fillText(
    `近端阻力 ${priceFormat.format(zone.center)}`,
    padding.left + 5,
    y(zone.center) - 5,
  );
  context.restore();
}

function drawCandleChart(allCandles, pivots, supportZone, resistanceZone) {
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
  const visibleSupport = (
    supportZone
    && supportZone.center >= rawCandleMin - candleRange * 0.75
    && supportZone.center <= rawCandleMax + candleRange * 0.25
  ) ? supportZone : null;
  const visibleResistance = (
    resistanceZone
    && resistanceZone.center >= rawCandleMin - candleRange * 0.25
    && resistanceZone.center <= rawCandleMax + candleRange * 0.75
  ) ? resistanceZone : null;
  if (visibleSupport) {
    overlayValues.push(visibleSupport.lower, visibleSupport.upper);
  }
  if (visibleResistance) {
    overlayValues.push(visibleResistance.lower, visibleResistance.upper);
  }
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
  drawSupportZone(context, width, padding, y, visibleSupport);
  drawResistanceZone(context, width, padding, y, visibleResistance);

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

function drawTickChart(ticks, supportZone, resistanceZone) {
  if (!ticks || ticks.length < 2) return;
  const { empty, context, width, height } = prepareCanvas();
  empty.style.display = "none";
  const padding = { top: 12, right: 65, bottom: 25, left: 8 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const prices = ticks.flatMap((tick) => [tick.bid, tick.ask, tick.last]);
  const rawMin = Math.min(...prices);
  const rawMax = Math.max(...prices);
  const rawRange = Math.max(rawMax - rawMin, 0.05);
  const margin = Math.max(rawRange * 0.16, 0.08);
  const visibleSupport = (
    supportZone
    && supportZone.center >= rawMin - Math.max(rawRange * 2, 0.5)
    && supportZone.center <= rawMax + margin
  ) ? supportZone : null;
  const visibleResistance = (
    resistanceZone
    && resistanceZone.center >= rawMin - margin
    && resistanceZone.center <= rawMax + Math.max(rawRange * 2, 0.5)
  ) ? resistanceZone : null;
  const min = visibleSupport
    ? Math.min(rawMin - margin, visibleSupport.lower - margin)
    : rawMin - margin;
  const max = visibleResistance
    ? Math.max(rawMax + margin, visibleResistance.upper + margin)
    : rawMax + margin;
  const x = (index) => padding.left + (index / Math.max(1, ticks.length - 1)) * plotWidth;
  const y = (price) => padding.top + ((max - price) / (max - min)) * plotHeight;

  context.clearRect(0, 0, width, height);
  drawGrid(context, width, height, padding, min, max);
  drawSupportZone(context, width, padding, y, visibleSupport);
  drawResistanceZone(context, width, padding, y, visibleResistance);

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

function chartFocusTimestampMs(data) {
  if (chartMode === "tick") {
    const timestampMs = Number(data?.ticks?.at(-1)?.timestamp_ms);
    return Number.isFinite(timestampMs) ? timestampMs : null;
  }
  const intervalSeconds = chartMode === "1m" ? 60 : 300;
  const liveCandles = mergeLiveCandle(
    data?.candles?.[chartMode] || [],
    data?.ticks || [],
    intervalSeconds,
  );
  const timestamp = Number(liveCandles.at(-1)?.timestamp);
  return Number.isFinite(timestamp) ? timestamp * 1000 : null;
}

function drawSelectedChart(data, force = false) {
  const keyLevels = displayKeyLevels(data);
  const supportZone = levelZone(keyLevels.support, data);
  const resistanceZone = levelZone(keyLevels.resistance, data);
  const levelSignature = `${keyLevels.source}:${keyLevels.support ?? ""}:${keyLevels.resistance ?? ""}`;
  if (chartMode === "tick") {
    const ticks = data.ticks || [];
    chartFocusMs = chartFocusTimestampMs(data);
    const signature = ticks.length
      ? `${ticks.at(-1).timestamp_ms}:${ticks.length}:${levelSignature}`
      : levelSignature;
    if (force || signature !== lastChartSignature) {
      drawTickChart(ticks, supportZone, resistanceZone);
    }
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
  chartFocusMs = Number.isFinite(Number(current?.timestamp))
    ? Number(current.timestamp) * 1000
    : chartFocusMs;
  const settingsSignature = Object.entries(enabledIndicators)
    .map(([key, value]) => `${key}:${value ? 1 : 0}`)
    .join(",");
  const signature = `${chartMode}:${data.feed.sequence}:${current.timestamp}:${current.close}:${current.high}:${current.low}:${strategyEnabled}:${settingsSignature}:${levelSignature}`;
  if (force || signature !== lastChartSignature) {
    drawCandleChart(
      liveCandles,
      data.daily_pivots,
      supportZone,
      resistanceZone,
    );
  }
  lastChartSignature = signature;
}

function redrawChartAndCalendar(data, force = true) {
  drawSelectedChart(data, force);
  renderMarketCalendar(data.market_calendar, chartFocusMs);
}

function render(data) {
  const ticker = data.ticker;
  if (clientTicks.at(-1)?.timestamp_ms !== ticker.timestamp_ms) {
    clientTicks.push({
      timestamp_ms: ticker.timestamp_ms,
      last: ticker.last,
      bid: ticker.bid,
      ask: ticker.ask,
    });
    if (clientTicks.length > 240) clientTicks.shift();
  }
  data.ticks = [...clientTicks];
  latestPayload = data;
  const tone = ticker.change_percent > 0 ? "up" : ticker.change_percent < 0 ? "down" : "neutral";

  setText("market-status", marketStatusText(ticker, data.feed?.source_age_ms));
  setText("updated-time", new Date(ticker.timestamp_ms).toLocaleTimeString("zh-CN", { hour12: false }));
  setText("feed-latency", `接口 ${data.feed.latency_ms.toFixed(0)} ms`);
  setText("frequency-badge", `EDGE · ${data.feed.quote_hz.toFixed(1)} Hz`);
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

  renderFrames(data.frames);
  renderVolume(data.volume_proxy, data.live_volume);
  chartFocusMs = chartFocusTimestampMs(data);
  renderMarketCalendar(data.market_calendar, chartFocusMs);
  renderScalpStrategy(data);
  drawSelectedChart(data);

  renderKeyLevelViews(data);
}

function marketStatusText(ticker, sourceAgeMs) {
  const status = String(ticker?.status || "").toLowerCase();
  if (status === "closed") {
    const nextOpen = Number(ticker.next_open_time || 0);
    return nextOpen > 0
      ? `市场休市 · ${sessionTime(nextOpen)}开市`
      : "市场休市";
  }
  if (status === "open" || status === "trading") {
    if (Number(ticker.trade_mode) === 0) return "暂不可交易";
    if (Number(sourceAgeMs) > 120000) return "行情停滞";
    const closeTime = Number(ticker.close_time || 0);
    return closeTime > Date.now() / 1000
      ? `市场交易中 · ${sessionTime(closeTime)}闭市`
      : "市场交易中";
  }
  return status ? `市场状态：${status}` : "市场状态未知";
}

function sessionTime(timestampSeconds) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(Number(timestampSeconds) * 1000));
}

async function refresh() {
  const requestedMarket = activeMarket;
  try {
    const response = await authorizedFetch(`/api/snapshot?market=${requestedMarket}`);
    const data = await response.json();
    if (!data.ok) throw new Error(data.error || "行情暂不可用");
    if (requestedMarket !== activeMarket) return;
    render(data);
  } catch (error) {
    setText("market-status", "连接重试中");
    setText("alert-line", error.message);
  }
}

async function refreshQuote() {
  if (!latestPayload) return;
  const requestedMarket = activeMarket;
  try {
    const response = await authorizedFetch(`/api/quote?market=${requestedMarket}`);
    const data = await response.json();
    if (!data.ok) throw new Error(data.error || "报价暂不可用");
    if (requestedMarket !== activeMarket) return;
    latestPayload.ticker = data.ticker;
    latestPayload.feed = { ...latestPayload.feed, ...data.feed };
    if (data.live_volume) latestPayload.live_volume = data.live_volume;
    if (data.strategy) latestPayload.strategy = data.strategy;
    render(latestPayload);
  } catch (error) {
    setText("market-status", "报价重试中");
    setText("alert-line", error.message);
  }
}

window.addEventListener("resize", () => {
  if (latestPayload) redrawChartAndCalendar(latestPayload, true);
});

document.querySelectorAll(".chart-mode").forEach((button) => {
  button.addEventListener("click", () => {
    chartMode = button.dataset.mode;
    document.querySelectorAll(".chart-mode").forEach((item) => {
      item.classList.toggle("active", item === button);
    });
    setText("chart-title", chartMode === "tick" ? "Tick 实时报价" : `${chartMode === "1m" ? "1分钟" : "5分钟"} K线`);
    lastChartSignature = "";
    if (latestPayload) redrawChartAndCalendar(latestPayload, true);
  });
});

const scalpToggle = $("scalp-toggle");
if (scalpToggle) {
  setScalpExpanded(false);
  scalpToggle.addEventListener("click", () => {
    setScalpExpanded(scalpToggle.getAttribute("aria-expanded") !== "true");
  });
}

function applyMarketUi() {
  const config = MARKET_CONFIGS[activeMarket];
  $("hypothesis-link").href = `/hypotheses?market=${activeMarket}`;
  setText("brand-mark", config.mark);
  $("brand-mark").classList.toggle("btc", activeMarket === "btc");
  setText("brand-eyebrow", config.eyebrow);
  setText("brand-title", config.title);
  setText("volume-eyebrow", config.volumeEyebrow);
  setText("volume-title", config.volumeTitle);
  setText("volume-note", config.volumeNote);
  setText("bot-title", `${activeMarket === "btc" ? "BTC" : "黄金"}机器人点位告警`);
  setText("contract-size-label", config.contractLabel);
  setText("position-unit-label", config.positionLabel);
  setText(
    "risk-note",
    activeMarket === "btc"
      ? "Gate 当前 BTC_USDT 每张为 0.0001 BTC；实际下单仍需核对合约规格、最小张数、手续费与资金费率。禁止补仓、扛单和马丁。"
      : "下单前必须核对你的交易平台合约规格与最小手数；禁止补仓、扛单和马丁。",
  );
  setText(
    "journal-description",
    `自动保存${activeMarket === "btc" ? "BTC永续" : "黄金"}触发时的完整价格、指标与决策原因`,
  );
  const contractInput = $("contract-ounces");
  contractInput.min = String(config.contractMin);
  contractInput.step = String(config.contractStep);
  contractInput.value = String(config.contractUnit);
  $("price-chart").setAttribute(
    "aria-label",
    `${config.symbol}实时行情图`,
  );
  document.querySelectorAll(".market-option").forEach((button) => {
    const selected = button.dataset.market === activeMarket;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
  renderPaperJournal();
}

function switchMarket(nextMarket) {
  if (!MARKET_CONFIGS[nextMarket] || nextMarket === activeMarket) return;
  activeMarket = nextMarket;
  localStorage.setItem(ACTIVE_MARKET_KEY, activeMarket);
  latestPayload = null;
  latestScalpResult = null;
  lastChartSignature = "";
  clientTicks.length = 0;
  paperTrades = loadPaperTrades();
  setText("market-status", "正在切换");
  setText("alert-line", "正在获取新的行情数据…");
  setText("bot-state", "读取中");
  setText("bot-feedback", "");
  setText("last-price", "----.--");
  botSelectedChatId = "";
  botStrategyDay = "";
  resetBotStrategyPage();
  applyMarketUi();
  refresh();
  refreshBotAlerts("");
}

document.querySelectorAll(".market-option").forEach((button) => {
  button.addEventListener("click", () => switchMarket(button.dataset.market));
});

document.addEventListener("click", (event) => {
  const helpButton = event.target.closest("[data-help-key]");
  if (helpButton) {
    event.preventDefault();
    event.stopPropagation();
    openStrategyHelp(helpButton.dataset.helpKey, helpButton);
    return;
  }
  if (event.target.closest("#strategy-help-popover")) return;
  closeStrategyHelp();
});

$("strategy-help-close")?.addEventListener("click", closeStrategyHelp);
$("strategy-help-link")?.addEventListener("click", (event) => {
  const href = event.currentTarget.getAttribute("href");
  if (!href || href === "#") return;
  event.preventDefault();
  window.open(href, "_blank", "noopener,noreferrer");
});
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeStrategyHelp();
});
window.addEventListener("resize", closeStrategyHelp);

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
      if (latestPayload) redrawChartAndCalendar(latestPayload, true);
    });
  });
  master.addEventListener("change", () => {
    strategyEnabled = master.checked;
    $("price-chart").closest(".chart-card").querySelector(".strategy-bar")
      .classList.toggle("disabled", !strategyEnabled);
    saveStrategySettings();
    lastChartSignature = "";
    if (latestPayload) redrawChartAndCalendar(latestPayload, true);
  });
  $("price-chart").closest(".chart-card").querySelector(".strategy-bar")
    .classList.toggle("disabled", !strategyEnabled);
}

function initializeScalpControls() {
  ["risk-balance", "risk-percent", "contract-ounces"].forEach((id) => {
    $(id)?.addEventListener("input", () => updateRiskCalculator(latestScalpResult));
  });
  $("journal-clear")?.addEventListener("click", () => {
    if (!window.confirm("确认清空这台设备上的全部模拟交易记录？")) return;
    paperTrades = [];
    savePaperTrades();
    renderPaperJournal();
  });
  $("journal-export")?.addEventListener("click", exportPaperJournal);
  renderPaperJournal();
}

function startMarketUpdates() {
  if (snapshotTimer || quoteTimer) return;
  refresh();
  refreshBotAlerts("");
  quoteTimer = window.setInterval(refreshQuote, 2000);
  snapshotTimer = window.setInterval(refresh, 15000);
  botAlertsTimer = window.setInterval(() => refreshBotAlerts(), 15000);
}

function initializeBotControls() {
  $("bot-alert-form")?.addEventListener("submit", saveBotLevels);
  $("bot-cancel-levels")?.addEventListener("click", cancelBotLevels);
  $("bot-refresh")?.addEventListener("click", () => refreshBotAlerts());
  $("bot-chat-select")?.addEventListener("change", (event) => {
    botSelectedChatId = event.target.value;
    botStrategyDay = "";
    resetBotStrategyPage();
    setText("bot-feedback", "");
    refreshBotAlerts(botSelectedChatId);
  });
  $("bot-strategy-direction")?.addEventListener("change", (event) => {
    botStrategyDirection = event.target.value;
    resetBotStrategyPage();
    refreshBotStrategyDashboard();
  });
  $("bot-strategy-days")?.addEventListener("change", (event) => {
    botStrategyDays = Number(event.target.value) || 30;
    botStrategyDay = "";
    resetBotStrategyPage();
    refreshBotStrategyDashboard();
  });
  $("bot-strategy-status")?.addEventListener("change", (event) => {
    botStrategyStatus = event.target.value;
    resetBotStrategyPage();
    refreshBotStrategyDashboard();
  });
  $("bot-strategy-daily-body")?.addEventListener("click", (event) => {
    const row = event.target.closest("[data-strategy-day]");
    if (!row) return;
    botStrategyDay = row.dataset.strategyDay || "";
    resetBotStrategyPage();
    refreshBotStrategyDashboard();
  });
  $("bot-strategy-clear-day")?.addEventListener("click", () => {
    botStrategyDay = "";
    resetBotStrategyPage();
    refreshBotStrategyDashboard();
  });
  $("bot-strategy-next")?.addEventListener("click", () => {
    if (!botStrategyNextCursor) return;
    botStrategyPageHistory.push(botStrategyCursor);
    botStrategyCursor = botStrategyNextCursor;
    botStrategyPageNumber += 1;
    refreshBotStrategyDashboard();
  });
  $("bot-strategy-prev")?.addEventListener("click", () => {
    if (!botStrategyPageHistory.length) return;
    botStrategyCursor = botStrategyPageHistory.pop() || "";
    botStrategyPageNumber = Math.max(1, botStrategyPageNumber - 1);
    refreshBotStrategyDashboard();
  });
}

applyMarketUi();

initializeStrategyControls();
initializeScalpControls();
initializeBotControls();
startMarketUpdates();
