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


ACCOUNTS_FILE = BASE_DIR / "telegram_accounts.json"


class AccountManager:
    """
    Manages multiple Telegram accounts, session switching, and logouts.
    Stores metadata in telegram_accounts.json while keeping sessions in separate .session files.
    """

    def __init__(self):
        self.accounts_file = ACCOUNTS_FILE
        self.data = self._load_data()

    def _load_data(self) -> dict:
        if self.accounts_file.exists():
            try:
                with open(self.accounts_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "accounts" in data and data["accounts"]:
                        return data
            except Exception as e:
                print(f"[!] Warning reading accounts file: {e}")

        # Default initial structure (Account 1 and Account 2)
        default_api_id = API_ID
        try:
            default_api_id = int(default_api_id) if default_api_id else None
        except Exception:
            default_api_id = None

        default_api_hash = API_HASH
        default_phone = PHONE or ""

        initial_data = {
            "active_account_id": "account_1",
            "accounts": {
                "account_1": {
                    "id": "account_1",
                    "name": "Account 1",
                    "session_name": "telegram_session",
                    "phone": default_phone,
                    "api_id": default_api_id,
                    "api_hash": default_api_hash,
                    "user_title": "",
                },
                "account_2": {
                    "id": "account_2",
                    "name": "Account 2",
                    "session_name": "telegram_session_account2",
                    "phone": os.getenv("TELEGRAM_PHONE_2", ""),
                    "api_id": default_api_id,
                    "api_hash": default_api_hash,
                    "user_title": "",
                },
            },
        }
        self._write_data(initial_data)
        return initial_data

    def _write_data(self, data: dict):
        try:
            with open(self.accounts_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[!] Error saving accounts file: {e}")

    def save(self):
        self._write_data(self.data)

    @property
    def active_account_id(self) -> str:
        return self.data.get("active_account_id", "account_1")

    def get_active_account(self) -> dict:
        acc_id = self.active_account_id
        accounts = self.data.get("accounts", {})
        if acc_id not in accounts:
            first_id = next(iter(accounts.keys()), "account_1")
            self.data["active_account_id"] = first_id
            self.save()
            acc_id = first_id
        return accounts[acc_id]

    def set_active_account(self, account_id: str) -> bool:
        if account_id in self.data.get("accounts", {}):
            self.data["active_account_id"] = account_id
            self.save()
            return True
        return False

    def get_all_accounts(self) -> dict:
        return self.data.get("accounts", {})

    def add_account(self, name: str, phone: str = "", api_id=None, api_hash=None) -> dict:
        accounts = self.data.setdefault("accounts", {})
        count = len(accounts) + 1
        new_id = f"account_{count}"
        while new_id in accounts:
            count += 1
            new_id = f"account_{count}"

        session_name = f"telegram_session_{new_id}"
        acc_dict = {
            "id": new_id,
            "name": name.strip() or f"Account {count}",
            "session_name": session_name,
            "phone": phone.strip(),
            "api_id": api_id or API_ID,
            "api_hash": api_hash or API_HASH,
            "user_title": "",
        }
        accounts[new_id] = acc_dict
        self.save()
        return acc_dict

    def rename_account(self, account_id: str, new_name: str) -> bool:
        acc = self.data.get("accounts", {}).get(account_id)
        if acc and new_name.strip():
            acc["name"] = new_name.strip()
            self.save()
            return True
        return False

    def delete_account(self, account_id: str) -> bool:
        accounts = self.data.get("accounts", {})
        if len(accounts) <= 1:
            print("[!] Cannot delete the only remaining account. At least 1 account is required.")
            return False

        if account_id not in accounts:
            return False

        acc = accounts[account_id]
        session_base = BASE_DIR / acc["session_name"]
        for ext in (".session", ".session-journal"):
            sf = Path(f"{session_base}{ext}")
            if sf.exists():
                try:
                    sf.unlink()
                except Exception:
                    pass

        del accounts[account_id]

        if self.active_account_id == account_id:
            self.data["active_account_id"] = next(iter(accounts.keys()))

        self.save()
        return True

    async def logout_account(self, client, account_id: str) -> bool:
        acc = self.data.get("accounts", {}).get(account_id)
        if not acc:
            return False

        if client and client.is_connected():
            try:
                if await client.is_user_authorized():
                    await client.log_out()
                    print(f"[✓] Terminated Telegram authorization on servers.")
            except Exception as e:
                print(f"[!] Warning during server log_out: {e}")
            try:
                await client.disconnect()
            except Exception:
                pass

        await asyncio.sleep(0.5)

        session_base = BASE_DIR / acc["session_name"]
        for ext in (".session", ".session-journal"):
            sf = Path(f"{session_base}{ext}")
            if sf.exists():
                try:
                    sf.unlink()
                    print(f"[✓] Removed local session file: {sf.name}")
                except Exception as e:
                    try:
                        await asyncio.sleep(0.5)
                        sf.unlink()
                        print(f"[✓] Removed local session file: {sf.name}")
                    except Exception:
                        print(f"[!] Warning deleting {sf.name}: {e}")

        acc["user_title"] = ""
        acc["phone"] = ""
        self.save()
        return True

    async def connect_active_account(self, proxy=None):
        acc = self.get_active_account()
        session_path = str(BASE_DIR / acc["session_name"])

        api_id = acc.get("api_id") or API_ID
        api_hash = acc.get("api_hash") or API_HASH
        phone = acc.get("phone") or PHONE

        if not api_id or not api_hash:
            print(f"\n[!] Telegram API Credentials required for '{acc['name']}'.")
            if not api_id:
                raw_id = input("Enter TELEGRAM_API_ID: ").strip()
                try:
                    api_id = int(raw_id)
                    acc["api_id"] = api_id
                except ValueError:
                    print("[ERROR] API_ID must be an integer.")
                    return None, None
            if not api_hash:
                api_hash = input("Enter TELEGRAM_API_HASH: ").strip()
                acc["api_hash"] = api_hash
            self.save()

        try:
            api_id = int(api_id)
        except Exception:
            pass

        client = TelegramClient(session_path, api_id, api_hash, proxy=proxy)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                print("\n" + "=" * 60)
                print(f" 🔑 Authentication Required for: {acc['name']}")
                print("=" * 60)
                if not phone:
                    phone = input(f"Enter phone number for {acc['name']} (e.g. +1234567890): ").strip()
                    acc["phone"] = phone
                    self.save()

                print(f"Connecting to Telegram with {phone}...")
                print("Telegram will send a login code to your Telegram app (or via SMS).")
                await client.start(phone=phone)

            me = await client.get_me()
            name = f"{me.first_name or ''} {me.last_name or ''}".strip()
            username = f"@{me.username}" if me.username else "No Username"
            user_title = f"{name} ({username}) [ID: {me.id}]"
            acc["user_title"] = user_title
            if me.phone:
                acc["phone"] = f"+{me.phone}" if not me.phone.startswith("+") else me.phone
            self.save()

            print(f"\n[+] Successfully logged in as: {name} ({username}) [ID: {me.id}] - [{acc['name']}]")
            return client, me

        except KeyboardInterrupt:
            print(f"\n[*] Login cancelled by user for {acc['name']}.")
            if client.is_connected():
                await client.disconnect()
            return None, None
        except Exception as e:
            print(f"\n[!] Error connecting account '{acc['name']}': {e}")
            if client.is_connected():
                await client.disconnect()
            return None, None


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


async def handle_account_manager(client, account_mgr):
    """Interactive menu to switch between accounts, add accounts, or manage them."""
    while True:
        accounts = account_mgr.get_all_accounts()
        active_id = account_mgr.active_account_id
        active_acc = account_mgr.get_active_account()

        print("\n" + "=" * 65)
        print(" 👥 TELEGRAM ACCOUNT MANAGER")
        print(f" Currently Active: {active_acc['name']} - {active_acc.get('user_title') or 'Not logged in'}")
        print("=" * 65)

        acc_list = list(accounts.values())
        for idx, acc in enumerate(acc_list, 1):
            is_active = " ⭐ [ACTIVE]" if acc["id"] == active_id else ""
            status = acc.get("user_title") or ("Configured" if acc.get("phone") else "Not logged in yet")
            phone_str = f"[{acc.get('phone')}]" if acc.get("phone") else ""
            print(f" {idx}. {acc['name']} {phone_str} -> {status}{is_active}")

        print("-" * 65)
        print(" [1-N] Select number to switch active account")
        print(" [A]   ➕ Add a new Telegram account")
        print(" [R]   ✏️ Rename an account label")
        print(" [D]   🗑️ Delete an account from list")
        print(" [B]   🔙 Back to Main Menu")
        print("=" * 65)

        sub_choice = input("Enter your choice: ").strip().lower()

        if sub_choice in ("b", "back", "0", ""):
            return None

        if sub_choice.isdigit():
            idx = int(sub_choice)
            if 1 <= idx <= len(acc_list):
                selected = acc_list[idx - 1]
                if selected["id"] == active_id:
                    print(f"\n[*] '{selected['name']}' is ALREADY your active account.")
                    continue
                else:
                    account_mgr.set_active_account(selected["id"])
                    print(f"\n[+] Active account switched to: '{selected['name']}'!")
                    return "switch_account"
            else:
                print(f"[!] Please enter a number between 1 and {len(acc_list)}.")

        elif sub_choice == "a":
            switched = await handle_add_account(account_mgr)
            if switched == "switch_account":
                return "switch_account"

        elif sub_choice == "r":
            handle_rename_account(account_mgr)

        elif sub_choice == "d":
            await handle_delete_account(client, account_mgr)

        else:
            print("[!] Invalid choice. Please try again.")


async def handle_add_account(account_mgr):
    """Add a new Telegram account configuration."""
    print("\n" + "=" * 60)
    print(" ➕ ADD NEW TELEGRAM ACCOUNT")
    print("=" * 60)
    default_name = f"Account {len(account_mgr.get_all_accounts()) + 1}"
    name = input(f"Enter account label/name [Default: {default_name}]: ").strip() or default_name
    phone = input("Enter phone number (e.g. +1234567890) [optional, can enter later]: ").strip()

    print("\nAPI Credentials:")
    print("1. Use same API_ID & API_HASH as other accounts (Recommended)")
    print("2. Enter custom API_ID & API_HASH for this account")
    cred_choice = input("Select (1-2) [Default: 1]: ").strip()

    custom_id, custom_hash = None, None
    if cred_choice == "2":
        try:
            custom_id = int(input("Enter TELEGRAM_API_ID: ").strip())
            custom_hash = input("Enter TELEGRAM_API_HASH: ").strip()
        except Exception:
            print("[!] Invalid API ID. Defaulting to shared credentials.")

    new_acc = account_mgr.add_account(name, phone=phone, api_id=custom_id, api_hash=custom_hash)
    print(f"\n[+] Added '{new_acc['name']}' successfully!")

    switch_now = input(f"Do you want to switch to '{new_acc['name']}' right now? (y/n): ").strip().lower()
    if switch_now in ("y", "yes", "بله", "1"):
        account_mgr.set_active_account(new_acc["id"])
        return "switch_account"
    return None


def handle_rename_account(account_mgr):
    """Rename an account's display label."""
    accounts = list(account_mgr.get_all_accounts().values())
    print("\nSelect account to rename:")
    for idx, acc in enumerate(accounts, 1):
        print(f" {idx}. {acc['name']}")

    choice = input(f"Choose account (1-{len(accounts)}) or 0 to cancel: ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(accounts):
        target = accounts[int(choice) - 1]
        new_name = input(f"Enter new label for '{target['name']}': ").strip()
        if new_name:
            account_mgr.rename_account(target["id"], new_name)
            print(f"[✓] Renamed to '{new_name}'.")


async def handle_delete_account(client, account_mgr):
    """Remove an account configuration and optional session file."""
    accounts = list(account_mgr.get_all_accounts().values())
    if len(accounts) <= 1:
        print("[!] You only have 1 account. At least 1 account must remain.")
        return

    print("\nSelect account to delete from list:")
    for idx, acc in enumerate(accounts, 1):
        active_tag = " (Currently Active)" if acc["id"] == account_mgr.active_account_id else ""
        print(f" {idx}. {acc['name']}{active_tag}")

    choice = input(f"Choose account to delete (1-{len(accounts)}) or 0 to cancel: ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(accounts):
        target = accounts[int(choice) - 1]
        confirm = input(f"Are you sure you want to delete '{target['name']}' and its session? (yes/no): ").strip().lower()
        if confirm in ("y", "yes", "بله", "1"):
            if target["id"] == account_mgr.active_account_id and client and client.is_connected():
                await client.disconnect()
            account_mgr.delete_account(target["id"])
            print(f"[✓] Deleted account '{target['name']}'.")


async def handle_logout(client, account_mgr):
    """Log out of the current active Telegram account."""
    active_acc = account_mgr.get_active_account()
    user_info = active_acc.get("user_title") or active_acc.get("phone") or active_acc["name"]

    print("\n" + "=" * 60)
    print(" 🚪 LOG OUT TELEGRAM ACCOUNT")
    print(f" Active Account: {active_acc['name']} ({user_info})")
    print("=" * 60)
    print("Warning: Logging out will terminate this authorization session on")
    print("Telegram servers and remove local session files.")
    print("You will need to re-verify via SMS/Telegram code to log in again.")
    print("-" * 60)

    confirm = input(f"Are you sure you want to log out from '{active_acc['name']}'? (yes/no): ").strip().lower()
    if confirm in ("y", "yes", "بله", "1"):
        success = await account_mgr.logout_account(client, active_acc["id"])
        if success:
            print(f"\n[+] Successfully logged out of '{active_acc['name']}'.")
            return "logged_out"
    else:
        print("[*] Log out cancelled.")
    return None


async def main_menu(client, account_mgr):
    """Display interactive menu options."""
    while True:
        active_acc = account_mgr.get_active_account()
        user_info = active_acc.get("user_title") or active_acc.get("phone") or "Connected"

        print("\n" + "=" * 65)
        print(" 📱 Telegram Account Reader & Group Summarizer")
        print(f" [👤 Active Account: {active_acc['name']} -> {user_info}]")
        print("=" * 65)
        print("1. List all joined groups & channels")
        print("2. Sync / Export FULL group chat (auto-resume new messages)")
        print("3. Quick export recent messages from a group (custom limit)")
        print("4. Batch export recent messages from ALL groups")
        print("5. Start real-time live group message monitor")
        print("6. AI Research & Report Generator (Ask notes -> Report Cluster)")
        print("7. Launch Obsidian Second Brain Builder & Consolidator")
        print(f"8. 👥 Switch / Manage Telegram Accounts (Active: {active_acc['name']})")
        print(f"9. 🚪 Log Out from Current Account ({active_acc['name']})")
        print("10. Exit")
        print("=" * 65)

        choice = input("Select an option (1-10): ").strip()

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
            try:
                from build_second_brain import generate_custom_report, VAULT_DIR
                generate_custom_report(VAULT_DIR)
            except Exception as e:
                print(f"[!] Error launching report generator: {e}")
        elif choice == "7":
            try:
                from build_second_brain import main as launch_second_brain
                launch_second_brain()
            except Exception as e:
                print(f"[!] Error launching Second Brain: {e}")
        elif choice == "8":
            res = await handle_account_manager(client, account_mgr)
            if res == "switch_account":
                return "switch_account"
        elif choice == "9":
            res = await handle_logout(client, account_mgr)
            if res == "logged_out":
                return "logged_out"
        elif choice in ("10", "0", "exit", "q"):
            print("\nExiting. Goodbye!")
            return "exit"
        else:
            print("[!] Invalid choice. Please enter a number between 1 and 10.")


async def main():
    account_mgr = AccountManager()
    proxy = get_proxy()

    while True:
        active_acc = account_mgr.get_active_account()
        print("\n" + "=" * 60)
        print(f" Connecting to Telegram [{active_acc['name']}]...")
        print("=" * 60)

        client, me = await account_mgr.connect_active_account(proxy=proxy)
        if not client:
            print("\n[!] Could not connect to active account.")
            print("1. Open Account Manager (switch account)")
            print("2. Retry connecting")
            print("3. Exit")
            retry_choice = input("Select (1-3): ").strip()
            if retry_choice == "1":
                res = await handle_account_manager(None, account_mgr)
                continue
            elif retry_choice == "2":
                continue
            else:
                break

        try:
            action = await main_menu(client, account_mgr)
            if action == "exit":
                break
            elif action == "switch_account":
                if client.is_connected():
                    await client.disconnect()
                continue
            elif action == "logged_out":
                if client.is_connected():
                    await client.disconnect()
                # Check other accounts
                other_accounts = [a for a in account_mgr.get_all_accounts().values() if a["id"] != active_acc["id"]]
                if other_accounts:
                    next_acc = other_accounts[0]
                    switch_other = input(f"\nWould you like to switch to '{next_acc['name']}'? (y/n): ").strip().lower()
                    if switch_other in ("y", "yes", "بله", "1"):
                        account_mgr.set_active_account(next_acc["id"])
                continue

        except KeyboardInterrupt:
            print("\nProgram interrupted by user.")
            break
        except Exception as e:
            print(f"\n[!] Unexpected error: {e}")
            break
        finally:
            if client and client.is_connected():
                await client.disconnect()
                print("[*] Disconnected from Telegram.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExited.")
