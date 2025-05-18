import os
import json
import time
import shutil
import datetime
from telethon import TelegramClient, events, sync
from telethon.tl.types import MessageMediaPoll
from telethon.tl.functions.messages import GetHistoryRequest

# Helper function to load environment variables from a file
def load_env(filename):
    if not os.path.exists(filename):
        return
    with open(filename, 'r') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, val = line.strip().split('=', 1)
                os.environ[key] = val

# Helper function to get a valid integer input
def get_valid_int(prompt):
    while True:
        val = input(prompt).strip()
        if val.isdigit():
            return int(val)
        print("Invalid input. Please enter a valid number.")

# Helper function to create a new .env file
def create_env_file(filename):
    print("Creating new .env file...")
    api_id = get_valid_int("Enter your API ID: ")
    api_hash = input("Enter your API Hash: ").strip()
    session_name = input("Enter your session name: ").strip()

    with open(filename, 'w') as f:
        f.write(f"API_ID={api_id}\n")
        f.write(f"API_HASH={api_hash}\n")
        f.write(f"SESSION_NAME={session_name}\n")

# Helper function to reset credentials
def reset_credentials():
    backup = ".env.backup"
    if os.path.exists(".env"):
        shutil.copy(".env", backup)
    os.remove(".env")
    create_env_file(".env")
    print("Credentials reset. Please restart the script.")

# Load or create .env file
if not os.path.exists(".env"):
    create_env_file(".env")

load_env(".env")

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME")

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
client.start()

# Global state
copied_message_ids = set()

# Helper function to choose chat
async def choose_chat():
    dialogs = await client.get_dialogs()
    print("\nAvailable chats:")
    for i, dialog in enumerate(dialogs):
        name = dialog.name or dialog.entity.username or str(dialog.id)
        print(f"{i+1}. {name}")
    index = get_valid_int("\nSelect a chat by number: ") - 1
    return dialogs[index].entity

# Helper to check if a message is a poll
def is_poll(message):
    return isinstance(message.media, MessageMediaPoll)

# Helper to export messages
async def export_messages(entity, messages, filename):
    data = []
    for message in messages:
        if message.id in copied_message_ids:
            continue
        copied_message_ids.add(message.id)

        if message.media and not is_poll(message):
            file_path = await message.download_media()
            data.append({"id": message.id, "text": message.text, "file": file_path})
        elif is_poll(message):
            data.append({"id": message.id, "poll": message.media.poll.question})
        else:
            data.append({"id": message.id, "text": message.text})

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Exported {len(data)} messages to {filename}")

# Helper to import messages
async def import_messages(target, filename):
    if not os.path.exists(filename):
        print("File not found.")
        return

    with open(filename, 'r', encoding='utf-8') as f:
        messages = json.load(f)

    for msg in messages:
        if "file" in msg:
            await client.send_file(target, msg["file"], caption=msg.get("text", ""))
        elif "poll" in msg:
            print("Skipping poll message.")
        else:
            await client.send_message(target, msg.get("text", ""))
        time.sleep(0.5)

    print(f"Imported {len(messages)} messages to {target.title}")

# Helper to copy messages in date range
async def copy_messages_by_date(source, target):
    from_date = datetime.datetime.strptime(input("Enter FROM date (YYYY-MM-DD): "), "%Y-%m-%d")
    to_date = datetime.datetime.strptime(input("Enter TO date (YYYY-MM-DD): "), "%Y-%m-%d")
    all_messages = []
    offset_id = 0
    limit = 100

    while True:
        history = await client(GetHistoryRequest(
            peer=source,
            offset_id=offset_id,
            offset_date=None,
            add_offset=0,
            limit=limit,
            max_id=0,
            min_id=0,
            hash=0
        ))
        messages = history.messages
        if not messages:
            break

        for msg in messages:
            if msg.date.replace(tzinfo=None) < from_date:
                break
            if from_date <= msg.date.replace(tzinfo=None) <= to_date:
                all_messages.append(msg)

        offset_id = messages[-1].id
        if messages[-1].date.replace(tzinfo=None) < from_date:
            break

    await export_messages(source, all_messages, "temp_messages.json")
    await import_messages(target, "temp_messages.json")
    os.remove("temp_messages.json")

# Live monitor
async def live_monitor(source, target):
    @client.on(events.NewMessage(chats=source))
    async def handler(event):
        message = event.message
        if message.id in copied_message_ids:
            return
        copied_message_ids.add(message.id)
        if message.media and not is_poll(message):
            file_path = await message.download_media()
            await client.send_file(target, file_path, caption=message.text)
        elif is_poll(message):
            print("Skipping poll message.")
        else:
            await client.send_message(target, message.text)

    print("Live monitoring started. Press Ctrl+C to stop.")
    await client.run_until_disconnected()

# Main menu
async def main():
    while True:
        print("\nMain Menu")
        print("1. Connect to Telegram")
        print("2. Reset credentials")
        print("3. Copy messages between chats")
        print("4. Copy messages in date range")
        print("5. Live monitor messages")
        print("6. Exit")
        choice = input("Choose an option: ").strip()

        if choice == '1':
            print("Connected.")
        elif choice == '2':
            reset_credentials()
            break
        elif choice == '3':
            print("Select source chat:")
            source = await choose_chat()
            print("Select target chat:")
            target = await choose_chat()
            all_msgs = await client.get_messages(source, limit=200)
            await export_messages(source, all_msgs, "temp_messages.json")
            await import_messages(target, "temp_messages.json")
            os.remove("temp_messages.json")
        elif choice == '4':
            print("Select source chat:")
            source = await choose_chat()
            print("Select target chat:")
            target = await choose_chat()
            await copy_messages_by_date(source, target)
        elif choice == '5':
            print("Select source chat:")
            source = await choose_chat()
            print("Select target chat:")
            target = await choose_chat()
            await live_monitor(source, target)
        elif choice == '6':
            break
        else:
            print("Invalid choice.")

if __name__ == '__main__':
    with client:
        client.loop.run_until_complete(main())
  
