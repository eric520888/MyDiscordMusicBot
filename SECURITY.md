# Security Policy

Security issues are handled separately from normal bug reports.

## Supported version

The `main` branch is the actively maintained version. Security fixes are normally applied there first.

## Reporting a vulnerability

Please **do not open a public issue with exploit details, secrets, tokens, cookies, private logs, or proof-of-concept material**.

Preferred reporting path:

1. Use GitHub's private vulnerability reporting / Security Advisory flow for this repository when it is available.
2. Include a concise description, affected component, reproduction conditions, expected impact, and suggested mitigation if known.
3. Remove or redact Discord tokens, API keys, cookies, guild/user data, and other credentials from evidence.

If private vulnerability reporting is not available, open a minimal public issue asking the maintainer for a private reporting channel **without including vulnerability details**.

## Scope

Security-sensitive areas include, but are not limited to:

- Discord authentication and permission handling;
- token, API-key and cookie handling;
- yt-dlp / YouTube authentication integration;
- command authorization and owner-only operations;
- user-controlled input passed to subprocesses or external services;
- deployment and container configuration;
- third-party dependency vulnerabilities.

## Secrets

The repository intentionally excludes `.env`, cookie files, logs, and `secrets/` through `.gitignore`. If a credential is accidentally committed, treat it as compromised and rotate/revoke it immediately; deleting it from a later commit is not sufficient.

## Disclosure

Please allow reasonable time for validation and remediation before public disclosure. Once a fix is ready, the maintainer may publish an advisory describing affected versions and the remediation.