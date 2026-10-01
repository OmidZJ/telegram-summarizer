"""
Telegram Message & Group Reader
================================
A tool to read, export, and monitor messages from Telegram groups and channels
using your personal Telegram account via Telethon MTProto client.

Features:
- List all joined groups and channels
- Read and export recent messages from a specific group
- Batch export recent messages from ALL groups to JSON/TXT for summarization
- Real-time live monitor for incoming messages across groups
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat, User

# Base directory & exports directory
BASE_DIR = Path(__file__).resolve().parent
EXPORTS_DIR = BASE_DIR / "exports"
EXPORTS_DIR.mkdir(exist_ok=True)

# Load environment variables
load_dotenv(BASE_DIR / ".env")

API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_HASH") or os.getenv("TELEGRAM_API_HASH")
PHONE = os.getenv("TELEGRAM_PHONE")
SESSION_NAME = os.getenv("TELEGRAM_SESSION", str(BASE_DIR / "telegram_session"))

# Proxy configuration (optional)
PROXY_TYPE = os.getenv("PROXY_TYPE", "").lower()
PROXY_HOST = os.getenv("PROXY_HOST")
PROXY_PORT = os.getenv("PROXY_PORT")
PROXY_USER = os.getenv("PROXY_USERNAME")
PROXY_PASS = os.getenv("PROXY_PASSWORD")


def get_proxy():
    """Build proxy tuple for Telethon if configured in .env."""
    if not PROXY_HOST or not PROXY_PORT:
        return None
    try:
        import socks
        type_map = {
            "socks5": socks.SOCKS5,
            "socks4": socks.SOCKS4,
            "http": socks.HTTP,
        }
        proxy_type = type_map.get(PROXY_TYPE, socks.SOCKS5)
        port = int(PROXY_PORT)
        return (proxy_type, PROXY_HOST, port, True, PROXY_USER or None, PROXY_PASS or None)
    except ImportError:
        print("[!] PySocks is required for proxy support. Install it with: pip install PySocks")
        return None


def get_credentials():
    """Ensure API_ID and API_HASH are present or prompt user."""
    global API_ID, API_HASH, PHONE

    if not API_ID or not API_HASH:
        print("=" * 60)
        print(" Telegram API Credentials Required")
        print("=" * 60)
        print("To read messages with your Telegram account, you need an API ID & Hash.")
        print("1. Go to: https://my.telegram.org")
        print("2. Log in with your Telegram phone number.")
        print("3. Click 'API development tools'.")
        print("4. Create an app (any name) to get 'api_id' and 'api_hash'.")
        print("5. Save them in .env or enter them below:")
        print("=" * 60)

        if not API_ID:
            API_ID = input("Enter TELEGRAM_API_ID: ").strip()
        if not API_HASH:
            API_HASH = input("Enter TELEGRAM_API_HASH: ").strip()

    if not PHONE:
        PHONE = input("Enter your phone number (e.g. +1234567890): ").strip()

    try:
        API_ID = int(API_ID)
    except ValueError:
        print("[ERROR] API_ID must be an integer.")
        sys.exit(1)

    return API_ID, API_HASH, PHONE


def get_sender_name(sender):
    """Format sender display name."""
    if isinstance(sender, User):
        first = sender.first_name or ""
        last = sender.last_name or ""
        name = f"{first} {last}".strip()
        if sender.username:
            name += f" (@{sender.username})"
        return name or f"User_{sender.id}"
    elif isinstance(sender, (Channel, Chat)):
        return sender.title or f"Chat_{sender.id}"
    return "Unknown Sender"


def get_dialog_type(dialog):
    """Return string description of dialog type."""
    if dialog.is_user:
        return "Direct Message"
    if dialog.is_group:
        if isinstance(dialog.entity, Channel) and dialog.entity.megagroup:
            return "Supergroup"
        return "Group"
    if dialog.is_channel:
        return "Channel"
    return "Unknown"


async def fetch_groups(client):
    """Retrieve all groups and supergroups (optionally channels)."""
    groups = []
    print("\nFetching dialogs from Telegram...")
    async for dialog in client.iter_dialogs():
        if dialog.is_group:
            groups.append({
                "id": dialog.id,
                "title": dialog.name,
                "type": get_dialog_type(dialog),
                "unread_count": dialog.unread_count,
                "entity": dialog.entity,
            })
    return groups


async def list_groups(client):
    """Display all groups in a formatted list."""
    groups = await fetch_groups(client)
    if not groups:
        print("No groups found for this account.")
        return []

    print("\n" + "=" * 75)
    print(f"{'#':<4} {'Type':<12} {'Group Title':<35} {'Group ID':<15} {'Unread'}")
    print("-" * 75)
    for idx, grp in enumerate(groups, 1):
        print(f"{idx:<4} {grp['type']:<12} {grp['title'][:33]:<35} {grp['id']:<15} {grp['unread_count']}")
    print("=" * 75)
    print(f"Total groups found: {len(groups)}")
    return groups


async def read_group_messages(client, entity, limit=50):
    """Read recent messages from a specific group entity."""
    messages = []
    async for msg in client.iter_messages(entity, limit=limit):
        if not msg:
            continue
        
        sender = await msg.get_sender()
        sender_name = get_sender_name(sender)
        sender_id = msg.sender_id

        # Determine media type tag if message has media
        media_tag = ""
        if msg.media:
            media_type = type(msg.media).__name__
            media_tag = f"[{media_type}]"

        text = msg.text or msg.message or ""
        if not text and media_tag:
            text = media_tag

        messages.append({
            "message_id": msg.id,
            "date": msg.date.strftime("%Y-%m-%d %H:%M:%S") if msg.date else "",
            "timestamp": int(msg.date.timestamp()) if msg.date else 0,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "reply_to_msg_id": msg.reply_to_msg_id,
            "text": text,
            "media": media_tag,
        })

    # Return chronological order (oldest to newest)
    messages.reverse()
    return messages


def save_messages_export(group_title, group_id, messages):
    """Save messages to JSON and TXT format in exports/ folder."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c for c in group_title if c.isalnum() or c in (" ", "_", "-")).rstrip().replace(" ", "_")
    safe_title = safe_title[:30] or f"chat_{group_id}"

    json_path = EXPORTS_DIR / f"{safe_title}_{timestamp}.json"
    txt_path = EXPORTS_DIR / f"{safe_title}_{timestamp}.txt"

    payload = {
        "group_id": group_id,
        "group_title": group_title,
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_messages": len(messages),
        "messages": messages,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"Group: {group_title} (ID: {group_id})\n")
        f.write(f"Exported at: {payload['exported_at']}\n")
        f.write(f"Total messages: {len(messages)}\n")
        f.write("=" * 60 + "\n\n")
        for m in messages:
            f.write(f"[{m['date']}] {m['sender_name']}:\n")
            f.write(f"{m['text']}\n")
            f.write("-" * 40 + "\n")

    print(f"\n[+] Saved {len(messages)} messages to:")
    print(f"    - JSON: {json_path}")
    print(f"    - TXT:  {txt_path}")


def get_synced_chat_paths(group_id, group_title):
    """Get or create JSON and TXT paths for a synced group chat."""
    sync_dir = EXPORTS_DIR / "synced_chats"
    sync_dir.mkdir(exist_ok=True)

    # Check if a sync file already exists for this group ID
    for existing_file in sync_dir.glob(f"*_{group_id}.json"):
        txt_file = existing_file.with_suffix(".txt")
        return existing_file, txt_file

    safe_title = "".join(c for c in group_title if c.isalnum() or c in (" ", "_", "-")).rstrip().replace(" ", "_")
    safe_title = safe_title[:30] or f"chat_{group_id}"

    json_path = sync_dir / f"{safe_title}_{group_id}.json"
    txt_path = sync_dir / f"{safe_title}_{group_id}.txt"
    return json_path, txt_path


def load_synced_chat(json_path):
    """Load existing synced chat metadata and messages from JSON."""
    if not json_path.exists():
        return {
            "group_id": None,
            "group_title": "",
            "group_type": "",
            "first_synced_at": "",
            "last_synced_at": "",
            "last_message_id": 0,
            "total_messages": 0,
            "messages": [],
        }

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure required keys exist
            data.setdefault("messages", [])
            data.setdefault("last_message_id", 0)
            data.setdefault("total_messages", len(data["messages"]))
            return data
    except Exception as e:
        print(f"[!] Warning: Could not read existing file {json_path}: {e}")
        return {
            "group_id": None,
            "group_title": "",
            "group_type": "",
            "first_synced_at": "",
            "last_synced_at": "",
            "last_message_id": 0,
            "total_messages": 0,
            "messages": [],
        }


def save_synced_chat(json_path, txt_path, chat_data):
    """Save updated synced chat data to JSON and formatted TXT files."""
    chat_data["total_messages"] = len(chat_data["messages"])
    chat_data["last_synced_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if chat_data["messages"]:
        chat_data["last_message_id"] = max(m["message_id"] for m in chat_data["messages"])

    # Save JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(chat_data, f, ensure_ascii=False, indent=2)

    # Save TXT
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write(f" Group Chat Archive: {chat_data.get('group_title', 'Unknown')} (ID: {chat_data.get('group_id', '')})\n")
        f.write(f" Type: {chat_data.get('group_type', 'Group')} | Total Messages: {chat_data['total_messages']}\n")
        f.write(f" First Synced: {chat_data.get('first_synced_at', '')} | Last Updated: {chat_data['last_synced_at']}\n")
        f.write(f" Highest Message ID: {chat_data.get('last_message_id', 0)}\n")
        f.write("=" * 70 + "\n\n")

        for m in chat_data["messages"]:
            reply_str = f" [In reply to #{m['reply_to_msg_id']}]" if m.get("reply_to_msg_id") else ""
            f.write(f"[{m['date']}] {m['sender_name']} (ID: #{m['message_id']}){reply_str}:\n")
            f.write(f"{m['text']}\n")
            f.write("-" * 50 + "\n")


async def handle_sync_group_chat(client):
    """
    Export all chat messages of a selected group, auto-resuming from the
    last stored message on every subsequent run.
    """
    groups = await fetch_groups(client)
    if not groups:
        print("No groups found for this account.")
        return

    # Scan existing synced files to show sync status in menu
    sync_dir = EXPORTS_DIR / "synced_chats"
    sync_dir.mkdir(exist_ok=True)

    print("\n" + "=" * 80)
    print(f"{'#':<4} {'Type':<12} {'Group Title':<32} {'Group ID':<15} {'Sync Status'}")
    print("-" * 80)

    for idx, grp in enumerate(groups, 1):
        # Check if synced file exists
        matches = list(sync_dir.glob(f"*_{grp['id']}.json"))
        status = "Not synced"
        if matches:
            try:
                with open(matches[0], "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    count = meta.get("total_messages", len(meta.get("messages", [])))
                    status = f"Synced ({count} msgs)"
            except Exception:
                status = "Synced (exists)"

        print(f"{idx:<4} {grp['type']:<12} {grp['title'][:30]:<32} {grp['id']:<15} {status}")

    print("=" * 80)
    choice = input("\nEnter group # or Group ID to sync (or 0 to cancel): ").strip()
    if choice in ("0", ""):
        return

    selected = None
    if choice.isdigit() and 1 <= int(choice) <= len(groups):
        selected = groups[int(choice) - 1]
    else:
        for g in groups:
            if str(g["id"]) == choice or g["title"].lower() == choice.lower():
                selected = g
                break

    if not selected:
        print("[!] Group not found.")
        return

    group_id = selected["id"]
    group_title = selected["title"]
    group_type = selected["type"]

    json_path, txt_path = get_synced_chat_paths(group_id, group_title)
    chat_data = load_synced_chat(json_path)

    # Initialize metadata if first time
    if not chat_data.get("first_synced_at"):
        chat_data["first_synced_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    chat_data["group_id"] = group_id
    chat_data["group_title"] = group_title
    chat_data["group_type"] = group_type

    existing_count = len(chat_data["messages"])
    last_id = chat_data.get("last_message_id", 0)

    # If messages exist, verify highest message id
    if existing_count > 0:
        actual_highest = max(m["message_id"] for m in chat_data["messages"])
        last_id = max(last_id, actual_highest)
        chat_data["last_message_id"] = last_id

    print("\n" + "=" * 60)
    print(f" Syncing Chat for: '{group_title}' (ID: {group_id})")
    if existing_count > 0:
        print(f" Current archive: {existing_count} messages already stored.")
        print(f" Last stored Message ID: {last_id}")
        print(f" -> Will resume and fetch ONLY new messages (ID > {last_id}).")
    else:
        print(" No previous archive found.")
        print(" -> Will fetch full chat history from the beginning.")
    print("=" * 60)

    limit_prompt = input("Limit number of new messages to fetch (press Enter for ALL / no limit): ").strip()
    fetch_limit = int(limit_prompt) if limit_prompt.isdigit() and int(limit_prompt) > 0 else None

    print("\nFetching messages... (Press Ctrl+C anytime to stop and save progress)")

    new_messages = []
    chunk_counter = 0

    try:
        # In Telethon:
        # min_id: only messages with ID > min_id
        # reverse=True: yields in chronological order (oldest to newest)
        kwargs = {"reverse": True}
        if last_id > 0:
            kwargs["min_id"] = last_id
        if fetch_limit:
            kwargs["limit"] = fetch_limit

        async for msg in client.iter_messages(selected["entity"], **kwargs):
            if not msg:
                continue

            sender = await msg.get_sender()
            sender_name = get_sender_name(sender)
            sender_id = msg.sender_id

            media_tag = ""
            if msg.media:
                media_tag = f"[{type(msg.media).__name__}]"

            text = msg.text or msg.message or ""
            if not text and media_tag:
                text = media_tag
            elif not text and msg.action:
                text = f"[Action: {type(msg.action).__name__}]"

            msg_entry = {
                "message_id": msg.id,
                "date": msg.date.strftime("%Y-%m-%d %H:%M:%S") if msg.date else "",
                "timestamp": int(msg.date.timestamp()) if msg.date else 0,
                "sender_id": sender_id,
                "sender_name": sender_name,
                "reply_to_msg_id": msg.reply_to_msg_id,
                "text": text,
                "media": media_tag,
            }

            new_messages.append(msg_entry)
            chunk_counter += 1

            if chunk_counter % 50 == 0:
                print(f"[+] Fetched {len(new_messages)} new messages... (latest ID: {msg.id})")

            # Intermediate save every 500 messages to prevent any data loss
            if chunk_counter % 500 == 0:
                temp_data = dict(chat_data)
                temp_data["messages"] = chat_data["messages"] + new_messages
                save_synced_chat(json_path, txt_path, temp_data)

    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n\n[!] Interrupted by user. Saving messages fetched so far...")
    except Exception as e:
        print(f"\n[!] Error during sync: {e}")

    # Merge new messages with existing messages
    if new_messages:
        # Build set of existing IDs to guarantee no duplicates
        existing_ids = {m["message_id"] for m in chat_data["messages"]}
        added_count = 0
        for m in new_messages:
            if m["message_id"] not in existing_ids:
                chat_data["messages"].append(m)
                existing_ids.add(m["message_id"])
                added_count += 1

        # Sort all messages by message_id to maintain strict chronological order
        chat_data["messages"].sort(key=lambda x: x["message_id"])
        save_synced_chat(json_path, txt_path, chat_data)

        print("\n" + "=" * 60)
        print(" [+] SYNC COMPLETED SUCCESSFULLY!")
        print(f" -> New messages added in this run: {added_count}")
        print(f" -> Total messages in archive:       {len(chat_data['messages'])}")
        print(f" -> Highest Message ID stored:       {chat_data['last_message_id']}")
        print(f" -> Saved to JSON: {json_path}")
        print(f" -> Saved to TXT:  {txt_path}")
        print("=" * 60)
    else:
        if existing_count > 0:
            print("\n[*] Archive is already up to date! No new messages since last sync.")
        else:
            print("\n[*] No messages found in this group.")


async def handle_read_single_group(client):
    """Interactive flow to select a group and read/export recent messages."""
    groups = await list_groups(client)
    if not groups:
        return

    choice = input("\nEnter group # or Group ID to read (or 0 to cancel): ").strip()
    if choice in ("0", ""):
        return

    selected = None
    if choice.isdigit() and 1 <= int(choice) <= len(groups):
        selected = groups[int(choice) - 1]
    else:
        for g in groups:
            if str(g["id"]) == choice or g["title"].lower() == choice.lower():
                selected = g
                break

    if not selected:
        print("[!] Group not found.")
        return

    limit_input = input("How many recent messages to fetch? (default 50): ").strip()
    limit = int(limit_input) if limit_input.isdigit() and int(limit_input) > 0 else 50

    print(f"\nFetching last {limit} messages from '{selected['title']}'...")
    try:
        messages = await read_group_messages(client, selected["entity"], limit=limit)
    except Exception as e:
        print(f"[!] Error reading messages: {e}")
        return

    if not messages:
        print("No messages found in this group.")
        return

    print("\n" + "=" * 60)
    print(f" Previewing last {min(10, len(messages))} messages (out of {len(messages)}):")
    print("=" * 60)
    for m in messages[-10:]:
        print(f"[{m['date']}] {m['sender_name']}:")
        clean_text = m['text'].replace('\n', ' ')
        print(f"  {clean_text[:120]}{'...' if len(clean_text) > 120 else ''}")
    print("=" * 60)

    save_messages_export(selected["title"], selected["id"], messages)


async def handle_batch_export_all(client):
    """Batch export messages from all joined groups."""
    groups = await fetch_groups(client)
    if not groups:
        print("No groups found.")
        return

    print(f"\nFound {len(groups)} groups.")
    limit_input = input("How many messages to fetch per group? (default 30): ").strip()
    limit = int(limit_input) if limit_input.isdigit() and int(limit_input) > 0 else 30

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_json_path = EXPORTS_DIR / f"all_groups_batch_{timestamp}.json"
    batch_txt_path = EXPORTS_DIR / f"all_groups_batch_{timestamp}.txt"

    all_data = []
    print("\nStarting batch export...")

    with open(batch_txt_path, "w", encoding="utf-8") as txt_file:
        txt_file.write(f"Telegram Batch Export - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        txt_file.write(f"Total Groups: {len(groups)} | Limit per group: {limit}\n")
        txt_file.write("=" * 70 + "\n\n")

        for idx, grp in enumerate(groups, 1):
            title = grp["title"]
            print(f"[{idx}/{len(groups)}] Fetching '{title}'...", end=" ", flush=True)
            try:
                msgs = await read_group_messages(client, grp["entity"], limit=limit)
                print(f"Done ({len(msgs)} messages)")

                grp_payload = {
                    "group_id": grp["id"],
                    "group_title": title,
                    "group_type": grp["type"],
                    "message_count": len(msgs),
                    "messages": msgs,
                }
                all_data.append(grp_payload)

                txt_file.write(f"### GROUP: {title} (ID: {grp['id']})\n")
                txt_file.write(f"Type: {grp['type']} | Messages: {len(msgs)}\n")
                txt_file.write("-" * 50 + "\n")
                for m in msgs:
                    txt_file.write(f"[{m['date']}] {m['sender_name']}: {m['text']}\n")
                txt_file.write("\n" + "=" * 70 + "\n\n")

            except Exception as e:
                print(f"Failed ({e})")

    with open(batch_json_path, "w", encoding="utf-8") as f:
        json.dump({
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "groups_count": len(all_data),
            "data": all_data,
        }, f, ensure_ascii=False, indent=2)

    print("\n[+] Batch export complete!")
    print(f"    - JSON: {batch_json_path}")
    print(f"    - TXT:  {batch_txt_path}")


async def handle_live_monitor(client):
    """Listen for incoming messages in real-time across all groups."""
    print("\n" + "=" * 60)
    print(" LIVE TELEGRAM GROUP MONITOR ACTIVE")
    print(" Listening for new incoming messages across all groups...")
    print(" Press Ctrl+C anytime to stop monitoring and return to menu.")
    print("=" * 60 + "\n")

    live_log_path = EXPORTS_DIR / "realtime_live_log.txt"

    @client.on(events.NewMessage)
    async def incoming_handler(event):
        # Filter for groups / supergroups
        if not event.is_group:
            return

        chat = await event.get_chat()
        sender = await event.get_sender()
        chat_title = getattr(chat, "title", f"Chat_{chat.id}")
        sender_name = get_sender_name(sender)
        date_str = event.date.strftime("%Y-%m-%d %H:%M:%S") if event.date else ""
        text = event.text or event.message.message or ""

        if not text and event.media:
            text = f"[{type(event.media).__name__}]"

        log_line = f"[{date_str}] [{chat_title}] {sender_name}:\n  {text}\n"
        print(log_line)

        # Append to live log
        try:
            with open(live_log_path, "a", encoding="utf-8") as f:
                f.write(log_line + "-" * 50 + "\n")
        except Exception:
            pass

    try:
        # Run until user interrupts with Ctrl+C
        while True:
            await asyncio.sleep(1)
    except (asyncio.CancelledError, KeyboardInterrupt):
        print("\nStopping live monitor...")
    finally:
        client.remove_event_handler(incoming_handler)
        print("[*] Live monitor stopped. Returning to menu.\n")


async def main_menu(client):
    """Display interactive menu options."""
    while True:
        print("\n" + "=" * 55)
        print(" Telegram Account Reader & Group Summarizer")
        print("=" * 55)
        print("1. List all joined groups & channels")
        print("2. Sync / Export FULL group chat (auto-resume new messages)")
        print("3. Quick export recent messages from a group (custom limit)")
        print("4. Batch export recent messages from ALL groups")
        print("5. Start real-time live group message monitor")
        print("6. Exit")
        print("=" * 55)

        choice = input("Select an option (1-6): ").strip()

        if choice == "1":
            await list_groups(client)
        elif choice == "2":
            await handle_sync_group_chat(client)
        elif choice == "3":
            await handle_read_single_group(client)
        elif choice == "4":
            await handle_batch_export_all(client)
        elif choice == "5":
            await handle_live_monitor(client)
        elif choice == "6":
            print("\nExiting. Goodbye!")
            break
        else:
            print("[!] Invalid choice. Please enter a number between 1 and 6.")


async def main():
    api_id, api_hash, phone = get_credentials()
    proxy = get_proxy()

    print("\nConnecting to Telegram...")
    client = TelegramClient(SESSION_NAME, api_id, api_hash, proxy=proxy)

    try:
        # start() prompts for code / 2FA in terminal if logging in for the first time
        await client.start(phone=phone)
        me = await client.get_me()
        print(f"\n[+] Successfully logged in as: {me.first_name} (@{me.username or 'No Username'}) [ID: {me.id}]")
        
        await main_menu(client)
    except KeyboardInterrupt:
        print("\nProgram interrupted by user.")
    except Exception as e:
        print(f"\n[!] Unexpected error: {e}")
    finally:
        if client.is_connected():
            await client.disconnect()
            print("[*] Disconnected from Telegram.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExited.")
