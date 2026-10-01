"""
Obsidian Second Brain Builder & Knowledge Consolidator
======================================================
Transforms Telegram chat archives into an interconnected, non-fragmented
Second Brain vault using Google Gemini API (Free Tier Friendly).

Features:
- Brain-in-the-Loop: Sends existing brain catalog to Gemini with each batch
  so the model UPDATES existing notes instead of creating duplicate fragments.
- Date-Stamped Information: Prefixes every fact/tip with **[YYYY-MM-DD]**
  so you always know the recency and timeline of the information.
- Dynamic Model Failover: Switches between free Gemini models seamlessly.
- Smart Checkpointing: Resume interrupted batches without wasting free quota.
- Built-in Vault Consolidator: Merges existing cluttered notes into rich master guides.
- Automatic Map of Content (00_Map_of_Content.md) and Graph View optimization.
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import requests

# Fix Windows console encoding for Persian/Unicode text
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Base paths
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

EXPORTS_DIR = BASE_DIR / "exports" / "synced_chats"
CHECKPOINTS_DIR = BASE_DIR / "exports" / "checkpoints"
CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
VAULT_DIR = BASE_DIR / "Obsidian_Vault"
VAULT_DIR.mkdir(parents=True, exist_ok=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Candidate models in order of priority (handles deprecations, rate limits, and 503 high demand)
CANDIDATE_MODELS = [
    "gemini-flash-latest",
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3.5-flash",
    "gemini-3.8-flash",
]
CURRENT_MODEL_INDEX = 0


def check_api_key():
    """Ensure Gemini API key is available."""
    global GEMINI_API_KEY
    if not GEMINI_API_KEY:
        print("=" * 65)
        print(" [!] Google Gemini API Key Required")
        print("=" * 65)
        print("1. Get a 100% free API key at: https://aistudio.google.com")
        print("2. Add it to your .env file: GEMINI_API_KEY=AIzaSy...")
        print("=" * 65)
        GEMINI_API_KEY = input("Or enter your GEMINI_API_KEY now: ").strip()
        if not GEMINI_API_KEY:
            print("[ERROR] Cannot proceed without an API key.")
            sys.exit(1)


def is_chatter(text: str) -> bool:
    """Filter out noise, greetings, stickers, and trivial one-liners."""
    if not text:
        return True
    clean = text.strip()
    if len(clean) < 12:
        return True

    noise_patterns = [
        r"^(سلام|درود|مرسی|ممنون|تشکر|خواهش|خواهش میکنم|اوکی|بله|خیر|دمت گرم|خسته نباشید|مبارکه|انشالله|ایشالا|اره|نه)$",
        r"^(hi|hello|thanks|thank you|thx|ok|okay|k|yes|no|bye|welcome|congrats)$",
        r"^\[Action:.*\]$",
        r"^\[MessageMedia.*\]$",
        r"^\[Photo\]$",
        r"^\[Sticker\]$",
    ]
    for pat in noise_patterns:
        if re.match(pat, clean, re.IGNORECASE):
            return True
    return False


def call_gemini(prompt: str, json_mode: bool = True, max_retries: int = 10) -> str:
    """
    Call Google Gemini REST API with automatic candidate model failover on 429 (rate limit),
    503 (overload), and 404 (unavailable). Cycles through independent model quota pools.
    Supports both JSON response mode and freeform Markdown text mode.
    """
    global CURRENT_MODEL_INDEX
    consecutive_429s = 0

    for attempt in range(max_retries):
        model_name = CANDIDATE_MODELS[CURRENT_MODEL_INDEX]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        gen_config = {
            "temperature": 0.2,
            "maxOutputTokens": 8192,
        }
        if json_mode:
            gen_config["responseMimeType"] = "application/json"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": gen_config
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=90)

            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        return parts[0]["text"]
                return ""

            elif resp.status_code == 429:
                consecutive_429s += 1
                old_model = model_name
                # Immediately switch to next candidate model with its own quota pool!
                CURRENT_MODEL_INDEX = (CURRENT_MODEL_INDEX + 1) % len(CANDIDATE_MODELS)
                new_model = CANDIDATE_MODELS[CURRENT_MODEL_INDEX]

                # If all models in the pool have hit 429, wait briefly before cycling again
                if consecutive_429s >= len(CANDIDATE_MODELS):
                    wait_time = 20
                    print(f"[!] All candidate models hit 429 rate limit. Waiting {wait_time}s before next cycle...")
                    time.sleep(wait_time)
                    consecutive_429s = 0
                else:
                    print(f"[!] Rate limit (429) hit on {old_model}. Switching to {new_model} immediately...")
                    time.sleep(3)

            elif resp.status_code in (404, 503):
                old_model = model_name
                CURRENT_MODEL_INDEX = (CURRENT_MODEL_INDEX + 1) % len(CANDIDATE_MODELS)
                new_model = CANDIDATE_MODELS[CURRENT_MODEL_INDEX]
                print(f"[!] Model {old_model} returned {resp.status_code}. Failing over to {new_model}...")
                time.sleep(2)

            else:
                print(f"[!] API Error {resp.status_code} ({model_name}): {resp.text[:150]}")
                time.sleep(4)

        except Exception as e:
            print(f"[!] Network error ({e}). Retrying in 4s...")
            time.sleep(4)

    return ""


def sanitize_filename(name: str) -> str:
    """Make filename safe for Windows and Obsidian."""
    cleaned = re.sub(r'[\\/*?:"<>|#^]', "", name).strip()
    return cleaned[:75] or "Untitled_Note"


def repair_json_array(json_str: str) -> str:
    """If a JSON array was cut off mid-response, salvage all complete objects."""
    s = json_str.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s).strip()

    if not s.startswith("["):
        if s.startswith("{"):
            s = "[" + s
        else:
            first_b = s.find("[")
            if first_b != -1:
                s = s[first_b:]
            else:
                return s

    # Find the last occurrence of '}' to discard the half-written trailing object
    last_brace = s.rfind("}")
    if last_brace != -1:
        truncated = s[:last_brace + 1].strip()
        if not truncated.endswith("]"):
            truncated += "\n]"
        return truncated
    return s


def get_brain_catalog(vault_dir: Path, max_notes: int = 150) -> str:
    """
    Build a compact representation of the existing Second Brain catalog
    to feed back into Gemini so it knows what notes exist to update.
    """
    catalog_lines = []
    total = 0

    for cat_dir in sorted(vault_dir.iterdir()):
        if not cat_dir.is_dir() or cat_dir.name.startswith("."):
            continue

        notes = sorted(cat_dir.glob("*.md"))
        if not notes:
            continue

        cat_title = cat_dir.name.replace("_", " ")
        catalog_lines.append(f"\n[{cat_title}]")

        for note_file in notes:
            if "(خلاصه شده)" in note_file.name:
                continue
            if total >= max_notes:
                break
            title = note_file.stem
            # Extract 1-line summary from file if available
            summary = ""
            try:
                content = note_file.read_text(encoding="utf-8")
                match = re.search(r">\s*\[!summary\]\s*\n>\s*([^\n]+)", content)
                if match:
                    summary = f" -> {match.group(1).strip()[:80]}"
            except Exception:
                pass

            catalog_lines.append(f"- [[{title}]]{summary}")
            total += 1

        if total >= max_notes:
            catalog_lines.append(f"... (and more notes in vault)")
            break

    if not catalog_lines:
        return "(Brain is currently empty. Create foundational master notes.)"

    return "\n".join(catalog_lines)


SYSTEM_PROMPT = """
You are an expert knowledge curator and Obsidian Second Brain architect.
Your mission is to maintain an interconnected, non-fragmented, and comprehensive Second Brain vault from Telegram chat and community archives.

CURRENT BRAIN STATE:
You will be provided with the CURRENT list of notes already existing in the vault.

CRITICAL RULES:
1. PREFER UPDATING EXISTING NOTES OVER CREATING NEW ONES:
   - If the conversation discusses a topic already in the Brain, DO NOT create a new note with a slightly different title!
   - Set "action": "UPDATE" and "target_title": "<Exact Title from Brain>".
   - ONLY set "action": "CREATE" if the information represents a genuinely new topic/domain not covered by existing notes.
   - Keep the vault consolidated into rich, comprehensive master guides rather than hundreds of fragmented 2-line notes!

2. MANDATORY DATE STAMPING:
   - Every message in the conversation has a date timestamp: [YYYY-MM-DD].
   - EVERY bullet point in "new_key_points", "new_tips_and_experiences", and "new_mistakes_to_avoid" MUST start with its date in bold:
     "**[YYYY-MM-DD]** <Information/Rule/Fact>"
   - This ensures the user knows exactly when each rule, experience, or fact was stated!

3. LANGUAGE & LOCALIZATION INTELLIGENCE:
   - Match the primary language of the conversation (Persian, English, etc.).
   - Retain technical English terms and official terminology in parentheses where appropriate.

Output a valid JSON array of note operations adhering to this schema:
[
  {
    "action": "UPDATE" or "CREATE",
    "target_title": "Existing Note Title (if UPDATE) or New Master Note Title (if CREATE)",
    "category": "Existing category name from Brain catalog, or a new clean Category_Name if needed",
    "tags": ["tag1", "tag2"],
    "summary": "Concise 2-sentence overview of what this note covers.",
    "new_key_points": [
      "**[YYYY-MM-DD]** Official rule, requirement, verified procedure, or factual statement"
    ],
    "new_tips_and_experiences": [
      "**[YYYY-MM-DD]** Practical applicant tip or shared experience"
    ],
    "new_mistakes_to_avoid": [
      "**[YYYY-MM-DD]** Common pitfall, warning, or trap"
    ],
    "related_topics": [
      "Conceptual Topic 1 (for Obsidian [[Wikilinks]])",
      "Conceptual Topic 2 (for Obsidian [[Wikilinks]])"
    ]
  }
]

Output ONLY the raw valid JSON array.
"""


def find_existing_note(vault_dir: Path, target_title: str) -> Path:
    """Search for existing note file matching title across all vault categories."""
    target_clean = sanitize_filename(target_title).lower()

    # Exact match first (skip (خلاصه شده) companion notes)
    for md_file in vault_dir.rglob("*.md"):
        if md_file.name.startswith(".") or "(خلاصه شده)" in md_file.name:
            continue
        if md_file.stem.lower() == target_clean:
            return md_file

    # Partial / fuzzy containment match
    for md_file in vault_dir.rglob("*.md"):
        if md_file.name.startswith(".") or "(خلاصه شده)" in md_file.name:
            continue
        stem_lower = md_file.stem.lower()
        if (target_clean in stem_lower or stem_lower in target_clean) and len(target_clean) > 8:
            return md_file

    return None


def sanitize_category(name: str) -> str:
    """Normalize category folder names to clean underscore format."""
    cleaned = sanitize_filename(name).strip()
    return re.sub(r"\s+", "_", cleaned)


def normalize_point_for_dedupe(text: str) -> str:
    """Normalize text for strict duplicate detection without dropping distinct points."""
    t = re.sub(r"^\*{0,2}\[?\d{4}-\d{2}-\d{2}\]?\*{0,2}\s*[:\-–—]?\s*", "", text).strip()
    t = re.sub(r"^[⚠️📌💡⚡❌•\-\*\s]+", "", t).strip()
    t = t.replace("\u200c", " ").replace("ي", "ی").replace("ك", "ک")
    t = re.sub(r"[^\w\s\u0600-\u06FF]", "", t)
    return re.sub(r"\s+", " ", t).strip().lower()


def extract_core_text(bullet: str) -> str:
    """Extract text without the date stamp for duplicate detection."""
    return normalize_point_for_dedupe(bullet)


def save_or_update_note(vault_dir: Path, op: dict, source_file: str):
    """
    Create a new note or update an existing note by appending dated points
    into their respective sections with automatic zero-loss deduplication.
    """
    action = op.get("action", "CREATE").upper()
    target_title = sanitize_filename(op.get("target_title", "Untitled Note"))
    category = sanitize_category(op.get("category", "General_And_FAQ"))
    summary = op.get("summary", "").strip()

    new_points = [p.strip() for p in op.get("new_key_points", []) if p.strip()]
    new_tips = [t.strip() for t in op.get("new_tips_and_experiences", []) if t.strip()]
    new_mistakes = [m.strip() for m in op.get("new_mistakes_to_avoid", []) if m.strip()]
    new_related = [r.strip() for r in op.get("related_topics", []) if r.strip()]
    tags = [t.strip().replace("#", "").replace(" ", "_") for t in op.get("tags", []) if t.strip()]

    now_str = datetime.now().strftime("%Y-%m-%d")

    # Check if note file already exists
    existing_file = find_existing_note(vault_dir, target_title) if (action == "UPDATE" or target_title) else None

    if existing_file and existing_file.exists():
        # UPDATE EXISTING NOTE
        try:
            content = existing_file.read_text(encoding="utf-8")
        except Exception:
            content = ""

        # Update frontmatter updated_at
        if "updated_at:" in content:
            content = re.sub(r"updated_at:\s*[^\n]+", f"updated_at: {now_str}", content)
        elif "---" in content:
            content = content.replace("---\n\n", f"updated_at: {now_str}\n---\n\n", 1)

        # Helper to append unique bullet points to a section (Zero-Loss Deduplication)
        def append_to_section(doc: str, section_header: str, items: list, prefix: str = "- ") -> str:
            if not items:
                return doc

            # Filter duplicates strictly: only drop identical normalized text
            doc_lines_norm = {normalize_point_for_dedupe(l) for l in doc.splitlines() if l.strip()}
            unique_items = []
            for it in items:
                norm = normalize_point_for_dedupe(it)
                if not norm:
                    continue
                if norm not in doc_lines_norm:
                    unique_items.append(it)
                    doc_lines_norm.add(norm)

            if not unique_items:
                return doc

            formatted_block = "\n".join(f"{prefix}{it}" for it in unique_items)

            if section_header in doc:
                # Insert at end of that section
                pattern = rf"({re.escape(section_header)}[^\n]*\n)(.*?)(?=\n## |\Z)"
                match = re.search(pattern, doc, re.DOTALL)
                if match:
                    existing_section_body = match.group(2).rstrip()
                    new_section_body = f"{existing_section_body}\n{formatted_block}\n"
                    doc = doc[:match.start(2)] + new_section_body + doc[match.end(2):]
                else:
                    doc += f"\n\n{section_header}\n{formatted_block}"
            else:
                doc += f"\n\n{section_header}\n{formatted_block}"

            return doc

        content = append_to_section(content, "## 📌 Key Information & Rules", new_points)
        content = append_to_section(content, "## 💡 Tips & Experiences", new_tips)
        content = append_to_section(content, "## ⚠️ Common Mistakes & Warnings", new_mistakes, prefix="- ⚠️ ")

        # Append new related wikilinks
        for rel in new_related:
            clean_rel = re.sub(r"[\[\]]", "", rel).strip()
            if clean_rel:
                link_str = f"[[{clean_rel}]]"
                if link_str not in content:
                    content = append_to_section(content, "## 🔗 Related Notes", [link_str], prefix="- ")

        try:
            existing_file.write_text(content, encoding="utf-8")
            print(f"    [Updated Note] [[{existing_file.stem}]] (+{len(new_points) + len(new_tips)} new points)")
        except Exception as e:
            print(f"[!] Error updating {existing_file.name}: {e}")

    else:
        # CREATE NEW MASTER NOTE
        cat_dir = vault_dir / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        file_path = cat_dir / f"{target_title}.md"

        tags_yaml = "\n".join(f"  - {t}" for t in tags) if tags else "  - second_brain"
        points_md = "\n".join(f"- {p}" for p in new_points) if new_points else "- (No specific points recorded yet)"
        tips_md = "\n".join(f"- {t}" for t in new_tips) if new_tips else ""
        mistakes_md = "\n".join(f"- ⚠️ {m}" for m in new_mistakes) if new_mistakes else ""
        links_md = "\n".join(f"- [[{r}]]" for r in new_related) if new_related else "- [[00_Map_of_Content]]"

        body = [
            f"---",
            f"title: \"{target_title}\"",
            f"category: \"{category}\"",
            f"created_at: {now_str}",
            f"updated_at: {now_str}",
            f"source: \"{source_file}\"",
            f"tags:",
            tags_yaml,
            f"---",
            f"",
            f"# {target_title}",
            f"",
            f"> [!summary]",
            f"> {summary or 'Comprehensive master note generated from Telegram discussions.'}",
            f"",
            f"## 📌 Key Information & Rules",
            points_md,
        ]

        if tips_md:
            body.extend([f"", f"## 💡 Tips & Experiences", tips_md])
        if mistakes_md:
            body.extend([f"", f"## ⚠️ Common Mistakes & Warnings", mistakes_md])

        body.extend([f"", f"## 🔗 Related Notes", links_md, f""])

        try:
            file_path.write_text("\n".join(body), encoding="utf-8")
            print(f"    [Created Note] [[{target_title}]] ({category})")
        except Exception as e:
            print(f"[!] Error creating {file_path.name}: {e}")


def generate_map_of_content(vault_dir: Path):
    """Create the central 00_Map_of_Content.md index dashboard for Obsidian."""
    moc_path = vault_dir / "00_Map_of_Content.md"
    categories = {}
    total_notes = 0

    for cat_dir in sorted(vault_dir.iterdir()):
        if cat_dir.is_dir() and not cat_dir.name.startswith("."):
            notes = [f.stem for f in cat_dir.glob("*.md")]
            if notes:
                categories[cat_dir.name] = sorted(notes)
                total_notes += len(notes)

    moc_content = f"""---
title: فهرست مطالب
updated_at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
total_notes: {total_notes}
tags:
  - moc
  - index
---

# 🧠 فهرست مطالب (Map of Content)

> پایگاه دانش یکپارچه و دسته‌بندی‌شده استخراج‌شده از آرشیو پیام‌ها و تجربیات.
> **تعداد کل یادداشت‌ها**: {total_notes} یادداشت در {len(categories)} دسته‌بندی موضوعی.
> در نرم‌افزار آبسیدین می‌توانید با کلید میانبر `Ctrl+G` نمای گراف شبکه‌ای (Graph View) را باز کنید.

---

"""
    for cat, notes in sorted(categories.items()):
        cat_clean = cat.replace("_", " ")
        moc_content += f"\n## 📁 {cat_clean} ({len(notes)} notes)\n"
        main_notes = [n for n in notes if "(خلاصه شده)" not in n]
        for note in main_notes:
            moc_content += f"- [[{note}]]\n"
            summary_name = f"{note} (خلاصه شده)"
            if summary_name in notes:
                moc_content += f"  - ⚡ [[{summary_name}]]\n"
        for note in notes:
            if "(خلاصه شده)" in note and note.replace(" (خلاصه شده)", "") not in main_notes:
                moc_content += f"- ⚡ [[{note}]]\n"

    try:
        moc_path.write_text(moc_content, encoding="utf-8")
        print(f"\n[+] Updated Map of Content: {moc_path} ({total_notes} master notes indexed)")
    except Exception as e:
        print(f"[!] Warning writing MOC: {e}")


def get_checkpoint_path(file_path: Path) -> Path:
    """Return path to checkpoint file for a given chat file."""
    safe_name = sanitize_filename(file_path.stem)
    return CHECKPOINTS_DIR / f"checkpoint_{safe_name}.json"


def load_checkpoint(file_path: Path):
    """Load existing checkpoint if available."""
    cp_path = get_checkpoint_path(file_path)
    if cp_path.exists():
        try:
            with open(cp_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Backward compatibility: infer last_message_id if missing
                if "last_message_id" not in data:
                    data["last_message_id"] = 0
                return data
        except Exception:
            pass
    return None


def save_checkpoint(
    file_path: Path,
    current_batch: int,
    total_batches: int,
    ops_count: int,
    last_message_id: int = 0,
):
    """Save progress checkpoint to disk with exact message ID boundary."""
    cp_path = get_checkpoint_path(file_path)
    data = {
        "file": file_path.name,
        "current_batch": current_batch,
        "total_batches": total_batches,
        "ops_count": ops_count,
        "last_message_id": last_message_id,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        with open(cp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def synthesize_points_chunk(section_name: str, note_title: str, points: list) -> str:
    """Synthesize a chunk of raw bullet points with Gemini into structured, dated Markdown."""
    prompt = f"""You are an elite knowledge synthesizer and Obsidian Second Brain architect.
Your task is to deeply synthesize the following raw bullet points from the section '{section_name}' of the master guide '{note_title}'.

RAW BULLET POINTS:
{chr(10).join(points)}

OBJECTIVES & CRITICAL RULES:
1. MERGE DUPLICATES & REDUNDANCY (MANDATORY):
   - You MUST merge all overlapping, similar, or repetitive points into unified, authoritative bullet points.
   - Group them under 1 to 4 clear thematic subsections using Markdown headings '### <Persian Subheading>'.
   - DO NOT just repeat or list points with their date in front like '[YYYY-MM-DD]'. Each bullet point must be a synthesized statement starting with a bold topic, e.g.:
     * **<موضوع/قانون>:** <توضیح کامل، دقیق و بدون ابهام> (YYYY-MM-DD, ...)
2. PRESERVE DATES IN PARENTHESES:
   - Original points contain dates like **[YYYY-MM-DD]**.
   - You MUST collect and keep all dates in parentheses at the end of each synthesized statement:
     Example: "(YYYY-MM-DD, ...)" or "(2021-12-14, 2023-04-25, 2025-12-13)".
   - If a rule, value, or procedure evolved over time, explain the timeline evolution clearly and cite both/all dates:
     Example: "* **عنوان موضوع و تغییرات:** در سال‌های قبل روند به شکل اول بود (2021-03-04)، اما بر اساس آخرین به‌روزرسانی‌ها به شکل جدید تغییر یافته است (2026-07-29)."
3. PRESERVE ALL UNIQUE FACTS & DETAILS:
   - Do NOT omit any unique condition, threshold, reference, link, exception, or specific advice.
4. LANGUAGE & TONE:
   - Fluent, formal, authoritative language matching the source. Keep technical or domain-specific terms in parentheses where appropriate.
5. CLEAN OUTPUT:
   - Output ONLY clean Markdown (using '### ' for subheadings and '* ' or '- ' for bullet points).
   - Do NOT wrap in ```markdown or ``` code blocks.
"""
    raw = call_gemini(prompt, json_mode=False)
    if not raw:
        return ""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:markdown)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    return cleaned


def synthesize_points_section(section_name: str, note_title: str, points: list) -> str:
    """Synthesizes a list of bullet points, chunking if necessary."""
    if not points:
        return ""
    if len(points) <= 1:
        return "\n".join(points)

    chunk_size = 120
    if len(points) <= chunk_size:
        print(f"    -> Synthesizing '{section_name}' ({len(points)} points)...")
        res = synthesize_points_chunk(section_name, note_title, points)
        return res or "\n".join(points)

    chunks = [points[i:i + chunk_size] for i in range(0, len(points), chunk_size)]
    print(f"    -> Synthesizing '{section_name}' ({len(points)} points across {len(chunks)} chunks)...")

    synthesized_parts = []
    for idx, ch in enumerate(chunks, 1):
        print(f"       [Chunk {idx}/{len(chunks)}] Processing {len(ch)} points...")
        part = synthesize_points_chunk(section_name, note_title, ch)
        if part:
            synthesized_parts.append(part)
        time.sleep(2)

    combined = "\n\n".join(synthesized_parts)
    combined_lines = combined.splitlines()

    if len(combined_lines) > 80:
        print(f"       -> Harmonizing {len(combined_lines)} lines across chunks into unified guide...")
        harmonize_prompt = f"""You are an elite knowledge curator.
Below is the consolidated draft for section '{section_name}' of '{note_title}', compiled from multiple batches.
Harmonize the subheadings ('### '), merge any remaining duplicate points, and unify the structure.
CRITICAL: Preserve all dates in parentheses e.g. (YYYY-MM-DD, ...) and all unique facts.
Output ONLY clean Markdown.

DRAFT CONTENT:
{combined}
"""
        harmonized = call_gemini(harmonize_prompt, json_mode=False)
        if harmonized:
            cleaned = harmonized.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:markdown)?\s*", "", cleaned)
                cleaned = re.sub(r"\s*```$", "", cleaned).strip()
            return cleaned

    return combined


def synthesize_single_note(note_file: Path, min_points: int = 50, force: bool = False) -> bool:
    """
    Synthesize and clean a master note:
    - Skips notes with few points (total_bullets < min_points) unless force=True.
    - Retains the original master note with all its raw points 100% intact!
    - Creates a dedicated companion note '{title} (خلاصه شده).md' with deduplicated,
      structured knowledge and preserved (YYYY-MM-DD) date citations.
    - Adds a banner callout at the top of the original note pointing to the summary note.
    """
    if "(خلاصه شده)" in note_file.stem:
        return False

    try:
        content = note_file.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[!] Error reading {note_file.name}: {e}")
        return False

    # Extract frontmatter
    fm_match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    frontmatter_yaml = fm_match.group(1).strip() if fm_match else ""

    # Extract title
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    note_title = title_match.group(1).strip() if title_match else note_file.stem

    # Extract summary
    sum_match = re.search(r">\s*\[!summary\]\s*\n>\s*([^\n]+)", content)
    summary = sum_match.group(1).strip() if sum_match else ""

    # Parse sections and bullet points
    lines = content.splitlines()
    sections = {}
    current_sec = None

    for line in lines:
        line_s = line.strip()
        if line_s.startswith("## 📌") or "نکات کلیدی" in line_s or "Key Information" in line_s:
            current_sec = "rules"
            sections.setdefault(current_sec, [])
        elif line_s.startswith("## 💡") or "نکات و تجربیات" in line_s or "Tips & Experiences" in line_s:
            current_sec = "tips"
            sections.setdefault(current_sec, [])
        elif line_s.startswith("## ⚠️") or "اشتباهات رایج" in line_s or "Common Mistakes" in line_s:
            current_sec = "mistakes"
            sections.setdefault(current_sec, [])
        elif line_s.startswith("## 🔗") or "یادداشت‌های مرتبط" in line_s or "Related Notes" in line_s:
            current_sec = "links"
            sections.setdefault(current_sec, [])
        elif line_s.startswith("## "):
            current_sec = None
        elif current_sec and line_s.startswith("- "):
            sections.setdefault(current_sec, []).append(line_s)

    total_bullets = sum(len(items) for k, items in sections.items() if k != "links")
    if not force and total_bullets < min_points:
        print(f"[*] [[{note_file.stem}]] has only {total_bullets} points (Threshold: {min_points}+). Already short & concise. Skipping.")
        return False

    old_size_kb = len(content.encode("utf-8")) / 1024
    old_lines = len(lines)
    summary_stem = f"{note_file.stem} (خلاصه شده)"
    summary_file = note_file.parent / f"{summary_stem}.md"

    print(f"\n🧠 Synthesizing [[{note_file.stem}]] ({old_lines} lines, {old_size_kb:.1f} KB, {total_bullets} points)...")
    print(f"   -> Destination summary note: [[{summary_stem}]]")

    # 1. Synthesize Key Information & Rules
    rules_points = sections.get("rules", [])
    synth_rules = synthesize_points_section("Key Information & Rules", note_title, rules_points)

    # 2. Synthesize Tips & Experiences
    tips_points = sections.get("tips", [])
    synth_tips = synthesize_points_section("Tips & Experiences", note_title, tips_points)

    # 3. Synthesize Common Mistakes & Warnings
    mistakes_points = sections.get("mistakes", [])
    synth_mistakes = synthesize_points_section("Common Mistakes & Warnings", note_title, mistakes_points)

    # 4. Clean and deduplicate Related Notes wikilinks
    raw_links = re.findall(r"\[\[(.*?)\]\]", content)
    unique_links = set()
    for lk in raw_links:
        clean_lk = re.sub(r"[\[\]]", "", lk).strip()
        if clean_lk and clean_lk != note_file.stem and clean_lk != summary_stem and clean_lk != "00_Map_of_Content":
            unique_links.add(clean_lk)

    summary_links = [f"- [[{note_file.stem}]]"]
    for lk in sorted(unique_links):
        summary_links.append(f"- [[{lk}]]")
    links_md = "\n".join(summary_links)

    # Build tags for summary note cleanly from frontmatter
    tags_match = re.search(r"tags:\s*\n((?:\s*-\s*[^\n]+\n?)+)", frontmatter_yaml)
    if tags_match:
        t_matches = re.findall(r"-\s*([a-zA-Z0-9_\u0600-\u06FF]+)", tags_match.group(1))
        unique_tags = {t for t in t_matches if not t.isdigit() and len(t) > 1}
    else:
        unique_tags = set()
    unique_tags.add("summarized")
    tags_yaml = "\n".join(f"  - {t}" for t in sorted(unique_tags) if t)

    now_str = datetime.now().strftime("%Y-%m-%d")

    # Build assembled summary markdown
    summary_body = [
        "---",
        f'title: "{summary_stem}"',
        f'category: "{note_file.parent.name}"',
        f"created_at: {now_str}",
        f"updated_at: {now_str}",
        f'source_raw_note: "[[{note_file.stem}]]"',
        f"tags:",
        tags_yaml,
        "---",
        "",
        f"# {summary_stem}",
        "",
        f"> [!summary]",
        f"> {summary or 'نسخه خلاصه، پالایش‌شده و بدون تکرار تدوین‌شده بر اساس تاریخ وقایع.'}",
        "",
        f"> [!info] 📂 سند اصلی و جامع",
        f"> این یادداشت نسخه خلاصه، پالایش‌شده و بدون تکرار است. برای مشاهده تمامی جزئیات، تجربیات و متن کامل به یادداشت جامع [[{note_file.stem}]] مراجعه کنید.",
        "",
        "## 📌 Key Information & Rules",
        synth_rules or "- (No specific rules recorded)",
    ]

    if synth_tips:
        summary_body.extend(["", "## 💡 Tips & Experiences", synth_tips])
    if synth_mistakes:
        summary_body.extend(["", "## ⚠️ Common Mistakes & Warnings", synth_mistakes])

    summary_body.extend(["", "## 🔗 Related Notes", links_md, ""])

    new_content = "\n".join(summary_body)
    new_size_kb = len(new_content.encode("utf-8")) / 1024
    new_lines = len(new_content.splitlines())

    try:
        summary_file.write_text(new_content, encoding="utf-8")
        print(f"    ✨ Created Summary Note: [[{summary_stem}]] ({new_lines} lines, {new_size_kb:.1f} KB)")
    except Exception as e:
        print(f"[!] Error writing summary note: {e}")
        return False

    # Now, add callout banner to the original raw note pointing to this summary
    banner_callout = (
        f"> [!tip] 📌 نسخه خلاصه و دسته‌بندی‌شده\n"
        f"> برای مطالعه نسخه خلاصه، دسته‌بندی‌شده و بدون تکرار این راهنما همراه با تاریخ‌ها، یادداشت [[{summary_stem}]] را مشاهده کنید."
    )

    if f"[[{summary_stem}]]" not in content:
        # Insert banner right after summary block or title
        sum_match = re.search(r"(>\s*\[!summary\][^\n]*\n(?:>[^\n]*\n?)+)", content)
        if sum_match:
            end_pos = sum_match.end(1)
            updated_orig = content[:end_pos].rstrip() + "\n>\n" + banner_callout + "\n\n" + content[end_pos:].lstrip()
        else:
            title_m = re.search(r"(^#\s+[^\n]+\n)", content, re.MULTILINE)
            if title_m:
                end_pos = title_m.end(1)
                updated_orig = content[:end_pos] + "\n" + banner_callout + "\n\n" + content[end_pos:]
            else:
                updated_orig = banner_callout + "\n\n" + content

        try:
            note_file.write_text(updated_orig, encoding="utf-8")
            print(f"    🔗 Linked from original [[{note_file.stem}]] (Original {old_lines} lines kept 100% intact!)")
        except Exception as e:
            print(f"[!] Warning linking from original note: {e}")
    else:
        print(f"    🔗 Original [[{note_file.stem}]] already links to summary (Original {old_lines} lines kept 100% intact!)")

    return True


def synthesize_all_vault_notes(vault_dir: Path):
    """Iterate through all master notes in vault and synthesize those with accumulated points."""
    all_notes = []
    for cat_dir in sorted(vault_dir.iterdir()):
        if cat_dir.is_dir() and not cat_dir.name.startswith("."):
            for note_file in sorted(cat_dir.glob("*.md")):
                if "(خلاصه شده)" in note_file.name:
                    continue
                all_notes.append(note_file)

    if not all_notes:
        print("[!] No notes found in vault.")
        return

    default_thresh = 50
    thresh_input = input(f"\nEnter minimum points threshold to summarize (default {default_thresh}, notes below this are skipped): ").strip()
    min_points = int(thresh_input) if thresh_input.isdigit() and int(thresh_input) > 0 else default_thresh

    # 1. Automatically wipe all previous summaries and reset banners so we start with a clean slate
    print("\n[*] Deleting all previous summary notes and resetting banners before synthesizing...")
    clean_all_summary_notes(vault_dir, prompt_confirm=False)

    print("\n" + "=" * 65)
    print(f" 🚀 Deep Vault Synthesizer: Checking {len(all_notes)} notes (Threshold: >= {min_points} points)...")
    print(f" -> Notes with fewer than {min_points} points will remain untouched.")
    print("=" * 65)

    synthesized_count = 0
    skipped_count = 0
    for note in all_notes:
        success = synthesize_single_note(note, min_points=min_points, force=False)
        if success:
            synthesized_count += 1
            time.sleep(2)
        else:
            skipped_count += 1

    generate_map_of_content(vault_dir)
    print("\n" + "=" * 65)
    print(f" 🎉 Deep Synthesis Complete! Synthesized {synthesized_count} long notes (Skipped {skipped_count} short notes).")
    print("=" * 65)


def select_and_synthesize_note(vault_dir: Path):
    """List notes with their bullet point counts and let the user pick one to synthesize."""
    all_notes = []
    for cat_dir in sorted(vault_dir.iterdir()):
        if cat_dir.is_dir() and not cat_dir.name.startswith("."):
            for note_file in sorted(cat_dir.glob("*.md")):
                if "(خلاصه شده)" in note_file.name:
                    continue
                try:
                    text = note_file.read_text(encoding="utf-8")
                    bullets = sum(1 for line in text.splitlines() if line.strip().startswith("- "))
                    all_notes.append((note_file, bullets, len(text.encode("utf-8")) / 1024))
                except Exception:
                    pass

    if not all_notes:
        print("[!] No notes found in vault.")
        return

    # Sort by number of bullets descending
    all_notes.sort(key=lambda x: x[1], reverse=True)

    print("\nSelect a Note to Deeply Synthesize:")
    print("-" * 65)
    for idx, (nf, bullets, size_kb) in enumerate(all_notes, 1):
        if bullets >= 100:
            flag = " [🚨 High Redundancy - Recommended]"
        elif bullets >= 50:
            flag = " [⚡ Long Note - Recommended]"
        elif bullets >= 25:
            flag = " [⏳ Moderate]"
        else:
            flag = " [✅ Short - No summary needed]"
        print(f"{idx:2d}. {nf.stem[:48]:<48} | {bullets:4d} points | {size_kb:6.1f} KB{flag}")
    print("-" * 65)

    choice = input(f"Choose a note (1-{len(all_notes)}) or 0 to cancel: ").strip()
    if not choice.isdigit() or int(choice) < 1 or int(choice) > len(all_notes):
        return

    target_note = all_notes[int(choice) - 1][0]
    synthesize_single_note(target_note, force=True)
    generate_map_of_content(vault_dir)


def clean_all_summary_notes(vault_dir: Path, prompt_confirm: bool = True):
    """Delete all '(خلاصه شده)' notes and remove top banner callouts from original notes."""
    if prompt_confirm:
        print("\n" + "=" * 65)
        print(" 🗑️  CLEAN ALL SUMMARY NOTES (RESET)")
        print("=" * 65)
        confirm = input("Are you sure you want to delete all '(خلاصه شده)' notes and reset banners? (y/N): ").strip().lower()
        if confirm not in ("y", "yes"):
            print("[*] Cancelled.")
            return

    deleted = 0
    cleaned_orig = 0
    for cat_dir in vault_dir.iterdir():
        if cat_dir.is_dir() and not cat_dir.name.startswith("."):
            for md_file in list(cat_dir.glob("*.md")):
                if "(خلاصه شده)" in md_file.name:
                    try:
                        md_file.unlink()
                        deleted += 1
                    except Exception:
                        pass
                else:
                    try:
                        text = md_file.read_text(encoding="utf-8")
                        new_text = re.sub(r">\s*\[!tip\]\s*📌\s*نسخه خلاصه و دسته‌بندی‌شده[^\n]*\n(?:>[^\n]*\n?)*\n*", "", text)
                        if new_text != text:
                            md_file.write_text(new_text.strip() + "\n", encoding="utf-8")
                            cleaned_orig += 1
                    except Exception:
                        pass

    generate_map_of_content(vault_dir)
    print(f"[+] Reset complete: Deleted {deleted} previous summary files and reset banners on {cleaned_orig} master notes.")


def clean_broken_related_links(vault_dir: Path):
    """
    Scans every note in the vault and removes wikilinks from the '## 🔗 Related Notes'
    section that point to note files that do NOT actually exist in the vault.
    Only real [[links]] to existing .md files are kept.
    """
    print("\n" + "=" * 65)
    print(" 🔗 CLEAN BROKEN / EMPTY RELATED LINKS")
    print("=" * 65)

    # Build set of all existing note stems (case-folded for robust matching)
    existing_stems = set()
    for md_file in vault_dir.rglob("*.md"):
        if not md_file.name.startswith("."):
            existing_stems.add(md_file.stem.lower().strip())

    total_removed = 0
    total_notes_cleaned = 0

    for md_file in sorted(vault_dir.rglob("*.md")):
        if md_file.name.startswith("."):
            continue
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        # Locate the Related Notes section
        related_section_pattern = re.compile(
            r"(## 🔗 Related Notes[^\n]*\n)(.*?)(?=\n## |\Z)",
            re.DOTALL
        )
        match = related_section_pattern.search(content)
        if not match:
            continue

        section_header = match.group(1)
        section_body = match.group(2)

        # Process each line in the related notes section
        original_lines = section_body.splitlines(keepends=True)
        kept_lines = []
        removed_count = 0

        for line in original_lines:
            line_stripped = line.strip()

            # Extract all wikilinks on this line
            wikilinks = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", line_stripped)

            if not wikilinks:
                # No wikilink at all — it's a plain text keyword, remove it
                if line_stripped and not line_stripped.startswith("#"):
                    removed_count += 1
                    continue
                else:
                    kept_lines.append(line)
                    continue

            # Check if ANY wikilink on this line resolves to a real note
            has_real_link = any(
                wl.strip().lower() in existing_stems
                for wl in wikilinks
            )

            if has_real_link:
                kept_lines.append(line)
            else:
                removed_count += 1

        if removed_count > 0:
            new_body = "".join(kept_lines)
            new_content = content[:match.start(2)] + new_body + content[match.end(2):]

            # Clean up multiple consecutive blank lines left over
            new_content = re.sub(r"\n{3,}", "\n\n", new_content)

            try:
                md_file.write_text(new_content, encoding="utf-8")
                print(f"  [-] {md_file.name}: removed {removed_count} broken link(s)")
                total_removed += removed_count
                total_notes_cleaned += 1
            except Exception as e:
                print(f"  [!] Error writing {md_file.name}: {e}")

    print("\n" + "=" * 65)
    print(f" ✅ Done! Removed {total_removed} broken/empty links across {total_notes_cleaned} notes.")
    print("=" * 65)


def handle_consolidation_menu(vault_dir: Path):
    """Sub-menu for Vault Consolidation & Deep Note Synthesis."""
    while True:
        print("\n" + "=" * 65)
        print(" 🧹 VAULT CONSOLIDATOR & DEEP SYNTHESIZER")
        print("=" * 65)
        print("1. Deep Synthesize Long Notes Only (Default >= 50 points, skips short notes)")
        print("2. Deep Synthesize a Specific Note (Choose from list)")
        print("3. Merge Similar Note Files (Cluster separate files into Master Notes)")
        print("4. Clean/Reset All '(خلاصه شده)' Notes & Banners")
        print("5. Remove Broken/Empty Related Note Links (Non-Existent Wikilinks)")
        print("6. Back to Main Menu")
        print("=" * 65)

        sub_choice = input("Choose an option (1-6): ").strip()
        if sub_choice == "1":
            synthesize_all_vault_notes(vault_dir)
        elif sub_choice == "2":
            select_and_synthesize_note(vault_dir)
        elif sub_choice == "3":
            consolidate_vault(vault_dir)
        elif sub_choice == "4":
            clean_all_summary_notes(vault_dir)
        elif sub_choice == "5":
            clean_broken_related_links(vault_dir)
        elif sub_choice in ("6", "0", ""):
            break
        else:
            print("[!] Invalid option. Please enter 1-6.")


def unify_category_folders(vault_dir: Path):
    """Ensure all category folders use the canonical underscore naming convention."""
    space_to_underscore = {
        "Admission And Applications": "Admission_And_Applications",
        "Documents And Translation": "Documents_And_Translation",
        "General And FAQ": "General_And_FAQ",
        "Housing And Accommodation": "Housing_And_Accommodation",
        "Scholarships And Financial Aid": "Scholarships_And_Financial_Aid",
        "Visas And Immigration": "Visas_And_Immigration",
    }
    for space_name, under_name in space_to_underscore.items():
        space_path = vault_dir / space_name
        under_path = vault_dir / under_name
        if space_path.exists() and space_path.is_dir():
            under_path.mkdir(parents=True, exist_ok=True)
            for f in list(space_path.glob("*.md")):
                target = under_path / f.name
                if target.exists() and target.resolve() != f.resolve():
                    target_temp = under_path / f"__temp_merge__{f.name}"
                    shutil.move(str(f), str(target_temp))
                else:
                    shutil.move(str(f), str(target))
            try:
                space_path.rmdir()
                print(f"[+] Unified category folder: '{space_name}' -> '{under_name}'")
            except Exception:
                pass


def consolidate_vault(vault_dir: Path):
    """
    Scans the vault for fragmented / duplicate notes and consolidates them
    into rich master guides without losing any points.
    """
    print("\n" + "=" * 65)
    print(" 🧹 VAULT CONSOLIDATOR: Merging Same-Topic Notes (Zero-Loss)")
    print("=" * 65)

    # 1. Unify any folders with spaces into canonical underscore folders
    unify_category_folders(vault_dir)

    categories = [d for d in vault_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
    if not categories:
        print("No category folders found in vault.")
        return

    total_merged = 0
    all_deleted_stems_map = {}

    for cat_dir in categories:
        notes = [n for n in cat_dir.glob("*.md") if "(خلاصه شده)" not in n.name]
        if len(notes) <= 1:
            continue

        cat_name = cat_dir.name.replace("_", " ")
        print(f"\nAnalyzing category '{cat_name}' ({len(notes)} master notes)...")

        note_titles = [n.stem for n in notes]
        clustering_prompt = f"""
Here are {len(note_titles)} note titles from the category '{cat_name}':
{json.dumps(note_titles, ensure_ascii=False, indent=2)}

Analyze these note titles and group notes that cover the EXACT SAME subject, domain, or process into cohesive Master Topics.
For each master topic, provide a clean, descriptive master title in the same language as the notes, and list the note titles that should be merged into it.
Notes that are independent or cover distinct topics must NOT be forced together; only merge notes that are variations, fragments, or subsets of the same topic.

Output ONLY a JSON object where keys are the Master Topic Titles, and values are arrays of existing note titles to merge:
{{
  "Master Topic Title": ["Existing Note Title 1", "Existing Note Title 2"]
}}
"""
        raw = call_gemini(clustering_prompt)
        if not raw:
            continue

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            clusters = json.loads(cleaned)
        except Exception:
            print("[!] Could not parse cluster response for this category. Skipping.")
            continue

        for master_title, note_list in clusters.items():
            if len(note_list) <= 1:
                continue

            master_safe = sanitize_filename(master_title)
            master_file = cat_dir / f"{master_safe}.md"

            print(f"  -> Merging {len(note_list)} notes into Master Guide: [[{master_safe}]]")

            combined_points = []
            combined_tips = []
            combined_mistakes = []
            combined_links = set()
            combined_tags = set()
            combined_custom = {}
            master_summary = ""

            for n_title in note_list:
                src_path = cat_dir / f"{sanitize_filename(n_title)}.md"
                if not src_path.exists():
                    # Check without extension or with temp prefix
                    candidates = list(cat_dir.glob(f"*{sanitize_filename(n_title)}*.md"))
                    if candidates:
                        src_path = candidates[0]
                    else:
                        continue

                text = src_path.read_text(encoding="utf-8")

                # Extract summary
                if not master_summary:
                    s_match = re.search(r">\s*\[!summary\]\s*\n>\s*([^\n]+)", text)
                    if s_match:
                        master_summary = s_match.group(1).strip()

                # Extract tags
                tags_block = re.search(r"tags:\s*\n((?:\s*-\s*[^\n]+\n?)+)", text[:400])
                if tags_block:
                    t_matches = re.findall(r"-\s*([a-zA-Z0-9_\u0600-\u06FF]+)", tags_block.group(1))
                    combined_tags.update(t for t in t_matches if not t.isdigit() and len(t) > 1)

                # Extract sections with full zero-loss fidelity
                lines = text.splitlines()
                current_section = None
                custom_header = None
                for line in lines:
                    line_s = line.strip()
                    if line_s.startswith("## 📌") or "نکات کلیدی" in line_s or "Key Information" in line_s:
                        current_section = "points"
                        custom_header = None
                        continue
                    elif line_s.startswith("## 💡") or "نکات و تجربیات" in line_s or "Tips & Experiences" in line_s:
                        current_section = "tips"
                        custom_header = None
                        continue
                    elif line_s.startswith("## ⚠️") or "اشتباهات رایج" in line_s or "Common Mistakes" in line_s:
                        current_section = "mistakes"
                        custom_header = None
                        continue
                    elif line_s.startswith("## 🔗") or "یادداشت‌های مرتبط" in line_s or "Related Notes" in line_s:
                        current_section = "links"
                        custom_header = None
                        continue
                    elif line_s.startswith("## "):
                        current_section = "custom"
                        custom_header = line_s
                        combined_custom.setdefault(custom_header, [])
                        continue

                    if not line_s or line_s.startswith("---") or line_s.startswith("> [!summary]") or line_s.startswith("> [!tip]") or line_s.startswith("# "):
                        continue

                    if current_section == "points":
                        combined_points.append(line_s[2:].strip() if line_s.startswith("- ") else line_s)
                    elif current_section == "tips":
                        combined_tips.append(line_s[2:].strip() if line_s.startswith("- ") else line_s)
                    elif current_section == "mistakes":
                        item_text = line_s[2:].strip() if line_s.startswith("- ") else line_s
                        combined_mistakes.append(re.sub(r"^⚠️\s*", "", item_text))
                    elif current_section == "links":
                        combined_links.add(line_s)
                    elif current_section == "custom" and custom_header:
                        combined_custom[custom_header].append(line)

                # Remove merged source file if different from master
                if src_path.resolve() != master_file.resolve():
                    all_deleted_stems_map[src_path.stem] = master_safe
                    try:
                        src_path.unlink()
                        total_merged += 1
                    except Exception:
                        pass

                    # Clean up old companion summary note if present
                    old_summary = cat_dir / f"{src_path.stem} (خلاصه شده).md"
                    if old_summary.exists():
                        try:
                            old_summary.unlink()
                        except Exception:
                            pass

            # Zero-Loss Deduplication: Only drop 100% identical normalized sentences
            def dedupe_zero_loss(items):
                seen = set()
                out = []
                for it in items:
                    norm = normalize_point_for_dedupe(it)
                    if not norm:
                        continue
                    if norm not in seen:
                        seen.add(norm)
                        out.append(it)
                return out

            deduped_points = dedupe_zero_loss(combined_points)
            deduped_tips = dedupe_zero_loss(combined_tips)
            deduped_mistakes = dedupe_zero_loss(combined_mistakes)

            tags_yaml = "\n".join(f"  - {t}" for t in sorted(combined_tags) if t) if combined_tags else "  - master_guide"
            points_md = "\n".join(f"- {p}" for p in deduped_points) if deduped_points else "- (اطلاعات و قوانین استخراج شده)"
            tips_md = "\n".join(f"- {t}" for t in deduped_tips) if deduped_tips else ""
            mistakes_md = "\n".join(f"- ⚠️ {m}" for m in deduped_mistakes) if deduped_mistakes else ""
            links_md = "\n".join(f"{l}" for l in sorted(combined_links) if l) if combined_links else "- [[00_Map_of_Content]]"

            now_str = datetime.now().strftime("%Y-%m-%d")

            master_content = f"""---
title: "{master_safe}"
category: "{cat_dir.name}"
updated_at: {now_str}
tags:
{tags_yaml}
---

# {master_safe}

> [!summary]
> {master_summary or 'Master consolidated knowledge guide synthesized from Telegram archives.'}

## 📌 Key Information & Rules
{points_md}
"""
            if tips_md:
                master_content += f"\n## 💡 Tips & Experiences\n{tips_md}\n"
            if mistakes_md:
                master_content += f"\n## ⚠️ Common Mistakes & Warnings\n{mistakes_md}\n"

            for c_sec, c_lines in combined_custom.items():
                c_text = "\n".join(c_lines).strip()
                if c_text:
                    master_content += f"\n{c_sec}\n{c_text}\n"

            master_content += f"\n## 🔗 Related Notes\n{links_md}\n"

            master_file.write_text(master_content, encoding="utf-8")

    # Vault-wide Wikilink refactoring
    if all_deleted_stems_map:
        for md_file in vault_dir.rglob("*.md"):
            if md_file.name.startswith("."):
                continue
            try:
                content = md_file.read_text(encoding="utf-8")
                orig_content = content
                for old_stem, new_stem in all_deleted_stems_map.items():
                    if f"[[{old_stem}]]" in content:
                        content = content.replace(f"[[{old_stem}]]", f"[[{new_stem}]]")
                    if f"[[{old_stem}|" in content:
                        content = content.replace(f"[[{old_stem}|", f"[[{new_stem}|")
                if content != orig_content:
                    md_file.write_text(content, encoding="utf-8")
            except Exception:
                pass

    generate_map_of_content(vault_dir)
    print("\n" + "=" * 65)
    print(f" 🎉 Consolidation complete! Merged {total_merged} fragmented notes into master guides.")
    print("=" * 65)


def process_chat_file(file_path: Path):
    """
    Main Brain-in-the-Loop pipeline:
    1. Loads Telegram chat archive
    2. Identifies if this is an incremental update (new messages since last run)
       or an initial / resumed full-archive run.
    3. Feeds existing brain catalog + conversation batch to Gemini
    4. Gemini updates existing notes or creates new ones
    5. Every bullet point is date-stamped **[YYYY-MM-DD]**
    6. Saves progress checkpoints with exact message ID boundaries
    """
    global CURRENT_MODEL_INDEX
    print(f"\nLoading chat file: {file_path.name}...")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[!] Failed to read {file_path}: {e}")
        return

    all_messages = data.get("messages", [])
    total_raw = len(all_messages)
    print(f"Total messages in file: {total_raw:,}")

    checkpoint = load_checkpoint(file_path)
    last_message_id = checkpoint.get("last_message_id", 0) if checkpoint else 0
    cp_batch = checkpoint.get("current_batch", 0) if checkpoint else 0
    cp_total = checkpoint.get("total_batches", 0) if checkpoint else 0
    total_ops = checkpoint.get("ops_count", 0) if checkpoint else 0

    # Determine mode: Incremental Update vs Initial / Paused Run
    is_incremental = (last_message_id > 0 and cp_batch >= cp_total)

    if is_incremental:
        # Find messages newer than last_message_id
        new_raw_messages = [m for m in all_messages if m.get("message_id", 0) > last_message_id]

        if not new_raw_messages:
            print("\n" + "=" * 65)
            print(" ✅ Second Brain is already completely up to date!")
            print(f" -> All messages up to Message ID {last_message_id} are in the vault.")
            print(" -> No new messages found in this chat archive.")
            print(" -> Run 'main.py' (Option 2) to sync newer messages from Telegram first.")
            print("=" * 65)
            return

        print("\n" + "=" * 65)
        print(" 🔄 Incremental Second Brain Update:")
        print(f" -> Previously processed up to Message ID: {last_message_id}")
        print(f" -> Found {len(new_raw_messages):,} NEW messages arrived since last run!")
        print("=" * 65)

        # Filter noise on new messages
        filtered = []
        for m in new_raw_messages:
            text = m.get("text", "")
            if not is_chatter(text):
                date_str = m.get("date", "")[:10]
                sender = m.get("sender_name", "User")
                filtered.append({
                    "id": m.get("message_id", 0),
                    "text": f"[{date_str}] {sender}: {text}"
                })

        print(f"Retained new messages: {len(filtered):,} (filtered out {len(new_raw_messages) - len(filtered):,} chatter)")

        if not filtered:
            print("[*] All new messages were greetings or chatter. Updating checkpoint to latest message ID.")
            highest_id = new_raw_messages[-1].get("message_id", last_message_id)
            save_checkpoint(file_path, cp_total + 1, cp_total + 1, total_ops, last_message_id=highest_id)
            return

        batch_size = 800
        total_batches = (len(filtered) + batch_size - 1) // batch_size
        start_batch = 0
        batch_offset = cp_total

    else:
        # Initial run or resuming a paused mid-run
        filtered = []
        for m in all_messages:
            text = m.get("text", "")
            if not is_chatter(text):
                date_str = m.get("date", "")[:10]
                sender = m.get("sender_name", "User")
                filtered.append({
                    "id": m.get("message_id", 0),
                    "text": f"[{date_str}] {sender}: {text}"
                })

        print(f"Retained messages: {len(filtered):,} (filtered out {total_raw - len(filtered):,} chatter)")

        if not filtered:
            print("[!] No meaningful content found.")
            return

        default_batch_size = 800
        batch_input = input(f"\nEnter batch size (messages per AI call, default {default_batch_size}): ").strip()
        batch_size = int(batch_input) if batch_input.isdigit() and int(batch_input) > 50 else default_batch_size

        total_batches = (len(filtered) + batch_size - 1) // batch_size
        start_batch = 0
        batch_offset = 0

        if checkpoint and cp_batch > 0 and cp_batch < cp_total:
            print("\n" + "=" * 60)
            print(f" 🔄 Found paused progress for this file:")
            print(f" -> Completed {cp_batch}/{cp_total} batches.")
            print("=" * 60)
            res = input("Resume from where you paused? (Y/n): ").strip().lower()
            if res not in ("n", "no"):
                start_batch = cp_batch

    # Run batches
    print("\n" + "=" * 65)
    print(f" Starting Brain-in-the-Loop Extraction ({CANDIDATE_MODELS[CURRENT_MODEL_INDEX]})")
    print(f" -> Total batches to process: {total_batches - start_batch} (Batch {start_batch + 1} to {total_batches})")
    print(f" -> Brain State: Injected dynamically into every AI prompt")
    print(f" -> Date Stamping: Every bullet point prefixed with **[YYYY-MM-DD]**")
    print(f" -> Press Ctrl+C anytime to pause (progress is auto-saved)")
    print("=" * 65)

    batch_idx = start_batch
    try:
        while batch_idx < total_batches:
            batch = filtered[batch_idx * batch_size : (batch_idx + 1) * batch_size]
            conversation_text = "\n\n".join(item["text"] for item in batch)
            batch_max_id = max(item["id"] for item in batch)

            chunk_success = False
            max_chunk_retries = 4

            for chunk_attempt in range(max_chunk_retries):
                current_model = CANDIDATE_MODELS[CURRENT_MODEL_INDEX]
                attempt_str = f" (Attempt {chunk_attempt + 1}/{max_chunk_retries})" if chunk_attempt > 0 else ""
                print(f"\n[Batch {batch_idx + 1}/{total_batches}]{attempt_str} Processing {len(batch)} messages with Gemini ({current_model})...")

                # Extract dynamic brain catalog
                brain_catalog = get_brain_catalog(VAULT_DIR)

                user_prompt = f"""{SYSTEM_PROMPT}

CURRENT BRAIN CATALOG (Existing Notes in Vault):
===
{brain_catalog}
===

TELEGRAM CONVERSATION BATCH:
---
{conversation_text}
---
"""

                raw_response = call_gemini(user_prompt)
                if not raw_response:
                    print(f"[!] No response from {current_model}. Switching model and retrying...")
                    CURRENT_MODEL_INDEX = (CURRENT_MODEL_INDEX + 1) % len(CANDIDATE_MODELS)
                    time.sleep(3)
                    continue

                cleaned_json = raw_response.strip()
                if cleaned_json.startswith("```"):
                    cleaned_json = re.sub(r"^```(?:json)?\s*", "", cleaned_json)
                    cleaned_json = re.sub(r"\s*```$", "", cleaned_json)

                operations = None
                try:
                    operations = json.loads(cleaned_json)
                except json.JSONDecodeError:
                    repaired = repair_json_array(cleaned_json)
                    try:
                        operations = json.loads(repaired)
                        print(f"[*] Repaired truncated JSON response for batch {batch_idx + 1}.")
                    except Exception:
                        operations = None

                if operations and isinstance(operations, list) and len(operations) > 0:
                    for op in operations:
                        save_or_update_note(VAULT_DIR, op, file_path.name)
                        total_ops += 1
                    chunk_success = True
                    break
                else:
                    print(f"[!] Chunk error in batch {batch_idx + 1}. Retrying chunk with next model...")
                    CURRENT_MODEL_INDEX = (CURRENT_MODEL_INDEX + 1) % len(CANDIDATE_MODELS)
                    time.sleep(3)

            if chunk_success:
                batch_idx += 1
                save_checkpoint(
                    file_path=file_path,
                    current_batch=batch_offset + batch_idx,
                    total_batches=batch_offset + total_batches,
                    ops_count=total_ops,
                    last_message_id=batch_max_id
                )
            else:
                print(f"\n[!] Batch {batch_idx + 1} failed after {max_chunk_retries} attempts.")
                save_checkpoint(
                    file_path=file_path,
                    current_batch=batch_offset + batch_idx,
                    total_batches=batch_offset + total_batches,
                    ops_count=total_ops,
                    last_message_id=last_message_id
                )
                retry_choice = input("Press [Enter] to try again, 's' to skip, or 'q' to pause: ").strip().lower()
                if retry_choice == "q":
                    print("[*] Pausing extraction. You can resume anytime from the main menu.")
                    break
                elif retry_choice == "s":
                    batch_idx += 1
                else:
                    time.sleep(2)
                    continue

            # Update MOC every 5 batches
            if batch_idx % 5 == 0:
                generate_map_of_content(VAULT_DIR)

            # Free tier polite delay
            time.sleep(3)

    except KeyboardInterrupt:
        print(f"\n\n[!] Paused by user. Batch {batch_idx} progress saved to checkpoint!")
        save_checkpoint(file_path, batch_offset + batch_idx, batch_offset + total_batches, total_ops, last_message_id)
    except Exception as e:
        print(f"\n[!] Unexpected error: {e}")
        save_checkpoint(file_path, batch_offset + batch_idx, batch_offset + total_batches, total_ops, last_message_id)

    generate_map_of_content(VAULT_DIR)

    print("\n" + "=" * 65)
    print(" 🎉 FINISHED! Your Living Second Brain is up to date!")
    print(f" 📂 Vault Location: {VAULT_DIR}")
    print("=" * 65)


def main():
    check_api_key()

    while True:
        print("\n" + "=" * 65)
        print(" 🧠 Obsidian Second Brain Builder & Knowledge Consolidator")
        print("=" * 65)
        print("1. Process Telegram Chat into Second Brain (Brain-in-the-Loop)")
        print("2. Consolidate & Merge Existing Fragmented Notes in Vault")
        print("3. Regenerate 00_Map_of_Content.md Dashboard")
        print("4. Export Vault to Standalone Offline HTML (Shareable Guide)")
        print("5. Exit")
        print("=" * 65)

        choice = input("Choose an option (1-5): ").strip()

        if choice == "1":
            if not EXPORTS_DIR.exists():
                print(f"[ERROR] Synced chats directory not found: {EXPORTS_DIR}")
                continue

            json_files = list(EXPORTS_DIR.glob("*.json"))
            if not json_files:
                print("[!] No synced chat JSON files found. Run 'main.py' first to export your chats.")
                continue

            print("\nSelect Chat Archive to Convert:")
            for idx, f in enumerate(json_files, 1):
                size_mb = f.stat().st_size / (1024 * 1024)
                cp = load_checkpoint(f)
                status = ""
                if cp:
                    last_id = cp.get("last_message_id", 0)
                    cp_b = cp.get("current_batch", 0)
                    cp_t = cp.get("total_batches", 0)
                    if last_id > 0 and cp_b >= cp_t:
                        try:
                            with open(f, "r", encoding="utf-8") as jf:
                                jdata = json.load(jf)
                            new_count = sum(1 for m in jdata.get("messages", []) if m.get("message_id", 0) > last_id)
                            if new_count > 0:
                                status = f" [🔄 {new_count} new messages pending]"
                            else:
                                status = " [✅ Up to date]"
                        except Exception:
                            status = " [✅ Up to date]"
                    else:
                        status = f" [Resume: {cp_b}/{cp_t} batches]"
                print(f"{idx}. {f.name} ({size_mb:.2f} MB){status}")

            f_choice = input(f"\nChoose a file (1-{len(json_files)}) or 0 to back: ").strip()
            if f_choice in ("0", ""):
                continue

            if f_choice.isdigit() and 1 <= int(f_choice) <= len(json_files):
                selected_file = json_files[int(f_choice) - 1]
                process_chat_file(selected_file)

        elif choice == "2":
            handle_consolidation_menu(VAULT_DIR)

        elif choice == "3":
            generate_map_of_content(VAULT_DIR)

        elif choice == "4":
            try:
                from export_vault_to_html import export_vault
                export_vault()
            except Exception as e:
                print(f"[!] Error during HTML export: {e}")

        elif choice in ("5", "0", "exit", "q"):
            print("\nGoodbye!")
            break

        else:
            print("[!] Invalid option. Please enter 1-5.")


if __name__ == "__main__":
    main()
