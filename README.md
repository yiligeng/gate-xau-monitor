# Gate XAUUSD CFD / BTCUSDT 永续行情监控

AI 或新维护者请先阅读
[`AI_PROJECT_KNOWLEDGE.md`](AI_PROJECT_KNOWLEDGE.md)，再按任务进入 AWS、
认证或数据库子文档。

一个只读的 Python 后端行情监控工具，直接读取 Gate 公共行情接口，不需要
API Key，也不会下单。网页版同时支持 XAUUSD 黄金 CFD 与 BTC_USDT 永续。

功能：

- 自动打开本地网页仪表盘和实时1分钟K线图
- Gate CFD 报价约每250毫秒读取一次，并通过本地事件流推送到网页
- 内存记录最近240个Tick，可切换Tick、1分钟和5分钟图
- 显示真实到达频率、接口耗时以及价格实际变化频率
- 高频Tick会实时更新正在形成的1分钟和5分钟K线柱体
- Tick、1分钟和5分钟图均在最新位置显示实时价格线与价格标签
- 可开关组合策略：EMA200、布林通道、ATR通道、PSAR、经典日枢轴点
- 按启用指标实时投票，显示组合“偏多 / 偏空 / 观望”和每项方向
- 实时买价、卖价、点差和当日涨跌
- 1分钟、5分钟、15分钟 EMA、RSI、ATR
- 根据多周期结构显示“偏多 / 偏空 / 震荡”
- 显示短线支撑、阻力和条件触发提示
- 自定义价格突破提醒
- 可选保存 tick 数据到 CSV
- BTC_USDT 永续真实报价、1/5/15分钟与日线K线
- BTC 永续真实成交量、分钟 RVOL 和最近60秒主动买卖差
- 后端统一计算多周期趋势、关键位聚类、扫损回收、执行条件与超短策略评分

网页只负责展示后端结果和保存本机模拟交易日志。Gate 行情读取、技术指标
和 `SCALP-1.0-PY` 策略决策均在 Python 后端完成。

旧版独立纯前端 Sites 部署已经退役并取消公开访问；当前生产入口只有
`https://sheshetrip.fun`，由 Caddy 转发到 Python 服务。

生产服务器同时运行仅限本机访问的 PostgreSQL 16。数据库密码不在代码库
中，当前初始结构和未来迁移 AWS RDS 的操作说明见
[`aws/POSTGRESQL_TO_RDS.md`](aws/POSTGRESQL_TO_RDS.md)。

正式网站使用数据库用户登录，未登录不能读取仪表盘或行情 API。账号创建、
停用、重置和用户自助修改说明见
[`aws/USER_AUTH.md`](aws/USER_AUTH.md)。

## 快速运行

需要 Python 3.10 或更高版本。

## 部署流水线

GitHub 私有仓库已配置为适合生产审批式部署：

- PR 和 `main` push 会自动跑 CI。
- 生产部署只在 GitHub Actions 页面手动运行 `Deploy Production`。
- 手动运行后由 Lightsail 上的 self-hosted runner 执行固定部署脚本。
- GitHub 不保存服务器 SSH 私钥、数据库连接串或企微 Secret。
- 当前 GitHub plan 不支持 private repo 的环境审批和分支保护，所以不要把
  deploy workflow 改成 `main` 自动触发。

服务器实际部署脚本模板在 `ops/deploy-xau-monitor`。

### 生产网站（推荐）

直接访问：

```text
https://sheshetrip.fun
```

网站要求登录，账号由管理员创建。

### 本地网页版（开发）

登录系统依赖 PostgreSQL 和 `DATABASE_URL`。先按
[`aws/POSTGRESQL_TO_RDS.md`](aws/POSTGRESQL_TO_RDS.md) 准备本地数据库，
再通过安全的临时环境变量启动：

```bash
cd "/Users/a11/Documents/投资/gate-xau-monitor"
PYTHONPATH=src python3 -m xau_monitor --web
```

不要把数据库连接串写进代码、README、Shell 历史或 Git。
`启动监控.command` 尚未接入数据库环境变量，当前不能作为可靠的本地入口。

网页报价约每250毫秒更新一次，K线和技术指标每5秒重新计算。关闭启动监控的终端窗口，或在其中按 `Control + C`，即可停止服务。

页面顶部可以在 `XAUUSD CFD` 与 `BTCUSDT 永续` 之间切换。

### 企业微信智能机器人

项目支持企业微信“智能机器人 / API 模式 / 使用长连接”。这不是群机器人
Webhook；它使用企业微信后台生成的 Bot ID 和 Secret 接收消息并回复。

先安装可选依赖：

```bash
pip install -e ".[wecom]"
```

不要把 Secret 写进代码或文档。使用临时环境变量启动：

```bash
export WECOM_BOT_ID="你的Bot ID"
export WECOM_BOT_SECRET="重新生成后的Secret"
PYTHONPATH=src python3 -m xau_monitor --wecom-bot
```

如果要和网页服务一起运行：

```bash
PYTHONPATH=src python3 -m xau_monitor --web --wecom-bot --no-browser
```

生产服务器也可以单独启用机器人 systemd 服务。把下面的环境变量放到
root-only 文件 `/etc/xau-monitor/wecom-bot.env`：

```text
WECOM_BOT_ID=你的Bot ID
WECOM_BOT_SECRET=重新生成后的Secret
```

然后部署并启用 `aws/systemd/xau-monitor-wecom-bot.service`。这个服务单独
运行机器人，不影响现有网页登录监控服务。

机器人当前支持发送“黄金 / XAU”查看 XAUUSD 摘要，发送“BTC”查看
BTCUSDT 永续摘要，发送“帮助”查看菜单。机器人也支持当天点位提醒：

```text
@机器人 黄金 今日点位 A B C D
@机器人 黄金 点位
@机器人 黄金 取消今日点位
```

`今日点位` 会覆盖同一会话里该品种尚未过期的旧点位。每条点位有效到北京
时间当天 24 点；最新价距离点位小于等于 3 美元时最多提醒 2 次；如果价格
从创建时所在的一侧触达或穿过点位，这条点位当天自动作废。机器人只读行情和
策略摘要，不会下单。网页登录后的主仪表盘也有“机器人点位告警”面板，位置在
实时量能卡片下方，可以查看、覆盖保存或取消同一企业微信会话的今日点位。

### 命令行版

```bash
cd "/Users/a11/Documents/投资/gate-xau-monitor"
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
xau-monitor
```

不安装也可以直接运行：

```bash
PYTHONPATH=src python3 -m xau_monitor
```

只拉取一次并退出：

```bash
PYTHONPATH=src python3 -m xau_monitor --once
```

每3秒刷新，并保存行情：

```bash
PYTHONPATH=src python3 -m xau_monitor --interval 3 --csv data/xauusd_ticks.csv
```

设置价格提醒：

```bash
PYTHONPATH=src python3 -m xau_monitor --above 4062 --below 4040
```

查看全部参数：

```bash
PYTHONPATH=src python3 -m xau_monitor --help
```

## 指标说明

- EMA200：价格相对长期指数均线的位置，用于判断大方向。
- 布林通道：20周期均线加减2倍标准差，观察价格相对波动带的位置。
- ATR通道：EMA20 加减2倍 ATR14，观察趋势与波动边界。
- PSAR：抛物线转向点；点在价格下方偏多，在上方偏空。
- 日枢轴：使用上一根已完成日线计算 P、R1/R2、S1/S2。
- EMA5/10：观察极短线速度。
- EMA20/50：观察当前周期的主要方向。
- RSI14：观察动能；强趋势中超买、超卖不代表立即反转。
- ATR14：衡量波动，用于理解合理止损距离，不判断方向。
- 支撑/阻力：取最近一段已完成1分钟K线的局部低点和高点。

“偏多/偏空”是规则化的行情描述，不是收益保证或自动交易指令。CFD 和高杠杆交易风险很高。

## 数据接口

项目使用 Gate API v4 的 TradFi 公共端点：

- `GET /api/v4/tradfi/symbols/XAUUSD/tickers`
- `GET /api/v4/tradfi/symbols/XAUUSD/klines`

BTC 使用 Gate API v4 的 USDT 永续公共端点：

- `GET /api/v4/futures/usdt/tickers`
- `GET /api/v4/futures/usdt/candlesticks`
- `GET /api/v4/futures/usdt/trades`

账户、持仓和交易接口没有接入。
