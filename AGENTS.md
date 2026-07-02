# Repository Instructions

## Security
- Treat security as the first constraint for all changes in this repo.
- Never read, print, summarize, or open sensitive local files, even for debugging.
- Sensitive files include `.env`, `.env.*`, `*.env`, key/certificate files, credential files, local database dumps, provider tokens, and secret-like paths.
- Never log or print credentials, API keys, Discord webhook URLs, auth cookies, session tokens, PII, or portfolio-sensitive data. Use redacted placeholders such as `<redacted>`.
- Store credentials only in environment variables or a secrets manager. Do not hardcode credentials in source, tests, fixtures, docs, or examples.
- Ask before adding a new config location that could contain secrets.
- Flag potential OWASP Top 10 risks immediately when reviewing or changing code.

## Secret Handling
- Track `env.example` only with placeholder values.
- Do not create or edit real `.env` files from Codex.
- Run Codex with restricted filesystem sandboxing for this repo. Deny reads for `.env`, `.env.*`, `*.env`, key/certificate files, credential files, `.aws/`, `.ssh/`, `.netrc`, `.npmrc`, `.pypirc`, and secret-like paths.
- Do not use shell commands that dump environment variables or provider configuration unless the output is explicitly redacted first.
- Run `make security-scan` before commits that touch configuration, auth, providers, notifications, or deployment.

## Git
- Stage specific files only.
- Ask before committing or pushing.
- Never bypass hooks unless explicitly requested.
