# Contributing

Thanks for helping improve MyDiscordMusicBot. Contributions that improve reliability, documentation, accessibility, localization, testing, or gameplay are welcome.

## Before you start

- Search existing issues before opening a new one.
- For bugs, include the command or feature used, expected behavior, actual behavior, relevant logs, Python version, hosting environment, and reproduction steps.
- For larger features, open an issue first so the design and scope can be discussed before implementation.
- Never post Discord tokens, API keys, cookies, `.env` files, or other secrets in issues, pull requests, logs, screenshots, or commits.

## Development setup

Requirements:

- Python 3.11+
- FFmpeg
- A Discord application/bot for local testing

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python main.py
```

Fill only the credentials needed for the feature you are testing. Do not commit `.env` or cookie files.

## Project layout

- `main.py` — bot startup, intents, extension loading, command sync
- `cogs/music.py` — voice/music playback and yt-dlp integration
- `cogs/werewolf_bot.py` — Discord command entry points for Werewolf
- `cogs/werewolf_system/` — game state, roles, rules, UI and round flow
- `cogs/chat.py` — AI chat integration
- `Dockerfile` — production/container deployment path

## Making a change

1. Fork the repository and create a focused branch.
2. Keep each pull request limited to one coherent change.
3. Preserve compatibility with the production Python version used by the Docker image.
4. Update documentation when commands, environment variables, behavior, or deployment steps change.
5. Run the validation commands below before opening a pull request.

```bash
python -m compileall -q main.py cogs
python -m pip check
```

If your change adds testable pure logic, please add automated tests where practical.

## Pull requests

A good pull request includes:

- what changed and why;
- how the change was tested;
- user-visible behavior changes;
- deployment/configuration changes, if any;
- screenshots or logs when they materially help review.

Maintainers may request changes for security, backwards compatibility, maintainability, or project-scope reasons.

## Security reports

Do not disclose suspected vulnerabilities publicly. Follow `SECURITY.md`.

## License

By contributing, you agree that your contribution will be licensed under the repository's AGPL-3.0 license.