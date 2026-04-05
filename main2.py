import os
import sys
import shutil
import json
import threading
import time
import re
from datetime import datetime
from dotenv import load_dotenv, set_key, find_dotenv
from telegram.client import Telegram
from tqdm import tqdm

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
            with open('data/last_message.json') as f:
                self.last_message_id = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
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
            with open("data/last_session_config.json") as f:
                last = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
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
        with open("data/last_session_config.json", "w") as f:
            json.dump({
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
            with open("data/copy_map.json") as f:
                return {int(k): v for k, v in json.load(f).items()}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_copy_map(self, data):
        """Save message ID mapping"""
        with open("data/copy_map.json", "w") as f:
            json.dump(data, f)

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

    def copy_message(self, src, dest, msg_id):
        """Forward a message from source to destination"""
        data = {
            'chat_id': dest,
            'from_chat_id': src,
            'message_ids': [msg_id],
            'send_copy': True
        }
        MAX_RETRIES = 5
        for attempt in range(MAX_RETRIES):
            try:
                result = self.tg.call_method('forwardMessages', data, block=True)
                if result.update["messages"] == [None]:
                    raise Exception(f"Message {msg_id} could not be copied")
                return result.update["messages"][0]["id"]
            except Exception as e:
                error_msg = str(e)
                match = re.search(r'flood_wait_(\d+)', error_msg)
                if match:
                    wait_time = int(match.group(1))
                    print(f"Rate limited by Telegram. Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                elif "FloodWait" in error_msg:
                    wait_time = 5 * (attempt + 1)
                    print(f"Rate limit hit. Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    print(f"Error forwarding message {msg_id}: {e}")
        else:
            print(f"Failed to copy message {msg_id} after {MAX_RETRIES} retries.")
        return None

    def get_messages(self, chat_id):
        """Fetch messages from a given chat"""
        messages = []
        last = self.last_message_id
        while True:
            try:
                result = self.tg.get_chat_history(chat_id, limit=100, from_message_id=last)
                result.wait()
                if not result.update["messages"]:
                    break
                messages.extend(result.update["messages"])
                last = result.update["messages"][-1]["id"]
            except Exception as e:
                print(f"Error fetching messages: {e}")
                break
        return messages

    def advanced_menu(self):
        """Show advanced settings"""
        print("\nAdvanced Settings:")
        print("1. Clear message history")
        print("2. Reset session data")
        print("3. Back to main menu")
        choice = input("Select: ")
        
        if choice == "1":
            try:
                os.remove("data/copy_map.json")
                print("✅ Copy history cleared.")
            except FileNotFoundError:
                print("No copy history found.")
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

    def show_menu(self):
        """Main menu for the program"""
        while True:
            print("""
========= TeleCopy =========
0. Connect to Telegram
1. Set Source and Destination Chats
2. Copy Full History
3. Copy Messages by Date Range
4. Advanced Settings
5. Exit
""")
            choice = input("Choose an option: ").strip()

            if choice == "0":
                self.handle_connection()
            elif choice == "1":
                self.set_chats()
            elif choice == "2":
                self.full_copy()
            elif choice == "3":
                self.date_copy()
            elif choice == "4":
                self.advanced_menu()
            elif choice == "5":
                self.clean_exit()
            else:
                print("Invalid choice. Please select again.")

if __name__ == "__main__":
    tc = TeleCopy()
    try:
        tc.show_menu()
    except KeyboardInterrupt:
        tc.clean_exit()
