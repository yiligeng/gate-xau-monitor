from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from importlib.resources import files
from typing import Any
from zoneinfo import ZoneInfo, reset_tzpath

import tzdata


TIMEZONE_DATA_VERSION = tzdata.__version__
reset_tzpath((str(files("tzdata").joinpath("zoneinfo")),))
SHANGHAI = ZoneInfo.no_cache("Asia/Shanghai")
NEW_YORK = ZoneInfo.no_cache("America/New_York")
LONDON = ZoneInfo.no_cache("Europe/London")
TOKYO = ZoneInfo.no_cache("Asia/Tokyo")

FED_CALENDAR_URL = "https://www.federalreserve.gov/newsevents/calendar.htm"
BLS_SCHEDULE_URL = "https://www.bls.gov/schedule/2026/home.htm"
BEA_SCHEDULE_URL = "https://www.bea.gov/news/schedule"
ICE_LBMA_URL = "https://www.ice.com/iba/lbma-precious-metals"
CME_GOLD_URL = "https://www.cmegroup.com/markets/metals/precious/gold.html"
EIA_PETROLEUM_URL = "https://www.eia.gov/petroleum/supply/weekly/schedule.php"
TREASURY_AUCTIONS_URL = "https://www.treasurydirect.gov/auctions/upcoming/"
API_WSB_URL = "https://www.api.org/products-and-services/statistics/api-weekly-statistical-bulletin"
BOJ_CALENDAR_URL = "https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm"
CFETS_PARITY_URL = "https://www.chinamoney.com.cn/english/bmkcpr/"
NBS_RELEASE_URL = "https://www.stats.gov.cn/english/PressRelease/ReleaseCalendar/202512/t20251226_1962154.html"
SSE_TRADING_URL = "https://english.sse.com.cn/start/trading/schedule/"
ISM_CALENDAR_URL = (
    "https://www.ismworld.org/supply-management-news-and-reports/reports/"
    "rob-report-calendar/"
)
SOURCE_URLS = {
    "Federal Reserve": FED_CALENDAR_URL,
    "BLS": BLS_SCHEDULE_URL,
    "BEA": BEA_SCHEDULE_URL,
    "ISM": ISM_CALENDAR_URL,
    "BOJ": BOJ_CALENDAR_URL,
    "CFETS": CFETS_PARITY_URL,
    "NBS": NBS_RELEASE_URL,
    "SSE": SSE_TRADING_URL,
}


@dataclass(frozen=True)
class EventSpec:
    date: date
    hour: int
    minute: int
    title: str
    impact: str
    source: str
    category: str
    note: str = ""
    source_url: str = ""
    timezone: ZoneInfo = NEW_YORK


FOMC_DECISION_DATES = [
    date(2026, 7, 29),
    date(2026, 9, 16),
    date(2026, 10, 28),
    date(2026, 12, 9),
]

BOJ_DECISION_DATES = [
    date(2026, 7, 31),
    date(2026, 9, 18),
    date(2026, 10, 30),
    date(2026, 12, 18),
]

US_MACRO_EVENTS = [
    EventSpec(date(2026, 7, 30), 8, 30, "GDP 初值 + PCE", "最高", "BEA", "growth_inflation", "同一时间公布，黄金容易扫单"),
    EventSpec(date(2026, 7, 31), 8, 30, "就业成本指数 ECI", "高", "BLS", "labor_inflation", "工资通胀会影响利率预期"),
    EventSpec(date(2026, 8, 7), 8, 30, "非农就业 NFP", "最高", "BLS", "labor", "月内固定大波动事件"),
    EventSpec(date(2026, 8, 12), 8, 30, "CPI", "最高", "BLS", "inflation", "直接影响美元和美债收益率"),
    EventSpec(date(2026, 8, 13), 8, 30, "PPI", "高", "BLS", "inflation", "通胀链条确认"),
    EventSpec(date(2026, 8, 26), 8, 30, "PCE + GDP 修正", "最高", "BEA", "inflation_growth", "美联储偏好的通胀口径"),
    EventSpec(date(2026, 9, 4), 8, 30, "非农就业 NFP", "最高", "BLS", "labor", "月内固定大波动事件"),
    EventSpec(date(2026, 9, 10), 8, 30, "PPI", "高", "BLS", "inflation", "通胀链条确认"),
    EventSpec(date(2026, 9, 11), 8, 30, "CPI", "最高", "BLS", "inflation", "直接影响美元和美债收益率"),
    EventSpec(date(2026, 9, 30), 8, 30, "PCE", "最高", "BEA", "inflation", "美联储偏好的通胀口径"),
    EventSpec(date(2026, 10, 2), 8, 30, "非农就业 NFP", "最高", "BLS", "labor", "月内固定大波动事件"),
    EventSpec(date(2026, 10, 14), 8, 30, "CPI", "最高", "BLS", "inflation", "直接影响美元和美债收益率"),
    EventSpec(date(2026, 10, 15), 8, 30, "PPI", "高", "BLS", "inflation", "通胀链条确认"),
    EventSpec(date(2026, 10, 29), 8, 30, "GDP 初值 + PCE", "最高", "BEA", "growth_inflation", "同一时间公布，黄金容易扫单"),
    EventSpec(date(2026, 10, 30), 8, 30, "就业成本指数 ECI", "高", "BLS", "labor_inflation", "工资通胀会影响利率预期"),
    EventSpec(date(2026, 11, 6), 8, 30, "非农就业 NFP", "最高", "BLS", "labor", "月内固定大波动事件"),
    EventSpec(date(2026, 11, 10), 8, 30, "CPI", "最高", "BLS", "inflation", "直接影响美元和美债收益率"),
    EventSpec(date(2026, 11, 13), 8, 30, "PPI", "高", "BLS", "inflation", "通胀链条确认"),
    EventSpec(date(2026, 11, 25), 8, 30, "PCE + GDP 修正", "最高", "BEA", "inflation_growth", "美联储偏好的通胀口径"),
    EventSpec(date(2026, 12, 4), 8, 30, "非农就业 NFP", "最高", "BLS", "labor", "月内固定大波动事件"),
    EventSpec(date(2026, 12, 10), 8, 30, "CPI", "最高", "BLS", "inflation", "直接影响美元和美债收益率"),
    EventSpec(date(2026, 12, 15), 8, 30, "PPI", "高", "BLS", "inflation", "通胀链条确认"),
    EventSpec(date(2026, 12, 23), 8, 30, "PCE + GDP 三次估计", "最高", "BEA", "inflation_growth", "美联储偏好的通胀口径"),
]


def market_calendar_payload(now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now(SHANGHAI)).astimezone(SHANGHAI)
    events = today_event_list(now)
    windows = daily_risk_windows(now)
    return {
        "timezone": "Asia/Shanghai",
        "timezone_data_version": TIMEZONE_DATA_VERSION,
        "date": now.date().isoformat(),
        "generated_at": now.isoformat(),
        "windows": windows,
        "volatility_windows": daily_volatility_windows(now),
        "events": events,
        "event_windows": event_risk_windows(now, events),
        "summary": summary_for_events(events),
    }


def daily_risk_windows(now: datetime) -> list[dict[str, Any]]:
    local_day = now.astimezone(SHANGHAI).date()
    windows = [
        _window_from_shanghai(
            now,
            local_day,
            "亚洲午饭震荡窗",
            time(10, 25),
            time(13, 5),
            "震荡",
            "无日银/中国数据覆盖时，东京和中港午休更适合等假突破收回",
            source_url=SSE_TRADING_URL,
        ),
        _window_from_london(
            now,
            local_day,
            "英国午饭震荡窗",
            time(12, 0),
            time(13, 30),
            "震荡",
            "午间流动性回落，适合观察刺破后收回",
        ),
        _window_from_new_york(
            now,
            local_day,
            "美国午饭震荡窗",
            time(12, 0),
            time(13, 30),
            "震荡",
            "美国午间深度变薄，突破更容易变成假突破",
        ),
        _window_from_new_york(
            now,
            local_day,
            "COMEX 日切低流动性",
            time(16, 50),
            time(18, 10),
            "低流动性",
            "CME 黄金期货日内休市前后，点差和滑点容易放大",
            source_url=CME_GOLD_URL,
        ),
    ]
    return sorted(windows, key=lambda item: item["start"])


def daily_volatility_windows(now: datetime) -> list[dict[str, Any]]:
    local_day = now.astimezone(SHANGHAI).date()
    windows = [
        _window_from_tokyo(
            now,
            local_day,
            "东京盘启动",
            time(8, 55),
            time(9, 30),
            "中高",
            "日元和亚洲避险资金开始活跃",
        ),
        _window_from_shanghai(
            now,
            local_day,
            "人民币中间价",
            time(9, 10),
            time(9, 25),
            "中高",
            "USD/CNY fixing 会影响美元指数和亚洲风险偏好",
            source_url=CFETS_PARITY_URL,
        ),
        _window_from_shanghai(
            now,
            local_day,
            "中国开盘/宏观窗",
            time(9, 25),
            time(10, 5),
            "中高",
            "A股、港股和中国 09:30 数据容易带动亚洲黄金",
            source_url=NBS_RELEASE_URL,
        ),
        _window_from_shanghai(
            now,
            local_day,
            "亚洲尾盘",
            time(14, 55),
            time(15, 15),
            "中",
            "A股收盘和东京尾盘，亚洲资金常在这里调仓",
            source_url=SSE_TRADING_URL,
        ),
        _window_from_london(
            now,
            local_day,
            "伦敦盘启动",
            time(8, 0),
            time(10, 0),
            "中高",
            "欧洲流动性开始进场",
        ),
        _window_from_london(
            now,
            local_day,
            "LBMA 上午定盘",
            time(10, 25),
            time(10, 40),
            "中高",
            "伦敦黄金基准价附近",
            source_url=ICE_LBMA_URL,
        ),
        _window_from_new_york(
            now,
            local_day,
            "美国数据窗",
            time(8, 25),
            time(8, 45),
            "最高",
            "多数美国重磅数据在 08:30 ET 公布",
            source_url=BLS_SCHEDULE_URL,
        ),
        _window_from_new_york(
            now,
            local_day,
            "美国二次数据窗",
            time(9, 55),
            time(10, 10),
            "高",
            "ISM、JOLTS、成屋销售等常在 10:00 ET 公布",
            source_url=ISM_CALENDAR_URL,
        ),
        _window_from_new_york(
            now,
            local_day,
            "纽约主波动",
            time(9, 30),
            time(11, 30),
            "最高",
            "美股开盘后，美元/美债/COMEX 同时活跃",
        ),
        _window_from_london(
            now,
            local_day,
            "LBMA 下午定盘",
            time(14, 55),
            time(15, 10),
            "高",
            "伦敦下午定盘，常与纽约早盘重叠",
            source_url=ICE_LBMA_URL,
        ),
        _window_from_new_york(
            now,
            local_day,
            "美债拍卖结果窗",
            time(12, 55),
            time(13, 10),
            "高",
            "美债需求会带动收益率、美元和黄金二次定价",
            source_url=TREASURY_AUCTIONS_URL,
        ),
    ]
    windows.extend(_weekly_energy_windows(now, local_day))
    return sorted(windows, key=lambda item: item["start"])


def event_risk_windows(
    now: datetime,
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    if any(event["category"] == "fomc" for event in events):
        statement = next(event for event in events if event["category"] == "fomc")
        start = datetime.fromisoformat(statement["time"]) - timedelta(minutes=10)
        end = datetime.fromisoformat(statement["time"]) + timedelta(minutes=90)
        windows.append(
            _window(
                "FOMC 夜盘",
                start,
                end,
                "最高+",
                "声明和发布会会重新定价利率预期",
                now,
                source_url=FED_CALENDAR_URL,
            )
        )
    if any(event["category"] == "boj" for event in events):
        decision = next(event for event in events if event["category"] == "boj")
        start = datetime.fromisoformat(decision["time"]) - timedelta(minutes=15)
        end = datetime.fromisoformat(decision["time"]) + timedelta(hours=4)
        windows.append(
            _window(
                "BOJ 议息日",
                start,
                end,
                "最高",
                "日元利率预期变化会牵动美元和黄金避险交易",
                now,
                source_url=BOJ_CALENDAR_URL,
            )
        )
    return sorted(windows, key=lambda item: item["start"])


def _weekly_energy_windows(now: datetime, local_day: date) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    ny_day = _new_york_day_for_local_session(local_day)
    if ny_day.weekday() == 1:
        windows.append(
            _window_from_new_york(
                now,
                local_day,
                "API 原油库存",
                time(16, 25),
                time(16, 40),
                "中高",
                "油价异动会传导到通胀预期和黄金",
                source_url=API_WSB_URL,
            )
        )
    if ny_day.weekday() == 2:
        windows.append(
            _window_from_new_york(
                now,
                local_day,
                "EIA 原油库存",
                time(10, 25),
                time(10, 45),
                "高",
                "原油库存超预期时，通胀交易容易同步波动",
                source_url=EIA_PETROLEUM_URL,
            )
        )
    return windows


def today_event_list(now: datetime) -> list[dict[str, Any]]:
    local_day = now.astimezone(SHANGHAI).date()
    horizon_start = datetime.combine(local_day, time.min, tzinfo=SHANGHAI)
    horizon_end = datetime.combine(local_day + timedelta(days=1), time(4, 0), tzinfo=SHANGHAI)
    specs = list(US_MACRO_EVENTS)
    specs.extend(_fomc_specs())
    specs.extend(_boj_specs())
    specs.extend(_ism_specs(local_day))
    events = [_event_payload(spec, now) for spec in specs]
    return sorted(
        [
            event
            for event in events
            if horizon_start <= datetime.fromisoformat(event["time"]) <= horizon_end
        ],
        key=lambda item: item["time"],
    )


def summary_for_events(events: list[dict[str, Any]]) -> str:
    top = [event for event in events if event["impact"] in {"最高", "最高+"}]
    if top:
        return "今日有最高影响事件，数据前后避免追价。"
    if events:
        return "今日有中高影响事件，纽约盘前后注意波动。"
    return "今日暂无最高级美国事件，仍按固定风险时段观察。"


def _fomc_specs() -> list[EventSpec]:
    specs: list[EventSpec] = []
    for decision_date in FOMC_DECISION_DATES:
        specs.append(
            EventSpec(
                decision_date,
                14,
                0,
                "FOMC 利率声明",
                "最高+",
                "Federal Reserve",
                "fomc",
                "黄金最高风险事件之一",
            )
        )
        specs.append(
            EventSpec(
                decision_date,
                14,
                30,
                "FOMC 发布会",
                "最高+",
                "Federal Reserve",
                "fomc",
                "发布会问答容易二次波动",
            )
        )
    return specs


def _boj_specs() -> list[EventSpec]:
    specs: list[EventSpec] = []
    for decision_date in BOJ_DECISION_DATES:
        specs.append(
            EventSpec(
                decision_date,
                11,
                45,
                "BOJ 利率决议观察窗",
                "最高",
                "BOJ",
                "boj",
                "日银决议发布时间不固定，通常在东京午前后",
                timezone=TOKYO,
            )
        )
        specs.append(
            EventSpec(
                decision_date,
                15,
                30,
                "BOJ 发布会",
                "高",
                "BOJ",
                "boj_press",
                "发布会会解释政策取向，日元可能二次波动",
                timezone=TOKYO,
            )
        )
    return specs


def _ism_specs(local_day: date) -> list[EventSpec]:
    # Generate one month around the local day because U.S. 10:00 ET maps to
    # Beijing late evening and can straddle month boundaries in other zones.
    months = {(local_day.year, local_day.month)}
    previous = local_day.replace(day=1) - timedelta(days=1)
    following = (local_day.replace(day=28) + timedelta(days=4)).replace(day=1)
    months.add((previous.year, previous.month))
    months.add((following.year, following.month))
    specs: list[EventSpec] = []
    for year, month in months:
        first = _nth_business_day(year, month, 1)
        third = _nth_business_day(year, month, 3)
        specs.append(
            EventSpec(
                first,
                10,
                0,
                "ISM 制造业 PMI",
                "中高",
                "ISM",
                "pmi",
                "第一营业日 10:00 ET",
            )
        )
        specs.append(
            EventSpec(
                third,
                10,
                0,
                "ISM 服务业 PMI",
                "高",
                "ISM",
                "pmi",
                "第三营业日 10:00 ET",
            )
        )
    return specs


def _nth_business_day(year: int, month: int, n: int) -> date:
    current = date(year, month, 1)
    seen = 0
    while True:
        if current.weekday() < 5 and current not in _us_market_holidays(year):
            seen += 1
            if seen == n:
                return current
        current += timedelta(days=1)


def _us_market_holidays(year: int) -> set[date]:
    # Small subset needed for first/third-business-day ISM scheduling.
    return {
        date(year, 1, 1),
        date(year, 7, 4),
        date(year, 12, 25),
        _first_monday(year, 9),
    }


def _first_monday(year: int, month: int) -> date:
    current = date(year, month, 1)
    while current.weekday() != 0:
        current += timedelta(days=1)
    return current


def _event_payload(spec: EventSpec, now: datetime) -> dict[str, Any]:
    event_time = datetime.combine(
        spec.date,
        time(spec.hour, spec.minute),
        spec.timezone,
    ).astimezone(SHANGHAI)
    return {
        "time": event_time.isoformat(),
        "time_label": event_time.strftime("%m/%d %H:%M"),
        "title": spec.title,
        "impact": spec.impact,
        "source": spec.source,
        "source_url": spec.source_url or SOURCE_URLS.get(spec.source, ""),
        "category": spec.category,
        "note": spec.note,
        "status": _status_for(event_time, now),
    }


def _window_from_new_york(
    now: datetime,
    local_day: date,
    title: str,
    start_time: time,
    end_time: time,
    impact: str,
    note: str,
    source_url: str = "",
) -> dict[str, Any]:
    ny_day = _new_york_day_for_local_session(local_day)
    start = datetime.combine(ny_day, start_time, NEW_YORK).astimezone(SHANGHAI)
    end = datetime.combine(ny_day, end_time, NEW_YORK).astimezone(SHANGHAI)
    return _window(title, start, end, impact, note, now, source_url=source_url)


def _new_york_day_for_local_session(local_day: date) -> date:
    # A Beijing session day covers New York morning through its evening,
    # including windows that appear after midnight in Beijing.
    return local_day


def _window_from_london(
    now: datetime,
    local_day: date,
    title: str,
    start_time: time,
    end_time: time,
    impact: str,
    note: str,
    source_url: str = "",
) -> dict[str, Any]:
    start = datetime.combine(local_day, start_time, LONDON).astimezone(SHANGHAI)
    end = datetime.combine(local_day, end_time, LONDON).astimezone(SHANGHAI)
    return _window(title, start, end, impact, note, now, source_url=source_url)


def _window_from_tokyo(
    now: datetime,
    local_day: date,
    title: str,
    start_time: time,
    end_time: time,
    impact: str,
    note: str,
    source_url: str = "",
) -> dict[str, Any]:
    tokyo_day = datetime.combine(
        local_day,
        time(12, 0),
        SHANGHAI,
    ).astimezone(TOKYO).date()
    start = datetime.combine(tokyo_day, start_time, TOKYO).astimezone(SHANGHAI)
    end = datetime.combine(tokyo_day, end_time, TOKYO).astimezone(SHANGHAI)
    return _window(title, start, end, impact, note, now, source_url=source_url)


def _window_from_shanghai(
    now: datetime,
    local_day: date,
    title: str,
    start_time: time,
    end_time: time,
    impact: str,
    note: str,
    source_url: str = "",
) -> dict[str, Any]:
    start = datetime.combine(local_day, start_time, SHANGHAI)
    end = datetime.combine(local_day, end_time, SHANGHAI)
    return _window(title, start, end, impact, note, now, source_url=source_url)


def _window(
    title: str,
    start: datetime,
    end: datetime,
    impact: str,
    note: str,
    now: datetime,
    source_url: str = "",
) -> dict[str, Any]:
    return {
        "title": title,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "time_label": f"{start:%H:%M}-{end:%H:%M}",
        "impact": impact,
        "note": note,
        "source_url": source_url,
        "status": _window_status(start, end, now.astimezone(SHANGHAI)),
    }


def _window_status(start: datetime, end: datetime, now: datetime) -> str:
    if start <= now <= end:
        return "active"
    if now < start:
        return "upcoming"
    return "past"


def _status_for(event_time: datetime, now: datetime) -> str:
    if event_time < now - timedelta(minutes=15):
        return "past"
    if event_time <= now + timedelta(minutes=15):
        return "near"
    return "upcoming"
