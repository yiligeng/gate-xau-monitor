# XAU Monitor — AWS 部署资料

本目录记录 Gate XAUUSD 黄金监控项目的 AWS 接入方式。

给后续 AI 的最短交接入口：[`AI_HANDOFF.md`](AI_HANDOFF.md)。

## 当前配置

- AWS 区域：`ap-northeast-1`（Asia Pacific / Tokyo）
- AWS 账户：`960170157901`
- 本机基础 Profile：`xau-cli-base`
- 本机部署 Profile：`xau-lightsail`
- IAM 程序化用户：`xau-deploy-cli`
- IAM 部署角色：`XauMonitorDeployRole`
- 角色会话时长：1 小时

部署时统一使用：

```bash
aws <command> --profile xau-lightsail --region ap-northeast-1
```

验证当前部署身份：

```bash
aws sts get-caller-identity --profile xau-lightsail
```

预期 ARN 包含：

```text
assumed-role/XauMonitorDeployRole/
```

## 权限结构

```text
本机 AWS CLI
  └─ xau-cli-base
      └─ IAM 用户 xau-deploy-cli
          └─ 只允许 AssumeRole
              └─ XauMonitorDeployRole
                  ├─ 管理 Lightsail
                  ├─ 读取基础 CloudWatch 指标
                  └─ 创建 Lightsail 服务关联角色
```

`xau-deploy-cli` 没有 AWS 控制台密码，也没有直接管理云资源的权限。
实际部署命令通过 `xau-lightsail` Profile 获取短期角色凭证。

## 本机凭证

敏感凭证由 AWS CLI 保存在：

```text
~/.aws/credentials
~/.aws/config
```

这两个文件不属于项目，禁止复制到本目录、Git、聊天或云盘。

查看已经配置的 Profile：

```bash
aws configure list-profiles
```

## 当前资源状态

已于 2026-07-27 创建东京 Lightsail 实例：

- 实例名称：`Ubuntu-1`
- 状态：`running`
- 可用区：`ap-northeast-1a`（Tokyo, Zone A）
- 系统：Ubuntu 24.04 LTS（`ubuntu_24_04`）
- 套餐：`small_3_0`，USD 12/月
- 配置：2 GB RAM、2 vCPU、60 GB SSD、3 TB 月流量
- 网络：Dual-stack（IPv4 + IPv6）
- 静态公网 IPv4：`13.196.4.191`
- 公网 IPv6：`2406:da14:15da:6e00:c54d:bcab:e93f:934c`
- 私网 IPv4：`172.26.6.108`
- SSH 用户名：`ubuntu`
- SSH 密钥：东京区域的 Lightsail 默认密钥，本机安全路径
  `/Users/a11/.ssh/aws-lightsail-tokyo-default.pem`（权限 `600`）
- 自动快照：未启用
- 静态 IP 资源：`ubuntu-1-tokyo-static-ip`，已绑定
- 部署目录：`/opt/xau-monitor`
- systemd 服务：`xau-monitor.service`，已启用并运行
- 应用监听：`127.0.0.1:8765`，不直接暴露公网
- 监控正式域名：`https://sheshetrip.fun`
- 监控备用域名：`https://www.sheshetrip.fun`
- 空白保留域名：`https://chopsticktrip.com`、`https://www.chopsticktrip.com`
- HTTPS：Caddy 自动申请和续期 Let's Encrypt 证书
- 访问方式：数据库账号登录；未登录不能读取仪表盘或行情 API
- 数据库：同机 PostgreSQL 16，`127.0.0.1:5432`，不对公网开放
- 数据库迁移文档：[`POSTGRESQL_TO_RDS.md`](POSTGRESQL_TO_RDS.md)
- 用户认证文档：[`USER_AUTH.md`](USER_AUTH.md)

查询实例：

```bash
aws lightsail get-instance \
  --instance-name Ubuntu-1 \
  --profile xau-lightsail \
  --region ap-northeast-1
```

AWS CLI 用于管理实例、网络、快照等云资源；登录服务器和执行 Linux
命令使用 SSH。下载东京区域的默认私钥后，可使用：

```bash
ssh -i /Users/a11/.ssh/aws-lightsail-tokyo-default.pem ubuntu@13.196.4.191
```

私钥不得复制到项目、Git、聊天或云盘。

在这台 Mac 上双击项目根目录的 `连接云端监控.command`，会通过 SSH
加密隧道打开：

```text
http://127.0.0.1:18765
```

该地址只在本机隧道存续期间可用，不会把监控页面直接暴露到公网。

正式公网入口使用 HTTPS，打开后需要数据库账号登录：

```text
https://sheshetrip.fun
```

本机加密隧道仍作为备用入口。

## DNS 与 HTTPS

阿里云 DNS 已为 `sheshetrip.fun` 配置：

```text
@    A    13.196.4.191
www  A    13.196.4.191
```

`chopsticktrip.com` 的 DNS 也仍指向同一静态 IP，但 Caddy 对其根域名和
`www` 仅返回空白的 HTTP 200 页面。

Lightsail 公网防火墙开放：

- TCP 22：仅本机 SSH 出口 `/32` 与 `lightsail-connect`
- TCP 80：公网，用于 HTTP 跳转和 ACME
- TCP 443：公网，用于 HTTPS

内部端口 `8765` 未开放。

Caddy 配置位于服务器：

```text
/etc/caddy/Caddyfile
```

检查服务：

```bash
ssh -i /Users/a11/.ssh/aws-lightsail-tokyo-default.pem ubuntu@13.196.4.191 \
  'systemctl status caddy xau-monitor --no-pager'
```

## 安全操作

- 不使用 Root 账号进行日常部署。
- 不在脚本中硬编码 Access Key 或 Secret Key。
- 不把 SSH 私钥放入项目或提交到 Git。
- 不把端口 `8765` 直接暴露到公网。
- 公网只开放 SSH、HTTP 和 HTTPS；稳定后限制 SSH 来源。
- 不开放 PostgreSQL 端口 `5432`；数据库仅供服务器本机访问。
- 部署结束后可轮换或删除 `xau-deploy-cli` 的访问密钥。
- Root 账号保持 MFA 开启。

## 文件说明

- `iam/assume-role-policy.json`：部署用户切换角色的权限。
- `iam/role-trust-policy.json`：角色信任关系。
- `iam/lightsail-deploy-policy.json`：Lightsail 部署角色权限。
- `aws-config.example`：不包含密钥的 AWS CLI 配置参考。
- `POSTGRESQL_TO_RDS.md`：本机 PostgreSQL 运维及未来迁移 RDS 流程。
- `postgresql/xau-monitor-db-backup`：每日 PostgreSQL 逻辑备份脚本。
- `postgresql/bootstrap-local`：创建本机数据库、低权限账号及安全连接配置。
