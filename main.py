import os
import sys
import subprocess
import shutil
import pickle
import threading
import time
from datetime import datetime
from dotenv import load_dotenv, set_key, find_dotenv
from telegram.client import Telegram

load_dotenv(find_dotenv())
ENV_PATH = find_dotenv()

EXCLUDE_TYPES = [
    "messageChatChangePhoto", 
    "messageChatChangeTitle", 
    "messageBasicGroupChatCreate",
    "messageChatDeleteMember",
    "messageChatAddMembers",
]

def check_env_vars():
    required = [ "PHONE", "API_ID", "API_HASH"]
    missing = [var for var in required if not os.getenv(var)]
    if missing:
        print(f"Missing env values: {missing}")
        for var in missing:
            value = input(f"Enter value for {var}: ")
            set_key(ENV_PATH, var, value)
        print("✅ .env updated.")
        load_dotenv(ENV_PATH)
        print("Restart TeleCopy")
        exit()


def initialize_telegram():
    return Telegram(
        api_id=os.getenv("API_ID"),
        api_hash=os.getenv("API_HASH"),
        phone=os.getenv("PHONE"),
        database_encryption_key=os.getenv("DB_PASSWORD"),
        files_directory=os.getenv("FILES_DIRECTORY"),
        proxy_server=os.getenv("PROXY_SERVER"),
        proxy_port=os.getenv("PROXY_PORT"),
        proxy_type={"@type": os.getenv("PROXY_TYPE")} if os.getenv("PROXY_TYPE") else None,
    )

def update_config():
    current = {
        "PHONE": os.getenv("PHONE", "Not Set"),
        "API_ID": os.getenv("API_ID", "Not Set"),
        "API_HASH": os.getenv("API_HASH", "Not Set")
    }
    print("\nCurrent Configuration:")
    for idx, (key, val) in enumerate(current.items(), start=1):
        print(f"{idx}. {key}: {val}")
    choice = -1
    print("0. Return to main menu")
    while choice!=0:
        choice = input("Select which one to update (1-3): ").strip()
        if choice == "0":
            python = sys.executable
            os.execl(python, python, *sys.argv)
        keys = list(current.keys())
        try:
            key = keys[int(choice) - 1]
            new_val = input(f"Enter new value for {key}: ").strip()
            set_key(ENV_PATH, key, new_val)
            print(f"✅ {key} updated.")
            print("🔁 Please restart the script to apply the new configuration(s).")
        except (IndexError, ValueError):
            print("❌ Invalid selection.")

def list_chats(tg):
    result = tg.get_chats()
    result.wait()
    chats = result.update['chat_ids']
    print("\nAvailable Chats:")
    for chat_id in chats:
        r = tg.get_chat(chat_id)
        r.wait()
        title = r.update.get('title', 'Private Chat')
        print(f"Chat ID: {chat_id}, Title: {title}")

def set_source_and_destination(tg):
    list_chats(tg)
    source = input("Enter source chat ID: ")
    dest = input("Enter destination chat ID: ")
    set_key(ENV_PATH, "SOURCE", source)
    set_key(ENV_PATH, "DESTINATION", dest)
    print("✅ Source and Destination updated.")

def copy_message(tg, from_chat_id, to_chat_id, message_id):
    data = {
        'chat_id': to_chat_id,
        'from_chat_id': from_chat_id,
        'message_ids': [message_id],
        'send_copy': True,
    }
    result = tg.call_method('forwardMessages', data, block=True)
    return result

def get_all_messages(tg, chat_id):
    messages = []
    last = 0
    while True:
        r = tg.get_chat_history(chat_id, limit=100, from_message_id=last)
        r.wait()
        if not r.update["messages"]:
            break
        messages.extend(r.update["messages"])
        last = r.update["messages"][-1]["id"]
    return messages

def filter_messages_by_date(messages, from_date=None, to_date=None):
    def to_timestamp(date_str):
        return int(datetime.strptime(date_str, "%Y-%m-%d").timestamp()) if date_str else None

    from_ts = to_timestamp(from_date)
    to_ts = to_timestamp(to_date)

    filtered = []
    for m in messages:
        msg_ts = m["date"]
        if ((from_ts is None or msg_ts >= from_ts) and
            (to_ts is None or msg_ts <= to_ts)):
            if m["content"]["@type"] not in EXCLUDE_TYPES:
                filtered.append(m)
    return filtered

def custom_copy_messages(tg):
    try:
        with open("message/message_copy_dict.pickle", "rb") as f:
            copied = pickle.load(f)
    except OSError:
        copied = {}

    src = os.getenv("SOURCE")
    dst = os.getenv("DESTINATION")
    if not src or not dst:
        print("⚠️ SOURCE and DESTINATION must be set first. Please choose option 1 from the menu.")
        return
    src = int(src)
    dst = int(dst)

    print("Enter the date range for copying messages:")
    from_date = input("From date (YYYY-MM-DD) [leave empty to copy from start]: ").strip()
    to_date = input("To date (YYYY-MM-DD) [leave empty to copy till latest]: ").strip()

    all_messages = get_all_messages(tg, src)
    messages_to_copy = filter_messages_by_date(all_messages, from_date, to_date)

    print(f"Copying {len(messages_to_copy)} messages from {from_date or 'beginning'} to {to_date or 'latest'}...")
    for m in reversed(messages_to_copy):
        mid = m["id"]
        if mid in copied:
            continue
        try:
            result = copy_message(tg, src, dst, mid)
            new_id = result.update["messages"][0]["id"]
            copied[mid] = new_id
            print(f"Copied {mid} -> {new_id}")
        except Exception as e:
            print(f"Error copying message {mid}: {e}")
            continue

    os.makedirs("data", exist_ok=True)
    with open("message/message_copy_dict.pickle", "wb") as f:
        pickle.dump(copied, f)

    print("✅ Custom copy complete.")

def show_menu():
    tg = None
    session_active = False

    while True:
        os.system("clear" if os.name == "posix" else "cls")
        print(r"""
 _________  _______   ___       _______   ________  ________  ________  ___    ___ 
|\___   ___\\  ___ \ |\  \     |\  ___ \ |\   ____\|\   __  \|\   __  \|\  \  /  /|
\|___ \  \_\ \   __/|\ \  \    \ \   __/|\ \  \___|\ \  \|\  \ \  \|\  \ \  \/  / /
     \ \  \ \ \  \_|/_\ \  \    \ \  \_|/_\ \  \    \ \  \\\  \ \   ____\ \    / / 
      \ \  \ \ \  \_|\ \ \  \____\ \  \_|\ \ \  \____\ \  \\\  \ \  \___|\/  /  /  
       \ \__\ \ \_______\ \_______\ \_______\ \_______\ \_______\ \__\ __/  / /    
        \|__|  \|___@H__|\|___AN__|\|___UT__|\|__YA___|\|___GI____|\|__||\___/ /     
                                                                      \|___|/      
========= TeleCopy Coded By HanuTyagi =========""")
        print("0. Connect to Telegram")
        print("1. Select source and destination")
        print("2. Copy Past Messages (Full Clone)")
        print("3. Start live monitoring (Auto-Forward)")
        print("4. Custom Clone (by date)")
        print("5. Update API ID, Hash, Phone")
        print("6. Exit")

        choice = input("Choose an option: ").strip()

        if choice == "0":
            check_env_vars()
            new_api_id = os.getenv("API_ID")
            new_api_hash = os.getenv("API_HASH")
            new_phone = os.getenv("PHONE")

            try:
                with open("data/last_session_config.pickle", "rb") as f:
                    last = pickle.load(f)
            except FileNotFoundError:
                last = {}

            if (last.get("API_ID") != new_api_id or
                last.get("API_HASH") != new_api_hash or
                last.get("PHONE") != new_phone):
                print("🔁 Detected config change – resetting session...")
                try:
                    shutil.rmtree('data')
                except (FileNotFoundError):
                    print("No Last Session Config Found")

            os.makedirs("data", exist_ok=True)
            with open("data/last_session_config.pickle", "wb") as f:
                pickle.dump({
                    "API_ID": new_api_id,
                    "API_HASH": new_api_hash,
                    "PHONE": new_phone
                }, f)


            tg = initialize_telegram()
            tg.login()
            session_active = True
            print("✅ Connected to Telegram.")
            time.sleep(2)

        elif choice == "5":
            update_config()
        elif choice == "6":
            print("👋 Goodbye!")
            break

        elif not session_active:
            print("❌ Please connect to Telegram first using option 0.")
        
        elif choice == "1":
            set_source_and_destination(tg)
        elif choice == "2":
            copy_past_messages(tg)
        elif choice == "3":
            monitor_live(tg)
        elif choice == "4":
            custom_copy_messages(tg)
        else:
            print("❌ Invalid choice.")

if __name__ == "__main__":
    show_menu()
