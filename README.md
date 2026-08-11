# MyDiscordMusicBot

**A modular open-source Discord entertainment bot combining music playback, a fully hosted Werewolf game, and AI chat.**

[![CI](https://github.com/eric520888/MyDiscordMusicBot/actions/workflows/ci.yml/badge.svg)](https://github.com/eric520888/MyDiscordMusicBot/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/github/license/eric520888/MyDiscordMusicBot)](LICENSE)
[![Stars](https://img.shields.io/github/stars/eric520888/MyDiscordMusicBot)](https://github.com/eric520888/MyDiscordMusicBot/stargazers)
[![Forks](https://img.shields.io/github/forks/eric520888/MyDiscordMusicBot)](https://github.com/eric520888/MyDiscordMusicBot/network/members)
[![Last commit](https://img.shields.io/github/last-commit/eric520888/MyDiscordMusicBot)](https://github.com/eric520888/MyDiscordMusicBot/commits/main)

> 繁體中文摘要：這是一個以 `discord.py` 開發、持續維護的模組化 Discord Bot。核心功能包含 YouTube 音樂播放、完整自動主持的狼人殺遊戲，以及 AI 對話。專案以 AGPL-3.0 開源，歡迎提交 Issue、Pull Request、文件、翻譯與測試貢獻。

## Why this project exists

Many Discord bots focus on a single command or depend on an external human host for social games. This project explores a reusable, self-hostable entertainment stack where voice playback, interactive Discord UI, game state, role logic, and AI features can coexist in one modular bot.

The most substantial subsystem is the **Werewolf engine**: it automates lobby creation, role assignment, night actions, voting, win-condition checks, and post-game review through Discord interactions instead of requiring a human game master.

## Features

### Music / voice

- YouTube search and playback with `yt-dlp`
- interactive player controls, cover art and progress display
- queue management and loop modes
- seek and play-from-timestamp support
- Docker/Railway deployment path
- fallback handling for YouTube authentication, PO-token, JavaScript challenge, and datacenter playback issues

Common commands:

| Command | Description |
| --- | --- |
| `/play <query or URL>` | Search and play audio |
| `/play_at <time> <query or URL>` | Start playback from a timestamp |
| `/seek <time>` | Seek within the current track |
| `!pause` / `!resume` | Pause or resume |
| `!skip` | Skip current track |
| `!stop` | Stop and clear queue |
| `!queue` | Show queue |
| `!loop` | Cycle loop mode |

### Werewolf game engine

- graphical lobby with `/ww_create`
- **23 supported 12-player board configurations**
- automated role assignment and hidden-information flow
- interactive night actions for wolves and special roles
- daytime voting, ties, last words and role-triggered actions
- automatic win-condition evaluation
- `/ww_rules` rules/configuration reference
- `/ww_status` round, phase and alive-player status
- post-game review with role reveal and round history

The game code is separated into `cogs/werewolf_system/` so gameplay rules, state, UI, roles, and round flow can evolve independently from Discord command entry points.

### AI chat

- mention-based conversational responses
- Google Gemini integration
- optional feature: the bot can run without exposing API credentials in source control

## Architecture

```text
.
├── main.py                  # startup, intents, extension loading, command sync
├── cogs/
│   ├── music.py             # voice/music + yt-dlp integration
│   ├── werewolf_bot.py      # Werewolf Discord commands
│   ├── werewolf_system/     # game state, rules, roles, UI, round flow
│   ├── chat.py              # AI chat integration
│   ├── custom_help.py
│   └── General.py
├── .env.example             # documented configuration without secrets
├── Dockerfile               # container / Railway deployment
├── requirements.txt
├── CONTRIBUTING.md
├── SECURITY.md
└── LICENSE
```

## Quick start

### Requirements

- Python 3.11+
- FFmpeg
- a Discord application/bot token
- optional Gemini API key for AI chat

### Install

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env`, then fill in the credentials needed for your deployment.

```bash
python main.py
```

**Never commit `.env`, Discord tokens, API keys, cookies, or private logs.** The repository's `.gitignore` excludes the common secret-bearing files used by this project.

## Configuration

The canonical configuration reference is [`.env.example`](.env.example). Important variables include:

- `DISCORD_BOT_TOKEN`
- `GEMINI_API_KEY`
- `OWNER_IDS`
- `LOG_LEVEL`
- `YTDLP_COOKIES_FROM_BROWSER`
- `YTDLP_COOKIE_FILE`
- `YTDLP_COOKIES_B64`
- `YTDLP_LOW_RESOURCE`
- `YTDLP_DENO_V8_FLAGS`
- `YTDLP_NODE_OPTIONS`

For server/container deployments, keep cookie files outside the repository or inject them through the hosting platform's secret-management system.

## Open-source maintenance

This repository is actively maintained and is structured for outside contributions:

- **AGPL-3.0** open-source license
- `CONTRIBUTING.md` with local setup and validation guidance
- `SECURITY.md` for responsible vulnerability reporting
- structured bug and feature-request templates
- pull-request checklist
- GitHub Actions CI for dependency consistency and Python compilation
- Dependabot configuration for Python, GitHub Actions, and Docker dependencies
- CODEOWNERS for maintainer review of sensitive areas

Recent maintenance has included production deployment compatibility, Railway/YouTube playback fixes, dependency updates, and continued development of the Werewolf subsystem.

## Contributing

Contributions are welcome, especially in these areas:

- Werewolf rules, roles, game-flow correctness and tests
- multilingual UI / localization
- accessibility and interaction UX
- music playback reliability across hosting environments
- deployment documentation
- automated tests and CI improvements
- security hardening and dependency maintenance

Please read [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a pull request. For vulnerabilities, follow [`SECURITY.md`](SECURITY.md) instead of posting exploit details publicly.

## Validation

Before submitting changes:

```bash
python -m compileall -q main.py cogs
python -m pip check
```

Pull requests run the same baseline checks in GitHub Actions.

## Roadmap

Current directions include:

- Werewolf sheriff/badge mechanics
- broader multilingual support
- more automated tests around pure game logic
- improved deployment and playback resilience

Roadmap items are not release promises; implementation priority depends on maintenance needs and contributor interest.

## License

Source code is licensed under **GNU AGPL-3.0**. See [`LICENSE`](LICENSE).

If you modify this project and operate the modified version as a network service, review the AGPL-3.0 source-availability obligations that may apply to your deployment.

### Third-party media notice

`sounds/night.mp3` is included only for testing/demonstration and is **not claimed as original project-owned media**. Redistributors and deployers should replace it with audio they have the right to use.

## Project independence

This is an independent open-source project and is not affiliated with or endorsed by Discord, Google, YouTube, Railway, or the publishers/operators of third-party Werewolf game variants referenced by the implementation.
