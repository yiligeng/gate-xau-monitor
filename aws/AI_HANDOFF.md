# AWS AI Handoff

Last verified: 2026-07-28.

## Goal

Deploy `/Users/a11/Documents/投资/gate-xau-monitor` to an inexpensive AWS
Lightsail instance in Tokyo. The app is a Python XAUUSD monitor whose local web
entrypoint is:

```bash
PYTHONPATH=src python3 -m xau_monitor --web --no-browser
```

It listens on `127.0.0.1:8765` locally.

## Completed

- AWS CLI `2.36.7` installed at `/opt/homebrew/bin/aws`.
- AWS account ID: `960170157901`.
- Default deployment region: `ap-northeast-1` (Tokyo).
- Root account MFA is enabled.
- Root CLI bootstrap session was explicitly logged out.
- IAM programmatic user created: `xau-deploy-cli`.
- IAM role created: `XauMonitorDeployRole`.
- User can only call `sts:AssumeRole` on that role.
- Role trust is restricted to `xau-deploy-cli`.
- Role has an inline policy for:
  - `lightsail:*`
  - basic CloudWatch metric reads
  - creation of the Lightsail service-linked role
- Role assumption and Tokyo Lightsail API access were verified successfully.
- User selected the Tokyo 2 GB public-IPv4 bundle `small_3_0`, currently
  USD 12/month, with Ubuntu 24.04 (`ubuntu_24_04`).
- The earlier zero-instance quota restriction was removed.
- A Service Quotas request was submitted on 2026-07-24 for the Tokyo
  Lightsail `Instances` quota (`L-4259AF9B`) to be raised from `0` to the AWS
  default value of `20` vCPUs. The console confirmed:

  ```text
  提交 Instances 的配额提高请求，请求的值为 20。
  ```

  Its status was `进行中` (in progress) at the last check.
- AWS Support case `178488660400942` was automatically created for this quota
  request. The only correspondence visible as of 2026-07-24 18:00 CST was the
  automatic request record (not a human Support reply):

  ```text
  Service: Amazon Lightsail
  Region: Asia Pacific (Tokyo)
  Limit name: Instances
  New limit value: 20
  Use case description: This support case was created by Service Quotas
  ```

  The earlier case history is retained here for reference.
- The user explicitly approved creation of one USD 12/month server.
- Lightsail instance `Ubuntu-1` was created on 2026-07-27 at
  `2026-07-27T20:09:56.576000+08:00`.
- AWS CLI verification confirmed:

  ```text
  State: running
  Availability Zone: ap-northeast-1a
  Bundle: small_3_0
  Blueprint: ubuntu_24_04
  Original ephemeral public IPv4: <ORIGINAL_EPHEMERAL_PUBLIC_IPV4>
  Private IPv4: <LIGHTSAIL_PRIVATE_IPV4>
  Public IPv6: <LIGHTSAIL_PUBLIC_IPV6>
  SSH username: ubuntu
  ```

- Static IP `ubuntu-1-tokyo-static-ip` is attached to `Ubuntu-1`.
- Current static public IPv4: `<LIGHTSAIL_PUBLIC_IPV4>`.
- The instance uses the Tokyo Lightsail default SSH key. Its private key is
  stored only at `<LOCAL_LIGHTSAIL_SSH_KEY_PATH>` with mode
  `600`; never print, copy, commit, or upload its contents.
- Automatic snapshots are disabled.
- The instance now incurs the approved USD 12/month Lightsail charge while it
  exists.
- The project is deployed at `/opt/xau-monitor`.
- `xau-monitor.service` is enabled and active. It runs the Python backend on
  `127.0.0.1:8765`. The backend serves XAUUSD and BTC_USDT market data,
  indicators, volume context, and the server-side `SCALP-1.0-PY` strategy.
- PostgreSQL 16.14 is installed on the same Lightsail instance. The service is
  enabled and active, listens only on `127.0.0.1:5432`, and uses
  SCRAM-SHA-256 password authentication.
- The local database and application role are both named `xau_monitor`. The
  role is not a superuser and cannot create databases, roles, or replication.
  The schema version is `4`, under the `app` schema.
- The database connection string is stored only in
  `/etc/xau-monitor/database.env`, owned by `root:root` with mode `600`.
  Never print, copy, commit, or upload this file or its value.
- `xau-monitor.service` loads that environment file. Database connectivity and
  a transactional insert/rollback were verified as the `ubuntu` service user.
  The application does not yet automatically persist market snapshots; the
  `app.strategy_snapshots` table is prepared for that later feature.
- Database-backed user authentication is enabled. `app.users` stores scrypt
  password hashes and `app.sessions` stores only SHA-256 session token
  digests. The raw password and raw session token are never stored in the
  project.
- WeCom daily levels are stored in `app.price_alerts`.
  `app.point_strategy_trials` stores the `LEVEL-5X5-V1` forward-test lifecycle:
  levels below the creation price are long, levels above are short, and each
  triggered trial is tracked to a fixed 5 USD stop or 5 USD target. Win rate
  excludes pending, expired, replaced, and cancelled trials. The price basis
  is Gate `last`, without spread, slippage, or fees.
- The initial account is `owner`. Its random initial password is stored in the
  deploying Mac's login keychain under service
  `sheshetrip.fun-user-login` and account `owner`. Never print or copy it into
  project files, logs, Git, chat, or documentation.
- `/login` is public, but the dashboard, account page, business JavaScript, and
  all market APIs require a valid database session. Users can change their own
  username or password at `/account`; doing so revokes their other sessions.
- No IP blacklist, IP rate limiting, or Fail2ban is enabled. This is an
  explicit user decision for the current phase. Future DDoS options are
  documented in `aws/USER_AUTH.md`.
- `xau-monitor-db-backup.timer` is enabled and active. It creates a validated
  custom-format `pg_dump` around 03:15 UTC daily and retains seven days in
  `/var/backups/xau-monitor-postgresql`.
- Local PostgreSQL operations and the future RDS migration procedure are
  documented in `aws/POSTGRESQL_TO_RDS.md`.
- The Lightsail firewall exposes TCP 22 only to this Mac's observed SSH source
  `/32` and the `lightsail-connect` alias. TCP 80 and 443 are public. The
  internal app port `8765` and PostgreSQL port `5432` are not publicly open.
- Local launcher `连接云端监控.command` creates an SSH tunnel from
  `127.0.0.1:18765` to the remote app and opens it in the browser.
- Alibaba Cloud DNS has enabled A records for both the root and `www` hostnames
  of `chopsticktrip.com` and `sheshetrip.fun`, all pointing to `<LIGHTSAIL_PUBLIC_IPV4>`.
- Caddy is installed, enabled, and active.
- `chopsticktrip.com` and `www.chopsticktrip.com` intentionally return an empty
  HTTP 200 response over HTTPS; do not deploy the monitor there.
- `sheshetrip.fun` and `www.sheshetrip.fun` reverse-proxy to
  `127.0.0.1:8765`.
- Let's Encrypt certificates were issued successfully for all four hostnames.
- HTTP for `sheshetrip.fun` returns a permanent redirect to HTTPS.
- `sheshetrip.fun` uses the Python application's database login system. Caddy
  does not use Basic Auth. Caddy enforces a 32 KiB request-body ceiling, adds
  security response headers, and writes rotating JSON access logs under
  `/var/log/caddy/`.
- The legacy standalone Sites deployment is retired and restricted to its
  owner. It is not a public production entry point. The local `sites/` source
  was moved to the Mac Trash after the Python deployment was verified.
- Lightsail now exposes TCP 80 and 443 publicly. TCP 22 remains restricted to
  this Mac's observed SSH source `/32` plus the `lightsail-connect` alias.
- Verification results:

  ```text
  http://sheshetrip.fun -> 308
  https://sheshetrip.fun without a session -> 303 to /login
  https://sheshetrip.fun/login -> 200
  /dashboard.js without a session -> 303 to /login
  /api/snapshot?market=btc without a session -> 401
  owner login -> 200 with Secure, HttpOnly, SameSite=Strict session cookie
  authenticated /api/snapshot?market=btc -> 200, strategy=SCALP-1.0-PY
  authenticated credential update -> 200
  logout -> 200; the same session then receives 401
  https://chopsticktrip.com -> 200 with a zero-byte body
  ```
- A Tokyo EC2 fallback was priced on 2026-07-24 for comparison:
  `t3.small` (2 vCPU / 2 GiB) is USD 0.0272/hour, or about USD 19.86
  per 730-hour month. Adding a 30 GB gp3 root volume (about USD 2.88/month)
  and one public IPv4 address (about USD 3.65/month) gives an estimated base
  total of about USD 26.39/month before excess traffic, snapshots, tax, and
  other optional services. This is substantially more expensive and more
  complex than the approved USD 12/month Lightsail plan.

Policy backups are in `aws/iam/`. They contain no credentials.

## Local AWS profiles

Use this profile for every deployment command:

```text
xau-lightsail
```

Example:

```bash
AWS_PAGER='' aws sts get-caller-identity \
  --profile xau-lightsail \
  --region ap-northeast-1
```

Expected ARN contains:

```text
assumed-role/XauMonitorDeployRole/
```

Profile chain:

```text
xau-cli-base -> xau-deploy-cli -> AssumeRole -> XauMonitorDeployRole
```

`xau-deploy` was the Root bootstrap login profile. Its cached login credentials
were removed. Do not use or re-login this profile for normal deployment.

Credentials exist only in the user's local `~/.aws/credentials` and AWS config.
Do not read, print, move, commit, or expose their values.

## Next action

1. Monitor service health, authentication logs, and Caddy certificate renewal.
2. If the Mac's public SSH source IP changes, update the Lightsail TCP 22 CIDR
   through AWS CLI; browser SSH remains available through `lightsail-connect`.
3. Never expose port `8765` or commit private keys/passwords.

## Safety

- Never create Root access keys.
- Never broaden the deployment role to AdministratorAccess.
- Never paste AWS secrets into project files, terminal output, or chat.
- Do not create paid resources without explicit confirmation.
- Prefer idempotent AWS commands and inspect existing resources first.
- Do not delete AWS resources unless the user explicitly requests it and exact
  targets have been verified.
