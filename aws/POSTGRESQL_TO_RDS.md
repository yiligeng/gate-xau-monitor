# PostgreSQL 本机部署与迁移到 AWS RDS

## 当前状态

生产服务器 `Ubuntu-1` 在本机运行 PostgreSQL 16。它与 Python 应用共用
Lightsail 实例，不是 AWS RDS，也不会产生新的 AWS 固定资源费用。

固定配置：

- 数据库：`xau_monitor`
- 应用账号：`xau_monitor`
- Schema：`app`
- 连接地址：`127.0.0.1:5432`
- 密码认证：SCRAM-SHA-256
- 应用连接配置：`/etc/xau-monitor/database.env`
- 当前迁移：`db/migrations/001_initial.sql` 至
  `db/migrations/005_strategy_dashboard_indexes.sql`
- 幂等初始化脚本：`aws/postgresql/bootstrap-local`
- 自动备份：每天约 03:15 UTC（上海时间约 11:15），保留最近 7 天
- 备份目录：`/var/backups/xau-monitor-postgresql`

`database.env` 只允许服务器 root 读取。禁止显示其内容，禁止将它复制到
项目、Git、聊天、日志或云盘。

## 日常检查

```bash
sudo systemctl status postgresql xau-monitor-db-backup.timer
sudo -u postgres psql -d xau_monitor -c \
  "SELECT version, description, applied_at FROM app.schema_migrations;"
sudo ss -lntp | grep 5432
sudo ls -lh /var/backups/xau-monitor-postgresql
```

端口检查只能看到 PostgreSQL 监听 `127.0.0.1:5432`。Lightsail 公网防火墙
不得开放 5432。

立即创建并校验一份备份：

```bash
sudo systemctl start xau-monitor-db-backup.service
sudo systemctl status xau-monitor-db-backup.service --no-pager
```

## 结构迁移规则

每次修改数据库结构时，在 `db/migrations/` 增加一个只前进、不修改历史的
SQL 文件，例如 `002_add_users.sql`，并向 `app.schema_migrations` 写入对应
版本。已经应用过的迁移文件不得重写。

当前 `app.strategy_snapshots` 是服务端策略历史的预留表。应用尚未开始自动
写入；接入持久化时应限制写入频率，并制定按时间删除或归档的策略。
`app.users` 和 `app.sessions` 已经用于生产登录，迁移时必须包含且需要验证。
`app.price_alerts` 保存每日点位告警，`app.point_strategy_trials` 保存
`LEVEL-5X5-V1` 的待触发、持仓、胜负和审计价格；这两张表也必须完整迁移。

策略看板按北京时间的点位设置日聚合，并使用游标分页：

- `setup_day`：点位创建时间转换到 `Asia/Shanghai` 后固化的日期
- `point_strategy_trials_daily_idx`：每日、方向和状态聚合
- `point_strategy_trials_page_idx`：按递减 ID 的逐笔游标分页

不要用不断增大的 SQL `OFFSET` 翻页；长期数据增长后应继续使用
`id < cursor_id ORDER BY id DESC LIMIT ...`。

## 迁移到 RDS 前的准备

1. 在东京区创建 RDS for PostgreSQL，使用仍在标准支持期内、且不低于本机
   主版本的 PostgreSQL。
2. 数据库名保持为 `xau_monitor`，先用 Single-AZ 和最小可用规格。
3. 使用 General Purpose GP3、20 GiB，并开启存储自动扩容。
4. 开启存储加密、自动备份和删除保护。
5. RDS 设为不可公开访问，不分配公网入口。
6. 在同一区域建立 Lightsail VPC Peering；RDS 应位于可与 Lightsail 对等
   连接的默认 VPC。
7. RDS 安全组只允许来自 Lightsail 私网地址或明确的对等 VPC CIDR 的
   TCP 5432，不允许 `0.0.0.0/0` 或 `::/0`。
8. 将 RDS 管理员密码放入受控的密码存储，不写入命令历史或项目文件。

## 正式迁移流程

先在 Lightsail 创建一致性备份：

```bash
sudo systemctl start xau-monitor-db-backup.service
sudo -u postgres pg_dump \
  --format=custom \
  --no-owner \
  --no-acl \
  --file=/var/backups/xau-monitor-postgresql/rds-migration.dump \
  xau_monitor
```

在 RDS 中创建低权限应用账号 `xau_monitor` 和目标数据库。密码应通过安全
提示输入或密码管理器注入，不要把真实密码写进文档或 Shell 历史。

连接 RDS 时强制 TLS，并恢复备份：

```bash
pg_restore \
  --host=RDS_ENDPOINT \
  --port=5432 \
  --username=RDS_ADMIN_USER \
  --dbname=xau_monitor \
  --no-owner \
  --no-acl \
  --role=xau_monitor \
  /var/backups/xau-monitor-postgresql/rds-migration.dump
```

恢复后执行：

```sql
SELECT version, description, applied_at
FROM app.schema_migrations
ORDER BY version;

SELECT count(*) FROM app.strategy_snapshots;
SELECT count(*) FROM app.users;
SELECT count(*) FROM app.sessions;
SELECT count(*) FROM app.price_alerts;
SELECT status, count(*) FROM app.point_strategy_trials GROUP BY status;
```

确认数据后，把 `/etc/xau-monitor/database.env` 中的连接地址切换为 RDS
私网 Endpoint，并使用：

```text
sslmode=require
```

然后重启和验证应用：

```bash
sudo systemctl restart xau-monitor
sudo systemctl status xau-monitor --no-pager
curl --fail --silent https://sheshetrip.fun/api/snapshot?market=btc >/dev/null
```

切换后至少保留本机数据库和最终备份 7 天。确认 RDS 持续稳定、备份可恢复
后，再单独批准停止或卸载本机 PostgreSQL；迁移过程不自动删除源数据。

## 回滚

如果 RDS 连接或恢复异常：

1. 将 `database.env` 恢复为 `127.0.0.1:5432` 的原连接。
2. 重启 `xau-monitor`。
3. 验证 XAU 和 BTC API。
4. 保留失败的 RDS 实例用于排查，未得到明确批准前不要删除。

## 成本边界

本机 PostgreSQL 使用现有 Lightsail 的 CPU、2 GiB 内存和 60 GB SSD，
不会新增固定实例费。RDS 会产生独立的实例、存储、备份、网络和税费；
创建 RDS 属于新增付费资源，必须先获得明确批准。
