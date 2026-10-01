# Telegram Summarizer & Obsidian Second Brain

A modular, end-to-end Python toolkit to archive Telegram group and channel discussions, synthesize them into an interconnected **Obsidian Second Brain** using Google Gemini AI, and export everything into a standalone offline interactive HTML & PDF knowledge base.

---

## 🚀 Features

### 1. Telegram Message & Group Sync (`main.py`)
- **List Joined Groups & Channels**: View all groups, supergroups, and channels your account has joined, along with group IDs, unread message counts, and sync status.
- **Sync / Export FULL Group Chat (Auto-Resume)**:
  - **First Run**: Exports the entire message history of the selected group.
  - **Subsequent Runs**: Automatically detects the last stored `message_id` and fetches **only** newer messages (`min_id=last_id`), seamlessly appending them to the archive.
  - Saves to `exports/synced_chats/<group_name>_<group_id>.json` and `.txt`.
  - **Ctrl+C Safe & Auto-Save**: Progress checkpoints ensure no data is lost if interrupted.
- **Quick Read & Export**: Pick any group and retrieve the latest *N* messages on-demand.
- **Batch Export All Groups**: Export recent messages from **all** joined groups at once into structured `.json` and readable `.txt` files in `exports/`.
- **Live Real-Time Monitoring**: Stream new incoming messages across all groups live in your terminal with timestamps, sender names, and group titles, with automatic logging to `exports/realtime_live_log.txt`.

### 2. AI Second Brain Builder (`build_second_brain.py`)
- **Brain-in-the-Loop Synthesis**: Feeds the current vault catalog to Gemini so newer batches update and enrich existing master notes instead of generating duplicate fragments.
- **Date-Stamped Information**: Automatically prefixes every fact and tip with `[YYYY-MM-DD]` for clear chronological context.
- **Incremental Updates**: Detects new messages added to your chat archives and updates existing notes without re-processing older history.
- **Smart Model Failover**: Gracefully rotates between Gemini model quota pools on rate limits (429) or high-load conditions (503).
- **Consolidation Engine**: Merges related notes and generates an automatic Map of Content (`00_Map_of_Content.md`) optimized for Obsidian's interactive Graph View.

### 3. Standalone Offline HTML & PDF Exporter (`export_vault_to_html.py`)
- **100% Offline Single-File HTML**: Packages your entire Obsidian vault into a self-contained, zero-CDN HTML file with inline styles, search, and navigation.
- **First-Vocab BiDi Support**: Dynamically handles mixed RTL (Persian, Arabic) and LTR (English) text per paragraph.
- **Instant Search**: Full-text and tag search (`Ctrl+K`).
- **LaTeX & PDF Generation**: Generates a unified printable book PDF of your entire knowledge base.

---

## 📋 Prerequisites & Setup

### 1. Clone & Install Dependencies

```bash
git clone https://github.com/<your-username>/telegram-summarizer.git
cd telegram-summarizer
pip install -r requirements.txt
```

### 2. Telegram API Credentials

To access Telegram messages via MTProto, you need an API ID and API Hash:

1. Visit [my.telegram.org](https://my.telegram.org) and log in with your phone number.
2. Navigate to **API development tools**.
3. Create a new application (any app title and short name, e.g. "MySummarizer").
4. Copy your **`api_id`** (numeric) and **`api_hash`** (string).

### 3. Gemini API Key

Get a free Gemini API key from [Google AI Studio](https://aistudio.google.com).

### 4. Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
# Windows
copy .env.example .env

# Linux / macOS
cp .env.example .env
```

Open `.env` and fill in your credentials:

```env
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=0123456789abcdef0123456789abcdef
TELEGRAM_PHONE=+1234567890
GEMINI_API_KEY=AIzaSy...

# Optional proxy (uncomment if required in your network)
# PROXY_TYPE=socks5
# PROXY_HOST=127.0.0.1
# PROXY_PORT=10808
```

---

## 🛠️ Usage

### Step 1: Export Chat History (`main.py`)

Run the interactive client:

```bash
python main.py
```

1. On first login, Telegram will send a verification code to your Telegram app (or SMS). Enter it in the terminal.
2. Select **Option 2** to sync a group's full history. The archive will be saved in `exports/synced_chats/`.

### Step 2: Build the Second Brain Knowledge Base (`build_second_brain.py`)

```bash
python build_second_brain.py
```

1. Select **Option 1** to process a chat archive.
2. Choose your batch size (default: 800 messages per call — optimal for free quotas).
3. Notes are generated inside `Obsidian_Vault/` categorized by topic.
4. You can pause anytime with `Ctrl+C` and resume without losing progress.

### Step 3: Open in Obsidian

1. Download and install [Obsidian](https://obsidian.md).
2. Click **Open folder as vault**.
3. Select the `Obsidian_Vault` directory.
4. Open `00_Map_of_Content.md` to navigate notes, or press `Ctrl + G` to view your interactive **Graph View**!

### Step 4: Export to Offline HTML / PDF (`export_vault_to_html.py`)

```bash
python export_vault_to_html.py
```

Exports a single, self-contained `Second_Brain_Knowledge_Base.html` and TeX/PDF book to `exports/` for easy sharing.

---

## 📂 Project Structure

```text
telegram-summarizer/
├── main.py                   # Telegram MTProto client, chat exporter & live monitor
├── build_second_brain.py     # Gemini AI knowledge extractor & vault consolidator
├── export_vault_to_html.py   # Offline HTML & PDF documentation generator
├── requirements.txt          # Python dependencies
├── .env.example              # Sample environment configuration
├── .gitignore                # Git ignore rules for secrets, sessions, & archives
├── Obsidian_Vault/           # Destination folder for generated Obsidian notes
└── exports/
    ├── synced_chats/         # Exported JSON and TXT chat archives
    └── checkpoints/          # Progress checkpoints for resuming AI batches
```

---

## 🔒 Security & Privacy

- **Never commit `.env` or `*.session` files**: `.gitignore` is pre-configured to exclude all personal authentication sessions, tokens, and exported chat archives.
- **Zero Cloud Storage**: All raw messages and generated notes remain 100% on your local disk.
