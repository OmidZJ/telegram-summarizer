# Telegram Summarizer & Obsidian Second Brain

A modular, end-to-end Python toolkit to archive Telegram group and channel discussions across multiple accounts, synthesize them into an interconnected **Obsidian Second Brain** using Google Gemini AI, generate targeted research reports, and export everything into a standalone offline interactive HTML & PDF knowledge base.

---

## 🚀 Features

### 1. Multi-Account Telegram Client & Group Sync (`main.py`)
- **Multi-Account Switching & Management**: Connect and switch seamlessly between multiple Telegram accounts directly from the interactive menu, with isolated session management (`telegram_accounts.json`).
- **Secure Account Logout**: Invalidate sessions on Telegram servers and cleanly remove local session files on demand.
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
- **Group Clusters Architecture**: Automatically organizes notes into dedicated group/community subfolders (`Obsidian_Vault/<Group_Cluster>/<Category>/`) with localized Maps of Content and deep wikilinks.
- **Direct Telegram Message Links**: Every synthesized bullet point contains a direct, clickable deep-link pill (e.g. `[💬 #12345](https://t.me/c/...)`) pointing back to the exact source message in Telegram.
- **Brain-in-the-Loop Synthesis**: Feeds the current vault catalog to Gemini so newer batches update and enrich existing master notes instead of generating duplicate fragments.
- **Date Normalization & Range Filtering**: Filter messages by date ranges (`YYYY-MM-DD`, `YYYY-MM`, `YYYY`) to extract only relevant historical periods.
- **Date-Stamped Information**: Automatically prefixes every fact and tip with `[YYYY-MM-DD]` for clear chronological context.
- **Smart Model Failover**: Gracefully rotates between candidate Gemini models (`gemini-flash-lite-latest`, `gemini-3.5-flash`, etc.) on rate limits (429) or high-load conditions (503).
- **Consolidation & Cleanup Suite**: Built-in tools to merge fragmented notes, unify bilingual folder names, clean companion summary notes, and repair broken links.

### 3. AI Research & Custom Report Generator
- **Targeted Knowledge Mining**: Ask complex questions across your entire vault or specific categories.
- **Structured Report Cluster**: Generates comprehensive, synthesized reports stored in `Obsidian_Vault/Report_Cluster/` with source citations and key takeaways.

### 4. Standalone Offline HTML & PDF Exporter (`export_vault_to_html.py`)
- **100% Offline Single-File HTML**: Packages your entire Obsidian vault into a self-contained, zero-CDN HTML file with inline styles, search, and navigation.
- **Group Cluster Navigation**: Hierarchical explorer supporting Group Clusters, subclusters, and category badges.
- **First-Vocab BiDi Support**: Dynamically handles mixed RTL (Persian, Arabic) and LTR (English) text per paragraph.
- **Instant Search**: Full-text and tag search (`Ctrl+K`).
- **LaTeX & PDF Generation**: Generates a unified printable book PDF with Xepersian font configuration and clickable hyperlinked table of contents.

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

### Step 1: Launch the Interactive Dashboard (`main.py`)

Run the main client:

```bash
python main.py
```

The central menu allows you to:
1. **Sync / Export Groups**: Sync full message history with auto-resume.
2. **Manage Accounts**: Add secondary Telegram accounts or switch active profiles.
3. **Live Monitor**: Stream real-time messages from all joined channels.
4. **Launch AI Tools**: Direct shortcuts to the Second Brain builder or Custom Report generator.

### Step 2: Build the Second Brain Knowledge Base (`build_second_brain.py`)

```bash
python build_second_brain.py
```

1. Select **Option 1** to process an exported chat archive.
2. Choose your date range filter (or press Enter for full history).
3. Set your batch size (default: 800 messages per call — optimal for free quotas).
4. Notes are automatically organized into `Obsidian_Vault/<Group_Cluster>/`.
5. Pause anytime with `Ctrl+C` and resume without losing progress.

### Step 3: Open in Obsidian

1. Download and install [Obsidian](https://obsidian.md).
2. Click **Open folder as vault**.
3. Select the `Obsidian_Vault` directory.
4. Open `00_Map_of_Content.md` to navigate notes, or press `Ctrl + G` to view your interactive **Graph View**!

### Step 4: Export to Offline HTML / PDF (`export_vault_to_html.py`)

```bash
python export_vault_to_html.py
```

Exports a single, self-contained `Second_Brain_Knowledge_Base.html` and TeX/PDF book to `exports/` for easy offline reading and sharing.

---

## 📂 Project Structure

```text
telegram-summarizer/
├── main.py                         # Multi-account MTProto client, chat exporter & live monitor
├── build_second_brain.py           # Gemini AI knowledge extractor, cluster organizer & consolidator
├── export_vault_to_html.py         # Offline HTML & LaTeX/PDF documentation generator
├── requirements.txt                # Python dependencies
├── .env.example                    # Sample environment configuration template
├── telegram_accounts.example.json  # Multi-account configuration template
├── .gitignore                      # Git ignore rules for secrets, sessions, & archives
├── Obsidian_Vault/                 # Destination folder for generated Obsidian notes
└── exports/
    ├── synced_chats/               # Exported JSON and TXT chat archives
    └── checkpoints/                # Progress checkpoints for resuming AI batches
```

---

## 🔒 Security & Privacy

- **Never commit `.env`, `telegram_accounts.json`, or `*.session` files**: `.gitignore` is pre-configured to exclude all personal authentication sessions, tokens, credentials, and exported chat archives.
- **Zero Cloud Storage**: All raw messages and generated notes remain 100% on your local disk.
