# ip-change-notifier

Checks your external IP every few minutes and sends a Telegram message when it changes. Runs in Docker; stdlib-only Python, no dependencies.

## Setup

1. Create a bot via [@BotFather](https://t.me/BotFather) and copy the token.
2. Send any message (e.g. "hi") to your bot in Telegram.
3. `cp .env.example .env` and fill in the token. The chat id is detected automatically from your message (or set `TELEGRAM_CHAT_ID` yourself).
4. `docker compose up -d --build`
5. `docker compose logs -f`

## Config (env vars)

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | required | Bot token |
| `TELEGRAM_CHAT_ID` | auto-detected | Chat to notify; if empty, taken from the latest message sent to the bot |
| `CHECK_INTERVAL_SECONDS` | `300` | Check frequency |
| `NOTIFY_ON_START` | `false` | Send a message with the IP on first run |
| `LABEL` | empty | Tag added to messages (useful with several hosts) |

The last known IP is stored in the `ip-state` volume, so restarts don't trigger false alerts. If Telegram is unreachable, the change is retried on the next cycle.

## Run directly on a computer (no Docker)

Works on macOS, Windows and Linux with Python 3.8+ and no extra packages. It reads the same `.env` file.

```
python3 app/main.py        # Windows: py app\main.py
```

State is kept in `~/.ip-change-notifier/state.json`.

### Start automatically at login

**macOS** – create `~/Library/LaunchAgents/com.ipnotifier.plist` (adjust the path), then run `launchctl load ~/Library/LaunchAgents/com.ipnotifier.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
  <key>Label</key><string>com.ipnotifier</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/python3</string>
    <string>/Users/kadir/Projects/ip-change-notifier/app/main.py</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict></plist>
```

**Windows** – in PowerShell (adjust the path):

```
schtasks /Create /TN IpNotifier /SC ONLOGON /TR "pythonw C:\path\to\ip-change-notifier\app\main.py"
```

**Linux** – `~/.config/systemd/user/ip-notifier.service`, then `systemctl --user enable --now ip-notifier`:

```
[Unit]
Description=IP change notifier
[Service]
ExecStart=/usr/bin/python3 /path/to/ip-change-notifier/app/main.py
Restart=always
[Install]
WantedBy=default.target
```
