# Agent entrypoint

This is a Python Gate XAUUSD / BTCUSDT monitoring dashboard.

- Read `AI_PROJECT_KNOWLEDGE.md` first. It is the canonical project handoff and
  records the current architecture, production state, known gaps, and safety
  boundaries.
- For AWS, IAM, hosting, or deployment work, read `aws/AI_HANDOFF.md` first.
- Do not rediscover or recreate the AWS identities already documented there.
- Never print, copy, commit, or request AWS access keys or secrets.
- Never write user passwords, session cookies, database URLs, private keys, or
  credential values into project files, logs, Git, chat, or documentation.
- The user explicitly chose not to enable IP blacklists, IP rate limiting, or
  Fail2ban for now.
- Creating paid AWS resources requires explicit user confirmation.
