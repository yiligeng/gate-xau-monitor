# 网站用户登录与账号管理

## 当前访问边界

`sheshetrip.fun` 使用 PostgreSQL 数据库认证：

- `/login`、登录页面样式和图标可以公开读取。
- 仪表盘、账户设置、行情 API 和静态业务脚本必须持有有效会话。
- 未登录访问网页会跳转到 `/login`。
- 未登录访问 `/api/*` 返回 HTTP 401，不返回行情或策略数据。
- 会话 Cookie 使用 `Secure`、`HttpOnly`、`SameSite=Strict`，不设置
  `Domain`，有效期 7 天。
- 数据库只保存会话令牌的 SHA-256 摘要，不保存原始 Cookie。
- 密码使用带随机 Salt 的 scrypt 哈希，不保存明文，也无法从数据库反解。
- 用户修改账号或密码时必须再次输入当前密码；成功后其他会话全部撤销。

当前没有启用 IP 黑名单、IP 限流或 Fail2ban。

## 数据库结构

迁移文件：`db/migrations/002_auth.sql`

- `app.users`：用户名、密码哈希、启用状态和登录时间。
- `app.sessions`：会话摘要、到期时间、登录 IP 和 User-Agent。

登录 IP 只用于会话审计，不参与限制或封禁。

## 创建用户

账号只能由能够 SSH 登录服务器的管理员创建，网站没有公开注册接口。

进入服务器后：

```bash
sudo bash
set -a
. /etc/xau-monitor/database.env
set +a
runuser -u ubuntu -- env DATABASE_URL="${DATABASE_URL}" \
  /opt/xau-monitor/.venv/bin/python -m xau_monitor.users create USERNAME
unset DATABASE_URL
exit
```

命令会安全提示输入和确认密码，不会把密码写进 Shell 历史。用户名只允许
1–32 位英文字母、数字、点、横线和下划线；密码要求 12–128 个字符。

## 查看、停用和重置

先按上一节加载 `DATABASE_URL`，然后执行：

```bash
# 列出用户，不显示密码或会话令牌
runuser -u ubuntu -- env DATABASE_URL="${DATABASE_URL}" \
  /opt/xau-monitor/.venv/bin/python -m xau_monitor.users list

# 停用账号并撤销其全部会话
runuser -u ubuntu -- env DATABASE_URL="${DATABASE_URL}" \
  /opt/xau-monitor/.venv/bin/python -m xau_monitor.users \
  set-active USERNAME inactive

# 重新启用
runuser -u ubuntu -- env DATABASE_URL="${DATABASE_URL}" \
  /opt/xau-monitor/.venv/bin/python -m xau_monitor.users \
  set-active USERNAME active

# 重置密码并撤销其全部会话
runuser -u ubuntu -- env DATABASE_URL="${DATABASE_URL}" \
  /opt/xau-monitor/.venv/bin/python -m xau_monitor.users \
  reset-password USERNAME
```

用户本人可以登录后打开 `/account`，修改自己的用户名或密码。

## 初始 owner 凭据

初始账号名是 `owner`。随机初始密码保存在部署 Mac 的登录钥匙串中：

```text
服务：sheshetrip.fun-user-login
账户：owner
```

不要把密码复制到项目、Git、聊天或普通文档。首次登录后可以在账户页面
修改用户名和密码；修改成功后钥匙串中的旧密码将不再有效，应同步更新或
删除旧钥匙串记录。

## DDoS 与 IP 防护的后续方案

当前阶段按要求不启用 IP 限制。

Lightsail 防火墙适合定义“哪些来源允许访问端口”，但规则是允许型规则。
当 443 已对所有人开放时，它不适合作为动态单 IP 拒绝名单。应用内封禁或
Fail2ban 可以处理单个来源的撞库，但流量已经到达服务器，无法抵挡大规模
或分布式 DDoS。

需要进一步防护时，推荐按顺序实施：

1. 在站点前增加 CloudFront，获得边缘缓存和 AWS Shield Standard 基础
   网络层保护。
2. 经单独成本确认后增加 AWS WAF：为 `/api/auth/login` 设置较低的
   rate-based rule，为全站设置较高阈值的 HTTP flood 规则。
3. 限制源站只接受来自边缘层且携带秘密 Origin Header 的请求，避免攻击者
   绕过 CloudFront 直连 Lightsail。
4. 监控 401、5xx、请求量、CPU、内存和网络流量，再根据真实数据调整阈值。

Cloudflare 也可以作为替代边缘层，但不要同时叠加两套 CDN。创建
CloudFront/WAF 或修改 DNS 都属于新的外部配置与可能的费用，实施前必须
单独确认。
