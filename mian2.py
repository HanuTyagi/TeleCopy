import os
import sys
import subprocess
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

# Extended list of excluded message types
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
        self.load_config()

    def load_config(self):
        """Load or initialize configuration"""
        self.config_path = find_dotenv()
        load_dotenv(self.config_path)
        
        # Initialize message tracking
        os.makedirs('data', exist_ok=True)
        try:
            with open('data/last_message.pkl', 'rb') as f:
                self.last_message_id = pickle.load(f)
        except (FileNotFoundError, EOFError):
            self.last_message_id = 0

    # ... (Keep previous helper methods but enhance them with the following improvements)

    @on_exception(expo, Exception, max_tries=5)
    def copy_message(self, from_chat_id, to_chat_id, message_id):
        """Enhanced copy message with better error handling"""
        data = {
            'chat_id': to_chat_id,
            'from_chat_id': from_chat_id,
            'message_ids': [message_id],
            'send_copy': True,
            'options': {'ignore_content_type_restriction': True}
        }
        
        try:
            result = self.tg.call_method('forwardMessages', data, block=True)
            return result.update["messages"][0]["id"]
        except Exception as e:
            error_msg = str(e)
            if 'flood_wait' in error_msg:
                wait = int(re.search(r'flood_wait_(\d+)', error_msg).group(1))
                print(f"⏳ Flood wait: {wait} seconds")
                time.sleep(wait)
                raise
            elif 'MESSAGE_NOT_FOUND' in error_msg:
                print(f"⚠️ Message {message_id} not found - skipping")
                return None
            else:
                print(f"⚠️ Error copying message {message_id}: {error_msg}")
                raise

    def get_messages(self, chat_id, batch_size=100):
        """Improved message retrieval with batch processing"""
        messages = []
        from_id = 0
        with tqdm(desc="Fetching messages", unit="msg") as pbar:
            while True:
                result = self.tg.get_chat_history(
                    chat_id, 
                    limit=batch_size, 
                    from_message_id=from_id
                )
                result.wait()
                
                if not result.update["messages"]:
                    break
                
                messages.extend(result.update["messages"])
                from_id = messages[-1]["id"]
                pbar.update(len(result.update["messages"]))

                # Save progress every 1000 messages
                if len(messages) % 1000 == 0:
                    self._save_progress(messages)

        return messages

    def _save_progress(self, messages):
        """Save copy progress periodically"""
        if messages:
            self.last_message_id = messages[-1]["id"]
            with open('data/last_message.pkl', 'wb') as f:
                pickle.dump(self.last_message_id, f)

    def start_monitoring(self):
        """Real-time message monitoring with threading"""
        if not self.monitoring:
            self.monitoring = True
            self.monitor_event.clear()
            monitor_thread = threading.Thread(target=self._monitor_messages)
            monitor_thread.daemon = True
            monitor_thread.start()
            print("🚀 Started live monitoring (press Enter to stop)...")

    def _monitor_messages(self):
        """Background message monitoring"""
        src = int(os.getenv("SOURCE"))
        dst = int(os.getenv("DESTINATION"))
        
        while self.monitoring:
            try:
                result = self.tg.get_chat_history(src, limit=10)
                result.wait()
                
                for msg in reversed(result.update["messages"]):
                    if msg["id"] > self.last_message_id:
                        self.copy_message(src, dst, msg["id"])
                        self.last_message_id = msg["id"]
                        
                time.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                print(f"Monitoring error: {str(e)}")
                time.sleep(30)

    def validate_config(self):
        """Enhanced configuration validation"""
        errors = []
        api_id = os.getenv("API_ID")
        if not api_id or not api_id.isdigit():
            errors.append("API_ID must be a valid integer")
            
        api_hash = os.getenv("API_HASH")
        if not api_hash or len(api_hash) != 32:
            errors.append("API_HASH must be 32 characters")
            
        phone = os.getenv("PHONE")
        if not phone or not re.match(r'^\+?[1-9]\d{1,14}$', phone):
            errors.append("Invalid phone number format")
            
        return errors

    def interactive_setup(self):
        """Guided configuration setup with validation"""
        print("\n🔧 Interactive Setup 🔧")
        config = {
            'API_ID': ('Enter your API ID (my.telegram.org): ', r'^\d+$'),
            'API_HASH': ('Enter your API Hash: ', r'^[a-f0-9]{32}$'),
            'PHONE': ('Enter your phone number (+1234567890): ', r'^\+?[1-9]\d{1,14}$')
        }
        
        for key, (prompt, pattern) in config.items():
            while True:
                value = input(prompt).strip()
                if re.match(pattern, value):
                    set_key(self.config_path, key, value)
                    break
                print(f"❌ Invalid {key} format. Please try again.")
        
        print("✅ Configuration updated successfully!")
        self.load_config()

    def show_menu(self):
        """Enhanced menu system with status information"""
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            print("\n" + "="*40)
            print("TeleCopy - Enhanced Message Forwarding")
            print("="*40)
            print("[Status]")
            print(f"Connected: {'✅' if self.session_active else '❌'}")
            print(f"Monitoring: {'✅' if self.monitoring else '❌'}")
            print(f"Source Chat: {os.getenv('SOURCE', 'Not set')}")
            print(f"Destination Chat: {os.getenv('DESTINATION', 'Not set')}")
            print("\n[Menu]")
            print("1. Configure Telegram Connection")
            print("2. Set Source & Destination Chats")
            print("3. Full History Copy")
            print("4. Date-Range Copy")
            print("5. Start Live Monitoring")
            print("6. Stop Live Monitoring")
            print("7. Advanced Settings")
            print("8. Exit")
            
            choice = input("\nSelect an option: ").strip()
            
            if choice == '1':
                self.handle_connection()
            elif choice == '2':
                self.set_chats()
            elif choice == '3':
                self.full_copy()
            elif choice == '4':
                self.date_copy()
            elif choice == '5':
                self.start_monitoring()
            elif choice == '6':
                self.stop_monitoring()
            elif choice == '7':
                self.advanced_menu()
            elif choice == '8':
                self.clean_exit()
            else:
                print("⚠️ Invalid selection. Please try again.")
                time.sleep(1)

    # ... (Other methods with similar enhancements)

    def clean_exit(self):
        """Graceful shutdown procedure"""
        if self.monitoring:
            self.stop_monitoring()
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
