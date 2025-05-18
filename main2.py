import os
import sys
import shutil
import pickle
import threading
import time
import re
import json
from datetime import datetime
from dotenv import load_dotenv, set_key, find_dotenv
from telegram.client import Telegram
from tqdm import tqdm
from backoff import on_exception, expo

EXCLUDE_TYPES = [
    "messageChatChangePhoto", "messageChatChangeTitle",
    "messageBasicGroupChatCreate", "messageChatDeleteMember",
    "messageChatAddMembers", "messagePinMessage",
    "messageChatSetTheme", "messageChatSetMessageAutoDeleteTime",
    "messageSupergroupChatCreate", "messageChatJoinByLink",
    "messageVideoChatStarted", "messageVideoChatEnded",
    "messageVideoChatScheduled", "messageProximityAlertTriggered"
]

class TeleCopy:
    def __init__(self):
        self.tg = None
        self.session_active = False
        self.monitoring = False
        self.monitor_event = threading.Event()
        self.last_message_id = 0
        self.config_path = find_dotenv()
        self.load_config()

    def load_config(self):
        """Load or initialize configuration"""
        load_dotenv(self.config_path)
        os.makedirs('data', exist_ok=True)
        try:
            with open('data/last_message.pkl', 'rb') as f:
                self.last_message_id = pickle.load(f)
        except (FileNotFoundError, EOFError):
            self.last_message_id = 0

    def check_env_vars(self):
        """Validate required environment variables"""
        required = ["PHONE", "API_ID", "API_HASH"]
        missing = [var for var in required if not os.getenv(var)]
        if missing:
            print(f"Missing env values: {missing}")
            for var in missing:
                value = input(f"Enter value for {var}: ")
                set_key(self.config_path, var, value)
            print("✅ .env updated. Please restart.")
            sys.exit()

    def initialize_telegram(self):
        """Initialize Telegram connection"""
        self.tg = Telegram(
            api_id=os.getenv("API_ID"),
            api_hash=os.getenv("API_HASH"),
            phone=os.getenv("PHONE"),
            database_encryption_key=os.getenv("DB_PASSWORD"),
            files_directory=os.getenv("FILES_DIRECTORY"),
        )
        self.tg.login()
        self.session_active = True

    def handle_connection(self):
        """Handle Telegram connection setup"""
        self.check_env_vars()
        try:
            with open("data/last_session_config.pickle", "rb") as f:
                last = pickle.load(f)
        except FileNotFoundError:
            last = {}

        if (last.get("API_ID") != os.getenv("API_ID") or
            last.get("API_HASH") != os.getenv("API_HASH") or
            last.get("PHONE") != os.getenv("PHONE")):
            print("🔁 Config changed - resetting session...")
            try:
                shutil.rmtree('tdlib-session')
            except FileNotFoundError:
                pass

        os.makedirs("data", exist_ok=True)
        with open("data/last_session_config.pickle", "wb") as f:
            pickle.dump({
                "API_ID": os.getenv("API_ID"),
                "API_HASH": os.getenv("API_HASH"),
                "PHONE": os.getenv("PHONE")
            }, f)

        self.initialize_telegram()
        print("✅ Connected to Telegram.")
        time.sleep(1)

    def set_chats(self):
        """Set source and destination chats"""
        src = input("Enter source chat ID: ")
        dest = input("Enter destination chat ID: ")
        set_key(self.config_path, "SOURCE", src)
        set_key(self.config_path, "DESTINATION", dest)
        print("✅ Chats updated.")

    def full_copy(self):
        """Copy all historical messages"""
        if not self.validate_chats():
            return
            
        src = int(os.getenv("SOURCE"))
        dest = int(os.getenv("DESTINATION"))
        
        messages = self.get_messages(src)
        print(f"Copying {len(messages)} messages...")
        
        copied = self.load_copy_map()
        
        for msg in tqdm(reversed(messages), total=len(messages)):
            if msg['id'] in copied:
                continue
            new_id = self.copy_message(src, dest, msg['id'])
            if new_id:
                copied[msg['id']] = new_id
                self.save_copy_map(copied)

        print("✅ Full copy complete.")

    def validate_chats(self):
        """Check if chats are properly configured"""
        if not os.getenv("SOURCE") or not os.getenv("DESTINATION"):
            print("❌ Source and destination must be set first!")
            return False
        return True

    def load_copy_map(self):
        """Load message ID mapping"""
        try:
            with open("data/copy_map.pkl", "rb") as f:
                return pickle.load(f)
        except FileNotFoundError:
            return {}

    def save_copy_map(self, data):
        """Save message ID mapping"""
        with open("data/copy_map.pkl", "wb") as f:
            pickle.dump(data, f)

    def date_copy(self):
        """Copy messages within date range"""
        if not self.validate_chats():
            return

        src = int(os.getenv("SOURCE"))
        dest = int(os.getenv("DESTINATION"))
        
        from_date = input("Start date (YYYY-MM-DD): ")
        to_date = input("End date (YYYY-MM-DD): ")
        
        messages = self.get_messages(src)
        filtered = self.filter_messages(messages, from_date, to_date)
        
        copied = self.load_copy_map()
        
        for msg in tqdm(reversed(filtered), total=len(filtered)):
            if msg['id'] in copied:
                continue
            new_id = self.copy_message(src, dest, msg['id'])
            if new_id:
                copied[msg['id']] = new_id
                self.save_copy_map(copied)

        print(f"✅ Copied {len(filtered)} messages.")

    def filter_messages(self, messages, from_date, to_date):
        """Filter messages by date range"""
        from_ts = datetime.strptime(from_date, "%Y-%m-%d").timestamp()
        to_ts = datetime.strptime(to_date, "%Y-%m-%d").timestamp()
        return [m for m in messages if from_ts <= m['date'] <= to_ts]

    def advanced_menu(self):
        """Show advanced settings"""
        print("\nAdvanced Settings:")
        print("1. Clear message history")
        print("2. Reset session data")
        print("3. Back to main menu")
        choice = input("Select: ")
        
        if choice == "1":
            os.remove("data/copy_map.pkl")
            print("✅ Copy history cleared.")
        elif choice == "2":
            shutil.rmtree('tdlib-session')
            print("✅ Session data reset.")

    def clean_exit(self):
        """Graceful shutdown"""
        if self.monitoring:
            self.monitoring = False
            self.monitor_event.set()
        if self.tg:
            self.tg.stop()
        print("\n👋 Goodbye!")
        sys.exit(0)

if __name__ == "__main__":
    tc = TeleCopy()
    try:
        tc.show_menu()
    except KeyboardInterrupt:
        tc.clean_exit()
