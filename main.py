"""TeleCopy — copy/forward Telegram messages between chats via TDLib."""

import os
import sys
import hashlib
import shutil
import json
import logging
import threading
import time
import re
import atexit
from datetime import datetime, timezone
from dotenv import load_dotenv, set_key, find_dotenv
from telegram.client import Telegram
from tqdm import tqdm

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("telecopy.log"),
    ],
)
log = logging.getLogger("telecopy")

# ── Service-message types that should not be forwarded ────────────────────────
EXCLUDE_TYPES = frozenset({
    "messageChatChangePhoto", "messageChatChangeTitle",
    "messageBasicGroupChatCreate", "messageChatDeleteMember",
    "messageChatAddMembers", "messagePinMessage",
    "messageChatSetTheme", "messageChatSetMessageAutoDeleteTime",
    "messageSupergroupChatCreate", "messageChatJoinByLink",
    "messageVideoChatStarted", "messageVideoChatEnded",
    "messageVideoChatScheduled", "messageProximityAlertTriggered",
})

COPY_MAP_PATH = "data/copy_map.json"
SESSION_CFG_PATH = "data/last_session_config.json"
SAVE_EVERY = 50  # flush copy-map to disk after every N new copies


class TeleCopy:
    def __init__(self):
        self.tg = None
        self.session_active = False
        self.monitoring = False
        self.config_path = find_dotenv(usecwd=True) or ".env"
        self._pending_saves = 0
        self.copied: dict[int, int] = {}  # source msg ID → destination msg ID
        self._load_config()
        atexit.register(self.save_copy_map)

    # ── Configuration ───────────────────────────────────────────────────────

    def _load_config(self):
        load_dotenv(self.config_path)
        os.makedirs("data", exist_ok=True)
        self.copied = self._load_copy_map()

    def check_env_vars(self):
        required = ["PHONE", "API_ID", "API_HASH"]
        missing = [v for v in required if not os.getenv(v)]
        if missing:
            log.warning("Missing env values: %s", missing)
            for var in missing:
                value = input(f"Enter value for {var}: ").strip()
                set_key(self.config_path, var, value)
            log.info(".env updated. Please restart TeleCopy.")
            sys.exit(0)

    # ── Session fingerprint (stores hash, not raw credentials) ─────────────

    @staticmethod
    def _fingerprint(api_id: str, api_hash: str, phone: str) -> str:
        return hashlib.sha256(f"{api_id}{api_hash}{phone}".encode()).hexdigest()

    def handle_connection(self):
        self.check_env_vars()
        load_dotenv(self.config_path, override=True)
        api_id = os.getenv("API_ID", "")
        api_hash = os.getenv("API_HASH", "")
        phone = os.getenv("PHONE", "")
        new_fp = self._fingerprint(api_id, api_hash, phone)

        try:
            with open(SESSION_CFG_PATH) as f:
                old_fp = json.load(f).get("fingerprint", "")
        except (FileNotFoundError, json.JSONDecodeError):
            old_fp = ""

        if old_fp != new_fp:
            log.info("Credentials changed – resetting session…")
            for d in ("tdlib-session", "data"):
                try:
                    shutil.rmtree(d)
                except FileNotFoundError:
                    pass
            self.copied.clear()
            self._pending_saves = 0

        os.makedirs("data", exist_ok=True)
        with open(SESSION_CFG_PATH, "w") as f:
            json.dump({"fingerprint": new_fp}, f)

        self._init_telegram()
        log.info("✅ Connected to Telegram.")

    def _init_telegram(self):
        proxy_type = os.getenv("PROXY_TYPE")
        proxy_port_raw = os.getenv("PROXY_PORT")
        self.tg = Telegram(
            api_id=os.getenv("API_ID"),
            api_hash=os.getenv("API_HASH"),
            phone=os.getenv("PHONE"),
            database_encryption_key=os.getenv("DB_PASSWORD"),
            files_directory=os.getenv("FILES_DIRECTORY", "data/tdlib_files"),
            proxy_server=os.getenv("PROXY_SERVER"),
            proxy_port=int(proxy_port_raw) if proxy_port_raw else None,
            proxy_type={"@type": proxy_type} if proxy_type else None,
        )
        self.tg.login()
        self.session_active = True

    # ── Chat selection ──────────────────────────────────────────────────────

    def set_chats(self):
        self._list_chats()
        src = input("Enter source chat ID: ").strip()
        dst = input("Enter destination chat ID: ").strip()
        set_key(self.config_path, "SOURCE", src)
        set_key(self.config_path, "DESTINATION", dst)
        log.info("✅ Source and destination saved.")

    def _list_chats(self):
        result = self.tg.get_chats(limit=200)
        result.wait()
        if not result.update:
            log.error("Failed to retrieve chat list.")
            return
        chat_ids = result.update.get("chat_ids", [])
        log.info("Available chats (%d):", len(chat_ids))
        for cid in chat_ids:
            r = self.tg.get_chat(cid)
            r.wait()
            title = r.update.get("title", "Private Chat") if r.update else str(cid)
            print(f"  {cid}: {title}")

    def _validate_chats(self):
        load_dotenv(self.config_path, override=True)
        src = os.getenv("SOURCE")
        dst = os.getenv("DESTINATION")
        if not src or not dst:
            log.error("SOURCE and DESTINATION must be set first (option 1).")
            return None, None
        try:
            return int(src), int(dst)
        except ValueError:
            log.error("SOURCE and DESTINATION must be valid integer chat IDs.")
            return None, None

    # ── Copy-map persistence ────────────────────────────────────────────────

    def _load_copy_map(self) -> dict:
        try:
            with open(COPY_MAP_PATH) as f:
                return {int(k): v for k, v in json.load(f).items()}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_copy_map(self):
        os.makedirs("data", exist_ok=True)
        with open(COPY_MAP_PATH, "w") as f:
            json.dump(self.copied, f)
        self._pending_saves = 0

    def _record_copy(self, src_id: int, dst_id: int):
        self.copied[src_id] = dst_id
        self._pending_saves += 1
        if self._pending_saves >= SAVE_EVERY:
            self.save_copy_map()

    # ── Message fetching (streaming — low RAM footprint) ────────────────────

    def _iter_messages(self, chat_id: int):
        """Yield message objects from *chat_id*, newest-to-oldest, in batches of 100."""
        last = 0
        while True:
            try:
                result = self.tg.get_chat_history(chat_id, limit=100, from_message_id=last)
                result.wait()
                batch = result.update.get("messages", [])
                if not batch:
                    return
                yield from batch
                last = batch[-1]["id"]
            except Exception as e:
                log.error("Error fetching messages: %s", e)
                return

    # ── Message forwarding with FloodWait + exponential back-off ───────────

    def copy_message(self, src: int, dst: int, msg_id: int):
        """Forward *msg_id* from *src* to *dst*.

        Respects Telegram FloodWait delays and uses exponential back-off for
        other transient failures.  Returns the new message ID on success,
        or None after 5 failed attempts.
        """
        data = {
            "chat_id": dst,
            "from_chat_id": src,
            "message_ids": [msg_id],
            "send_copy": os.getenv("SEND_COPY", "true").lower() == "true",
        }
        attempt = 0
        while attempt < 5:
            try:
                result = self.tg.call_method("forwardMessages", data, block=True)
                msgs = result.update.get("messages", [None])
                if not msgs or msgs[0] is None:
                    raise ValueError(f"Null response for message {msg_id}")
                return msgs[0]["id"]
            except Exception as e:
                flood = re.search(
                    r'(?:FLOOD_WAIT|flood_wait)_(\d+)', str(e), re.IGNORECASE
                )
                if flood:
                    wait = int(flood.group(1))
                    log.warning(
                        "FloodWait %ds for message %d – sleeping…",
                        wait, msg_id,
                    )
                    time.sleep(wait)
                    # FloodWait is a server throttle, not a real failure;
                    # do not count it against the attempt budget.
                else:
                    attempt += 1
                    if attempt >= 5:
                        break
                    wait = 2 ** attempt
                    log.warning(
                        "Error on attempt %d/5 for message %d: %s (retrying in %ds)",
                        attempt, msg_id, e, wait,
                    )
                    time.sleep(wait)
        log.error("Failed to copy message %d after 5 attempts.", msg_id)
        return None

    # ── Date helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _parse_date_utc(date_str: str, end_of_day: bool = False):
        """Parse 'YYYY-MM-DD' as midnight UTC (or 23:59:59 when *end_of_day* is True).

        Returns None for an empty string.
        """
        if not date_str:
            return None
        ts = int(
            datetime.strptime(date_str, "%Y-%m-%d")
            .replace(tzinfo=timezone.utc)
            .timestamp()
        )
        if end_of_day:
            ts += 86399  # advance to 23:59:59 of the same day
        return ts

    # ── Copy operations ─────────────────────────────────────────────────────

    def full_copy(self):
        """Copy every historical message from source to destination."""
        src, dst = self._validate_chats()
        if src is None:
            return

        log.info("Fetching message list from source chat %d…", src)
        ids = [
            m["id"] for m in self._iter_messages(src)
            if m.get("content", {}).get("@type") not in EXCLUDE_TYPES
        ]
        ids.reverse()  # oldest → newest

        log.info("Found %d messages to process.", len(ids))

        count = 0
        for mid in tqdm(ids, desc="Copying", unit="msg"):
            if mid in self.copied:
                continue
            new_id = self.copy_message(src, dst, mid)
            if new_id:
                self._record_copy(mid, new_id)
                count += 1

        self.save_copy_map()
        log.info("✅ Full copy complete — %d messages copied.", count)

    def date_copy(self):
        """Copy messages within a user-specified date range."""
        src, dst = self._validate_chats()
        if src is None:
            return

        from_date = input("Start date (YYYY-MM-DD) [blank = from beginning]: ").strip()
        to_date   = input("End date (YYYY-MM-DD)   [blank = until latest]:    ").strip()
        from_ts = self._parse_date_utc(from_date)
        to_ts   = self._parse_date_utc(to_date, end_of_day=True)

        log.info("Fetching messages in date range…")
        filtered = []
        for m in self._iter_messages(src):
            msg_date = m["date"]
            # _iter_messages yields newest-to-oldest; once we go past from_ts
            # all subsequent messages will be even older — stop early.
            if from_ts is not None and msg_date < from_ts:
                break
            if m.get("content", {}).get("@type") in EXCLUDE_TYPES:
                continue
            if to_ts is not None and msg_date > to_ts:
                continue
            filtered.append(m)
        filtered.reverse()  # oldest → newest

        log.info("Found %d messages in the specified date range.", len(filtered))

        count = 0
        for msg in tqdm(filtered, desc="Copying", unit="msg"):
            mid = msg["id"]
            if mid in self.copied:
                continue
            new_id = self.copy_message(src, dst, mid)
            if new_id:
                self._record_copy(mid, new_id)
                count += 1

        self.save_copy_map()
        log.info("✅ Date-range copy complete — %d messages copied.", count)

    def start_live_monitoring(self):
        """Forward new messages from source to destination in real time."""
        src, dst = self._validate_chats()
        if src is None:
            return

        lock = threading.Lock()
        pending: set[int] = set()  # message IDs currently being forwarded

        def handle_update(update):
            if update.get("@type") != "updateNewMessage":
                return
            message = update["message"]
            if message["chat_id"] != src:
                return
            if message.get("content", {}).get("@type") in EXCLUDE_TYPES:
                return
            mid = message["id"]
            with lock:
                if mid in self.copied or mid in pending:
                    return
                pending.add(mid)
            try:
                new_id = self.copy_message(src, dst, mid)
                if new_id:
                    with lock:
                        self._record_copy(mid, new_id)
                        self.save_copy_map()
                    log.info("Live copied %d → %d", mid, new_id)
            finally:
                with lock:
                    pending.discard(mid)

        self.monitoring = True
        self.tg.add_update_handler(handle_update)
        log.info("📡 Live monitoring started. Press Ctrl+C to stop.")
        try:
            while self.monitoring:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.monitoring = False
            self.tg.remove_update_handler(handle_update)
            log.info("Live monitoring stopped.")

    # ── Settings ────────────────────────────────────────────────────────────

    def update_config(self):
        """Interactively update API credentials without restarting."""
        load_dotenv(self.config_path, override=True)
        keys = ["PHONE", "API_ID", "API_HASH"]
        current = {k: os.getenv(k, "Not Set") for k in keys}
        print("\nCurrent Configuration:")
        for idx, (k, v) in enumerate(current.items(), 1):
            print(f"  {idx}. {k}: {v}")
        print("  0. Return to main menu")
        while True:
            choice = input("Select which to update (1-3, 0 to return): ").strip()
            if choice == "0":
                return
            try:
                idx = int(choice) - 1
                if idx < 0 or idx >= len(keys):
                    raise IndexError
                key = keys[idx]
            except (IndexError, ValueError):
                print("Invalid selection.")
                continue
            new_val = input(f"Enter new value for {key}: ").strip()
            set_key(self.config_path, key, new_val)
            log.info("%s updated. Restart TeleCopy to apply.", key)

    def advanced_menu(self):
        print("\nAdvanced Settings:")
        print("  1. Clear copy history")
        print("  2. Reset session data")
        print("  0. Back")
        choice = input("Select: ").strip()
        if choice == "1":
            try:
                os.remove(COPY_MAP_PATH)
                self.copied.clear()
                log.info("✅ Copy history cleared.")
            except FileNotFoundError:
                log.info("No copy history found.")
        elif choice == "2":
            for d in ("tdlib-session", "data"):
                try:
                    shutil.rmtree(d)
                    log.info("Removed %s/", d)
                except FileNotFoundError:
                    pass
            self.copied.clear()
            self._pending_saves = 0
            self.tg = None
            self.session_active = False
            log.info("✅ Session data reset. Please reconnect (option 0).")

    # ── Graceful shutdown ───────────────────────────────────────────────────

    def clean_exit(self):
        self.monitoring = False
        if self.tg:
            try:
                self.tg.stop()
            except Exception:
                pass
        log.info("👋 Goodbye!")
        sys.exit(0)

    # ── Main menu ───────────────────────────────────────────────────────────

    def show_menu(self):
        while True:
            print("""
========= TeleCopy =========
0. Connect to Telegram
1. Set source and destination
2. Copy full history
3. Live monitoring (auto-forward)
4. Copy by date range
5. Update API credentials
6. Advanced settings
7. Exit
""")
            choice = input("Choose an option: ").strip()

            if choice == "0":
                self.handle_connection()
            elif choice == "5":
                self.update_config()
            elif choice == "6":
                self.advanced_menu()
            elif choice == "7":
                self.clean_exit()
            elif not self.session_active:
                print("Please connect to Telegram first (option 0).")
            elif choice == "1":
                self.set_chats()
            elif choice == "2":
                self.full_copy()
            elif choice == "3":
                self.start_live_monitoring()
            elif choice == "4":
                self.date_copy()
            else:
                print("Invalid choice.")


if __name__ == "__main__":
    tc = TeleCopy()
    try:
        tc.show_menu()
    except KeyboardInterrupt:
        tc.clean_exit()
