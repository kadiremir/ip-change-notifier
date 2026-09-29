"""Watch the external IP address and send a Telegram message when it changes."""
import json
import logging
import os
import re
import signal
import sys
import threading
import urllib.parse
import urllib.request
from pathlib import Path

def _load_dotenv():
    """Tiny .env loader so the script also runs natively (no Docker). Real env vars win."""
    for d in (Path(__file__).resolve().parent.parent, Path.cwd()):
        f = d / ".env"
        if f.is_file():
            for line in f.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("\"'"))
            return


_load_dotenv()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
INTERVAL = int(os.environ.get("CHECK_INTERVAL_SECONDS", "300"))
STATE_FILE = Path(
    os.environ.get("STATE_FILE") or Path.home() / ".ip-change-notifier" / "state.json"
)
NOTIFY_ON_START = os.environ.get("NOTIFY_ON_START", "false").lower() in ("1", "true", "yes")
HOSTNAME_LABEL = os.environ.get("LABEL", "")

IP_SERVICES = [
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://icanhazip.com",
    "https://checkip.amazonaws.com",
]
IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
IPV6 = re.compile(r"^[0-9a-fA-F:]+$")

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout
)
log = logging.getLogger("ip-notifier")
stop = threading.Event()


def get_external_ip():
    for url in IP_SERVICES:
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                ip = r.read().decode().strip()
            if IPV4.match(ip) or (":" in ip and IPV6.match(ip)):
                return ip
            log.warning("Unexpected response from %s: %r", url, ip[:50])
        except Exception as e:
            log.warning("IP lookup via %s failed: %s", url, e)
    return None


def send_telegram(text):
    global CHAT_ID
    api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    with urllib.request.urlopen(urllib.request.Request(api, data=data), timeout=15) as r:
        return json.load(r).get("ok", False)


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def save_state(**updates):
    state = load_state()
    state.update(updates)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(STATE_FILE)


def discover_chat_id():
    """Find the chat id from the latest message sent to the bot."""
    api = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    try:
        with urllib.request.urlopen(api, timeout=15) as r:
            updates = json.load(r).get("result", [])
    except Exception as e:
        log.error("getUpdates failed: %s", e)
        return None
    for u in reversed(updates):
        msg = u.get("message") or u.get("channel_post") or {}
        if "chat" in msg:
            return str(msg["chat"]["id"])
    return None


def ensure_chat_id():
    global CHAT_ID
    if CHAT_ID:
        return True
    CHAT_ID = load_state().get("chat_id", "") or discover_chat_id() or ""
    if not CHAT_ID:
        log.warning("No chat id yet. Send any message to your bot in Telegram.")
        return False
    save_state(chat_id=CHAT_ID)
    log.info("Using chat id %s", CHAT_ID)
    try:
        send_telegram("Connected. I'll message you when your IP changes.")
    except Exception as e:
        log.error("Telegram send failed: %s", e)
    return True


def check_address(key, title, current):
    """Compare `current` with the stored value for `key`; notify and save on change."""
    last = load_state().get(key)
    if current is None or current == last:
        if current:
            log.info("%s unchanged: %s", title, current)
        return
    label = f" [{HOSTNAME_LABEL}]" if HOSTNAME_LABEL else ""
    if last is None:
        msg, should_notify = f"IP monitor started{label}. {title}: {current}", NOTIFY_ON_START
    else:
        msg, should_notify = f"{title} changed{label}\nOld: {last}\nNew: {current}", True
    if should_notify:
        try:
            send_telegram(msg)
            log.info("Notification sent: %s", msg.replace("\n", " | "))
        except Exception as e:
            # Keep the old value so the notification is retried next cycle.
            log.error("Telegram send failed: %s", e)
            return
    save_state(**{key: current})


def check_once():
    if not ensure_chat_id():
        return
    ext = get_external_ip()
    if ext is None:
        log.error("Could not determine external IP; will retry")
    check_address("ip", "External IP", ext)


def main():
    if not BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN must be set")
        sys.exit(1)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    log.info("Started. Interval=%ss", INTERVAL)
    while not stop.is_set():
        check_once()
        # Poll quickly until we know the chat id, then use the normal interval.
        stop.wait(INTERVAL if CHAT_ID else 10)


if __name__ == "__main__":
    main()
