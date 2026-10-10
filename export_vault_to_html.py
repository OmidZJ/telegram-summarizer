"""
Obsidian Second Brain -> Standalone Offline Interactive HTML Exporter
====================================================================
Exports the entire Obsidian Knowledge Base into a single, self-contained,
zero-dependency offline HTML file that looks and feels like Obsidian.

Features:
- 100% Offline: Zero external CDN dependencies (fonts, styles, icons, and logic all inline).
- First-Vocab BiDi Engine: Dynamically assigns RTL or LTR to each block based on the first letter/word.
- Full PDF Export Option: One-click export of all notes into a complete book-format PDF.
- Single Note PDF Print: Quick print for individual notes.
- Default Light Theme with Dark Theme toggle (persisted in localStorage).
- Safe Wikilink Navigation: Handles quotes, apostrophes, and special characters cleanly.
- Hierarchical category tree explorer with collapsible folders and note count badges.
- Instant search across titles, categories, tags, and note content (Ctrl+K).
- Full Obsidian Callouts ([!summary], [!tip], [!info], [!warning], etc.).
- Direct quick-switcher between Master Notes and Companion (خلاصه شده) Summaries.
- Shareable as a single .html file over Telegram, WhatsApp, Email, or USB.
"""

import json
import os
import re
import sys
import html
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
import markdown

# Fix Windows console encoding for Persian/Unicode text
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Setup base paths
BASE_DIR = Path(__file__).resolve().parent
VAULT_DIR = BASE_DIR / "Obsidian_Vault"
EXPORTS_DIR = BASE_DIR / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE_EXPORTS = EXPORTS_DIR / "Second_Brain_Knowledge_Base.html"
OUTPUT_TEX_EXPORTS = EXPORTS_DIR / "Second_Brain_Knowledge_Base.tex"
OUTPUT_PDF_EXPORTS = EXPORTS_DIR / "Second_Brain_Knowledge_Base.pdf"

OUTPUT_FILE_VAULT = VAULT_DIR / "Second_Brain_Knowledge_Base.html"
OUTPUT_TEX_VAULT = VAULT_DIR / "Second_Brain_Knowledge_Base.tex"
OUTPUT_PDF_VAULT = VAULT_DIR / "Second_Brain_Knowledge_Base.pdf"


def get_category_display(category_raw: str) -> str:
    """Dynamically format directory names into clean, human-readable category titles."""
    if not category_raw or category_raw == "Obsidian_Vault":
        return "فهرست مطالب"
    if category_raw == "Report_Cluster":
        return "Report Cluster (گزارش‌های تخصصی)"
    clean = category_raw.replace("_", " ").strip()
    clean = re.sub(r"\bAnd\b", "&", clean)
    return clean


# SVG Icons for Callouts & UI
ICONS = {
    "summary": """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>""",
    "tip": """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"></path></svg>""",
    "info": """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>""",
    "warning": """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>""",
    "note": """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg>""",
}


def sanitize_id(title: str) -> str:
    """Generate a clean URL-safe slug ID for each note."""
    s = title.strip().lower()
    s = re.sub(r"[^\w\u0600-\u06FF]+", "-", s)
    return s.strip("-") or "note"


def parse_frontmatter(content: str):
    """Extract YAML frontmatter and body."""
    meta = {
        "title": "",
        "category": "",
        "created_at": "",
        "updated_at": "",
        "tags": [],
        "source_raw_note": "",
    }
    body = content

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", content, re.DOTALL)
    if match:
        yaml_text = match.group(1)
        body = content[match.end():]

        # Title
        t_match = re.search(r'^title:\s*["\']?(.*?)["\']?\s*$', yaml_text, re.MULTILINE)
        if t_match:
            meta["title"] = t_match.group(1).strip()

        # Category
        c_match = re.search(r'^category:\s*["\']?(.*?)["\']?\s*$', yaml_text, re.MULTILINE)
        if c_match:
            meta["category"] = c_match.group(1).strip()

        # Created / Updated
        cr_match = re.search(r'^created_at:\s*["\']?(.*?)["\']?\s*$', yaml_text, re.MULTILINE)
        if cr_match:
            meta["created_at"] = cr_match.group(1).strip()

        up_match = re.search(r'^updated_at:\s*["\']?(.*?)["\']?\s*$', yaml_text, re.MULTILINE)
        if up_match:
            meta["updated_at"] = up_match.group(1).strip()

        src_match = re.search(r'^source_raw_note:\s*["\']?(.*?)["\']?\s*$', yaml_text, re.MULTILINE)
        if src_match:
            meta["source_raw_note"] = re.sub(r"[\[\]]", "", src_match.group(1)).strip()

        # Tags
        tags_block = re.search(r"tags:\s*\n((?:\s*-\s*[^\n]+\n?)+)", yaml_text)
        if tags_block:
            raw_tags = re.findall(r"-\s*([a-zA-Z0-9_\u0600-\u06FF]+)", tags_block.group(1))
            meta["tags"] = [t for t in sorted(set(raw_tags)) if not t.isdigit() and len(t) > 1]

    return meta, body


def preprocess_markdown(text: str, current_note_stem: str) -> str:
    """Preprocess Obsidian Callouts, Dates, and Wikilinks before markdown parsing."""
    lines = text.splitlines()
    processed_lines = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        # Detect Obsidian callout header: > [!type] Title
        callout_m = re.match(r"^>\s*\[!([a-zA-Z0-9_-]+)\]\s*(.*)$", line.strip())
        if callout_m:
            c_type = callout_m.group(1).lower()
            c_title = callout_m.group(2).strip()
            if not c_title:
                if c_type == "summary":
                    c_title = "خلاصه راهنما"
                elif c_type == "tip":
                    c_title = "نکته کلیدی و مهم"
                elif c_type == "info":
                    c_title = "اطلاعات تکمیلی"
                elif c_type in ("warning", "caution"):
                    c_title = "هشدار و نکات احتیاطی"
                else:
                    c_title = c_type.capitalize()

            callout_body_lines = []
            i += 1
            while i < n and (lines[i].strip().startswith(">") or lines[i].strip() == ""):
                b_line = lines[i].strip()
                if b_line.startswith(">"):
                    b_line = b_line[1:].strip()
                callout_body_lines.append(b_line)
                i += 1

            icon_svg = ICONS.get(c_type, ICONS["note"])
            body_md = "\n".join(callout_body_lines).strip()

            processed_lines.append(f"""<div class="callout callout-{c_type}">
<div class="callout-header"><span class="callout-icon">{icon_svg}</span><span class="callout-title">{c_title}</span></div>
<div class="callout-body">
{body_md}
</div>
</div>""")
            continue
        else:
            processed_lines.append(line)
            i += 1

    content = "\n".join(processed_lines)

    # Transform Wikilinks safely without inline onclick strings (prevents single-quote breakage)
    def replace_wikilink(m):
        raw = m.group(1)
        if "|" in raw:
            target, display = raw.split("|", 1)
        else:
            target, display = raw, raw
        target = target.strip()
        display = display.strip()
        slug = sanitize_id(target)
        escaped_target = html.escape(target, quote=True)
        escaped_display = html.escape(display)
        return f'<a href="#{slug}" class="wikilink" data-stem="{escaped_target}">{escaped_display}</a>'

    content = re.sub(r"\[\[(.*?)\]\]", replace_wikilink, content)

    # Highlight Dates like (2026-06-27, 2026-08-30) or **[2026-06-27]**
    def replace_dates(m):
        inner = m.group(1)
        dates = [d.strip() for d in inner.split(",") if re.match(r"^\d{4}-\d{2}-\d{2}$", d.strip())]
        if dates:
            badges = "".join(f'<span class="date-chip">📅 {d}</span>' for d in dates)
            return f'<span class="date-group">{badges}</span>'
        return m.group(0)

    content = re.sub(r"\(((?:\d{4}-\d{2}-\d{2})(?:\s*,\s*\d{4}-\d{2}-\d{2})*)\)", replace_dates, content)
    content = re.sub(r"\*\*\[(\d{4}-\d{2}-\d{2})\]\*\*", r'<span class="date-chip">📅 \1</span>', content)

    # Transform Telegram message links [💬 #12345](https://t.me/...) into stylish pill links
    def replace_telegram_link(m):
        raw_num = m.group(1).strip().lstrip("#")
        url = m.group(2).strip()
        clean_url = html.escape(url, quote=True)
        return f'<a href="{clean_url}" target="_blank" rel="noopener noreferrer" class="telegram-msg-link" title="مشاهده پیام اصلی در تلگرام">💬 #{raw_num}</a>'

    content = re.sub(r"\[(?:💬\s*)?#?(\d+)\]\((https?://t\.me/[^\)]+)\)", replace_telegram_link, content)

    return content


def assign_bidi_direction(html_text: str) -> str:
    """
    Decides text direction (RTL or LTR) for each block (h1-h5, p, li, blockquote)
    based on the first alphabetical letter/word (ignoring leading emojis, numbers, and symbols).
    """
    def replace_tag(m):
        tag = m.group(1).lower()
        attrs = m.group(2) or ""
        inner = m.group(3)

        # Extract pure plain text by stripping HTML tags
        plain = re.sub(r"<[^>]+>", "", inner).strip()
        # Remove leading emojis, bullets, numbers, and symbols to find the first actual word/letter
        clean_text = re.sub(r"^[📁🧠📌⚡💡⚠️❌🧭\s\d\(\)\[\]\.\,\:\*\#\-\–\—\|]+", "", plain).strip()

        # Find first Persian or Latin letter
        letter_match = re.search(r"([a-zA-Z]|[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF])", clean_text)
        if letter_match:
            char = letter_match.group(1)
            # If Latin/English letter -> LTR
            if re.match(r"[a-zA-Z]", char):
                dir_val = "ltr"
            else:
                dir_val = "rtl"
        else:
            dir_val = "rtl"

        # Remove existing dir or class attributes if present
        attrs_clean = re.sub(r'\s*dir=["\'][^"\']*["\']', '', attrs)
        attrs_clean = re.sub(r'\s*class=["\'][^"\']*["\']', '', attrs_clean)

        return f'<{tag} dir="{dir_val}" class="bidi-{dir_val}"{attrs_clean}>{inner}</{tag}>'

    pattern = re.compile(r"<(h[1-5]|p|li|blockquote)(\s+[^>]*)?>(.*?)</\1>", re.DOTALL | re.IGNORECASE)
    return pattern.sub(replace_tag, html_text)


def build_notes_dataset():
    """Scan Obsidian_Vault and parse all Markdown notes into rich objects supporting Group Clusters."""
    all_notes = []
    vault_notes = list(VAULT_DIR.rglob("*.md"))

    # Map of note stem to file
    notes_by_stem = {f.stem: f for f in vault_notes}

    for md_file in vault_notes:
        if ".obsidian" in md_file.parts:
            continue

        raw_text = md_file.read_text(encoding="utf-8", errors="replace")
        meta, body_md = parse_frontmatter(raw_text)

        rel_path = md_file.relative_to(VAULT_DIR)

        # Check hierarchy depth for Group Clusters vs Flat Categories
        if len(rel_path.parts) >= 3:
            # Group Cluster / Subcluster / Note.md
            group_raw = rel_path.parts[0]
            subcluster_raw = rel_path.parts[1]
            group_display = get_category_display(group_raw)
            subcluster_display = get_category_display(subcluster_raw)
            category_raw = subcluster_raw
            category_display = f"{group_display} ➔ {subcluster_display}"
        elif len(rel_path.parts) == 2:
            # Category / Note.md
            group_raw = ""
            group_display = ""
            subcluster_raw = rel_path.parts[0]
            subcluster_display = get_category_display(subcluster_raw)
            category_raw = subcluster_raw
            category_display = subcluster_display
        else:
            # Root note
            group_raw = ""
            group_display = ""
            subcluster_raw = ""
            subcluster_display = "فهرست مطالب"
            category_raw = "Map_of_Content"
            category_display = "فهرست مطالب"

        title = meta.get("title") or md_file.stem

        is_summary = "(خلاصه شده)" in md_file.stem
        is_root_moc = (md_file.resolve() == (VAULT_DIR / "00_Map_of_Content.md").resolve())
        is_moc = is_root_moc

        if is_root_moc:
            title = "فهرست مطالب اصلی"
        elif md_file.name == "00_Map_of_Content.md" and group_display:
            title = f"فهرست مطالب: {group_display}"

        # Check companions within the same folder first, then global
        master_stem = None
        summary_stem = None
        if is_summary:
            potential_master = md_file.stem.replace(" (خلاصه شده)", "").strip()
            if (md_file.parent / f"{potential_master}.md").exists() or potential_master in notes_by_stem:
                master_stem = potential_master
        else:
            potential_summary = f"{md_file.stem} (خلاصه شده)"
            if (md_file.parent / f"{potential_summary}.md").exists() or potential_summary in notes_by_stem:
                summary_stem = potential_summary

        # Preprocess and render HTML
        preprocessed = preprocess_markdown(body_md, md_file.stem)
        rendered_html = markdown.markdown(
            preprocessed,
            extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
        )

        # Apply BiDi Direction based on the first letter/word of each block
        rendered_html = assign_bidi_direction(rendered_html)

        # Word count & reading time
        plain_words = re.findall(r"[\w\u0600-\u06FF]+", raw_text)
        word_count = len(plain_words)
        reading_time_mins = max(1, round(word_count / 180))

        # Count bullet points
        bullet_count = sum(1 for line in raw_text.splitlines() if line.strip().startswith("- ") or line.strip().startswith("* "))

        note_slug_id = sanitize_id(f"{group_raw}_{md_file.stem}" if group_raw and md_file.stem.startswith("00_") else md_file.stem)

        all_notes.append({
            "id": note_slug_id,
            "stem": md_file.stem,
            "title": title,
            "group": group_raw,
            "group_display": group_display,
            "subcluster": subcluster_raw,
            "subcluster_display": subcluster_display,
            "category": category_raw,
            "category_display": category_display,
            "is_summary": is_summary,
            "is_moc": is_moc,
            "master_stem": master_stem,
            "summary_stem": summary_stem,
            "created_at": meta.get("created_at") or "",
            "updated_at": meta.get("updated_at") or "",
            "tags": meta.get("tags") or [],
            "source_raw_note": meta.get("source_raw_note") or "",
            "word_count": word_count,
            "reading_time": reading_time_mins,
            "bullet_count": bullet_count,
            "body_md": body_md,
            "html": rendered_html,
        })

    # Sort notes: Root MOC first, then by category_display, then by title
    def sort_key(n):
        if n["is_moc"]:
            return ("000", "", "")
        return (n["category_display"], 1 if n["is_summary"] else 0, n["title"])

    all_notes.sort(key=sort_key)
    return all_notes


# ==============================================================================
# Markdown -> LaTeX (XePersian) Book Generator & Compiler
# ==============================================================================

def text_to_latex(text: str) -> str:
    """Escape LaTeX special characters in plain text."""
    replacements = [
        ('&', r'\&'),
        ('%', r'\%'),
        ('$', r'\$'),
        ('#', r'\#'),
        ('_', r'\_'),
        ('{', r'\{'),
        ('}', r'\}'),
        ('~', r'\textasciitilde{}'),
        ('^', r'\textasciicircum{}'),
        ('➔', r' - '),
        ('→', r' - '),
    ]
    for orig, repl in replacements:
        text = text.replace(orig, repl)
    return text


def process_inline_latex(text: str) -> str:
    """Process inline markdown (bold, italic, code, wikilinks, dates, external links)."""
    # 1. Protect inline code `code`
    code_tokens = []
    def save_code(m):
        code_tokens.append(m.group(1))
        return f'@@CODE{len(code_tokens)-1}@@'
    text = re.sub(r'`([^`]+)`', save_code, text)

    # 2. Protect wikilinks [[Target|Display]] or [[Target]]
    link_tokens = []
    def save_link(m):
        raw = m.group(1)
        if '|' in raw:
            tgt, disp = raw.split('|', 1)
        else:
            tgt, disp = raw, raw
        slug = sanitize_id(tgt.strip())
        link_tokens.append((slug, text_to_latex(disp.strip())))
        return f'@@LINK{len(link_tokens)-1}@@'
    text = re.sub(r'\[\[(.*?)\]\]', save_link, text)

    # 3. Protect external markdown links [Display](URL)
    ext_link_tokens = []
    def save_ext_link(m):
        disp = m.group(1).strip()
        url = m.group(2).strip()
        disp_clean = disp.replace("💬", "").strip() or "Link"
        ext_link_tokens.append((url, disp_clean))
        return f'@@EXTLINK{len(ext_link_tokens)-1}@@'
    text = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', save_ext_link, text)

    # 4. Escape general text
    text = text_to_latex(text)

    # 5. Bold & Italic
    text = re.sub(r'\*\*(.*?)\*\*', r'\\textbf{\1}', text)
    text = re.sub(r'\*(.*?)\*', r'\\textit{\1}', text)

    # 6. Restore wikilinks as clickable \hyperlink
    for idx, (slug, disp) in enumerate(link_tokens):
        text = text.replace(f'@@LINK{idx}@@', f'\\hyperlink{{note:{slug}}}{{{disp}}}')

    # 7. Restore external links as clickable \href
    for idx, (url, disp) in enumerate(ext_link_tokens):
        escaped_disp = text_to_latex(disp)
        text = text.replace(f'@@EXTLINK{idx}@@', f'\\lr{{\\href{{{url}}}{{\\texttt{{{escaped_disp}}}}}}}')

    # 8. Restore inline code inside \lr{\texttt{...}}
    for idx, c in enumerate(code_tokens):
        escaped_c = text_to_latex(c)
        text = text.replace(f'@@CODE{idx}@@', f'\\lr{{\\texttt{{{escaped_c}}}}}')

    return text


def convert_md_to_latex(body_md: str) -> str:
    """Convert a note's Markdown body into publication-grade LaTeX."""
    lines = body_md.splitlines()
    latex_lines = []
    i = 0
    n = len(lines)
    in_list = False
    list_type = None

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Empty lines
        if not stripped:
            if in_list:
                latex_lines.append(f'\\end{{{list_type}}}')
                in_list = False
                list_type = None
            latex_lines.append('')
            i += 1
            continue

        # Code block (```lang ... ```)
        if stripped.startswith('```'):
            if in_list:
                latex_lines.append(f'\\end{{{list_type}}}')
                in_list = False
                list_type = None
            code_lines = []
            i += 1
            while i < n and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            if i < n:
                i += 1  # Skip closing ```
            code_text = '\n'.join(code_lines)
            latex_lines.append(r'\begin{tcolorbox}[colback=gray!5!white,colframe=gray!40!white,arc=1mm,left=2mm,right=2mm,top=2mm,bottom=2mm]')
            latex_lines.append(r'\begin{latin}\begin{small}')
            latex_lines.append(r'\begin{verbatim}')
            latex_lines.append(code_text)
            latex_lines.append(r'\end{verbatim}')
            latex_lines.append(r'\end{small}\end{latin}')
            latex_lines.append(r'\end{tcolorbox}')
            continue

        # Markdown Table (| col1 | col2 |)
        if stripped.startswith('|') and '|' in stripped[1:]:
            if in_list:
                latex_lines.append(f'\\end{{{list_type}}}')
                in_list = False
                list_type = None
            table_lines = []
            while i < n and lines[i].strip().startswith('|'):
                table_lines.append(lines[i].strip())
                i += 1
            
            rows = []
            for t_line in table_lines:
                cells = [c.strip() for c in t_line.split('|')]
                if cells and cells[0] == '': cells.pop(0)
                if cells and cells[-1] == '': cells.pop()
                rows.append(cells)
            
            if len(rows) >= 2 and all(re.match(r'^:?-+:?$', c) for c in rows[1]):
                headers = rows[0]
                data_rows = rows[2:]
                col_spec = ' '.join(['X'] * max(1, len(headers)))
                latex_lines.append(r'\begin{table}[h!]')
                latex_lines.append(r'\centering')
                latex_lines.append(f'\\begin{{tabularx}}{{\\textwidth}}{{{col_spec}}}')
                latex_lines.append(r'\toprule')
                hdr_cells = [f'\\textbf{{{process_inline_latex(h)}}}' for h in headers]
                latex_lines.append(' & '.join(hdr_cells) + r' \\')
                latex_lines.append(r'\midrule')
                for row in data_rows:
                    while len(row) < len(headers): row.append('')
                    row_cells = [process_inline_latex(c) for c in row[:len(headers)]]
                    latex_lines.append(' & '.join(row_cells) + r' \\')
                latex_lines.append(r'\bottomrule')
                latex_lines.append(r'\end{tabularx}')
                latex_lines.append(r'\end{table}')
            continue

        # Obsidian Callouts (> [!type] Title)
        callout_m = re.match(r'^>\s*\[!([a-zA-Z0-9_-]+)\]\s*(.*)$', stripped)
        if callout_m:
            if in_list:
                latex_lines.append(f'\\end{{{list_type}}}')
                in_list = False
                list_type = None
            c_type = callout_m.group(1).lower()
            c_title = callout_m.group(2).strip()
            if not c_title:
                if c_type == 'summary': c_title = 'خلاصه راهنما'
                elif c_type == 'tip': c_title = 'نکته کلیدی و مهم'
                elif c_type == 'info': c_title = 'اطلاعات تکمیلی'
                elif c_type in ('warning', 'caution'): c_title = 'هشدار و نکات احتیاطی'
                else: c_title = c_type.capitalize()

            callout_lines = []
            i += 1
            while i < n and (lines[i].strip().startswith('>') or lines[i].strip() == ''):
                b_line = lines[i].strip()
                if b_line.startswith('>'):
                    b_line = b_line[1:].strip()
                callout_lines.append(b_line)
                i += 1

            c_body_raw = '\n'.join(callout_lines)
            c_body = convert_md_to_latex(c_body_raw)

            colback = 'blue!5!white'
            colframe = 'blue!75!black'
            if c_type == 'tip':
                colback = 'green!5!white'
                colframe = 'green!60!black'
            elif c_type == 'info':
                colback = 'violet!5!white'
                colframe = 'violet!70!black'
            elif c_type in ('warning', 'caution'):
                colback = 'orange!5!white'
                colframe = 'orange!80!black'

            escaped_title = process_inline_latex(c_title)
            latex_lines.append(f'\\begin{{tcolorbox}}[colback={colback},colframe={colframe},arc=2mm,title=\\textbf{{{escaped_title}}}]')
            latex_lines.append(c_body)
            latex_lines.append(r'\end{tcolorbox}')
            continue

        # Headings (##, ###, ####)
        h_match = re.match(r'^(#{1,4})\s+(.*)$', stripped)
        if h_match:
            if in_list:
                latex_lines.append(f'\\end{{{list_type}}}')
                in_list = False
                list_type = None
            level = len(h_match.group(1))
            h_text = process_inline_latex(h_match.group(2).strip())

            if level == 1:
                latex_lines.append(f'\\subsection*{{{h_text}}}')
            elif level == 2:
                latex_lines.append(f'\\subsection{{{h_text}}}')
            elif level == 3:
                latex_lines.append(f'\\subsubsection{{{h_text}}}')
            else:
                latex_lines.append(f'\\paragraph{{{h_text}}}')
            i += 1
            continue

        # Horizontal Divider
        if re.match(r'^(-{3,}|\*{3,}|_{3,})$', stripped):
            if in_list:
                latex_lines.append(f'\\end{{{list_type}}}')
                in_list = False
                list_type = None
            latex_lines.append(r'\noindent\rule{\textwidth}{0.4pt}')
            i += 1
            continue

        # Bullet List (- or *)
        list_m = re.match(r'^[-*]\s+(.*)$', stripped)
        if list_m:
            if not in_list or list_type != 'itemize':
                if in_list: latex_lines.append(f'\\end{{{list_type}}}')
                latex_lines.append(r'\begin{itemize}')
                in_list = True
                list_type = 'itemize'
            item_text = process_inline_latex(list_m.group(1).strip())
            latex_lines.append(f'\\item {item_text}')
            i += 1
            continue

        # Numbered List (1. )
        enum_m = re.match(r'^\d+\.\s+(.*)$', stripped)
        if enum_m:
            if not in_list or list_type != 'enumerate':
                if in_list: latex_lines.append(f'\\end{{{list_type}}}')
                latex_lines.append(r'\begin{enumerate}')
                in_list = True
                list_type = 'enumerate'
            item_text = process_inline_latex(enum_m.group(1).strip())
            latex_lines.append(f'\\item {item_text}')
            i += 1
            continue

        # Regular text paragraph
        if in_list:
            latex_lines.append(f'\\end{{{list_type}}}')
            in_list = False
            list_type = None

        processed = process_inline_latex(stripped)
        latex_lines.append(processed)
        i += 1

    if in_list:
        latex_lines.append(f'\\end{{{list_type}}}')

    return '\n'.join(latex_lines)


def generate_latex_book(notes: list) -> str:
    """Generate complete LaTeX book source code for the entire vault."""
    categories = {}
    for n in notes:
        if n['is_moc']:
            continue
        cat = n['category_display']
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(n)

    tex_doc = [r'''\documentclass[11pt,a4paper,oneside]{book}
\usepackage[top=2.5cm, bottom=2.5cm, right=2.5cm, left=2.5cm]{geometry}
\usepackage{xcolor}
\definecolor{accentcolor}{HTML}{7C3AED}
\definecolor{goldcolor}{HTML}{D97706}
\usepackage{tcolorbox}
\tcbuselibrary{skins,breakable}
\usepackage{tabularx}
\usepackage{booktabs}
\usepackage{fancyhdr}
\setlength{\headheight}{15pt}
\addtolength{\topmargin}{-3pt}
\usepackage{hyperref}
\hypersetup{
    colorlinks=true,
    linkcolor=accentcolor,
    urlcolor=accentcolor,
    citecolor=accentcolor
}
\usepackage{fontspec}
\usepackage{xepersian}

\settextfont{IRANSansMobile}
\setlatintextfont{Arial}

\pagestyle{fancy}
\fancyhf{}
\fancyhead[R]{\rightmark}
\fancyhead[L]{\textbf{Second Brain}}
\fancyfoot[C]{\thepage}
\renewcommand{\headrulewidth}{0.4pt}

\begin{document}

\begin{titlepage}
\centering
\vspace*{3cm}
{\Huge\textbf{پایگاه جامع دانش و یادداشت‌ها}}\\[1cm]
{\Large\textbf{Second Brain | Knowledge Base}}\\[1.5cm]
{\large مجموعه کامل یادداشت‌ها، راهنماها و خلاصه‌های تخصصی}\\[2cm]
\vfill
{\large تاریخ نگارش: \today}\\[0.5cm]
{\small تدوین‌شده به صورت خودکار با موتور زی‌پرشین (XePersian)}
\end{titlepage}

\tableofcontents
\clearpage
''']

    for cat_name, cat_notes in categories.items():
        escaped_cat = text_to_latex(cat_name)
        tex_doc.append(f'\\chapter{{{escaped_cat}}}')

        for note in cat_notes:
            escaped_title = text_to_latex(note['title'])
            slug = sanitize_id(note['stem'])

            tex_doc.append(f'\\section{{{escaped_title}}}')
            tex_doc.append(f'\\label{{note:{slug}}}')
            tex_doc.append(f'\\hypertarget{{note:{slug}}}{{}}')

            meta_items = []
            if note['is_summary']:
                meta_items.append(r'\textbf{⚡ نسخه خلاصه شده}')
            if note['created_at']:
                created = note['created_at']
                meta_items.append(f'تاریخ ثبت: \\lr{{{created}}}')
            if note['word_count']:
                words = note['word_count']
                meta_items.append(f'{words} کلمه')

            if meta_items:
                badge_text = ' • '.join(meta_items)
                tex_doc.append(r'\begin{tcolorbox}[colback=gray!8!white,colframe=gray!30!white,arc=1mm,left=2mm,right=2mm,top=1mm,bottom=1mm]')
                tex_doc.append(f'\\small {badge_text}')
                tex_doc.append(r'\end{tcolorbox}')

            body_md = note.get('body_md', '')
            if body_md:
                body_tex = convert_md_to_latex(body_md)
                tex_doc.append(body_tex)

            tex_doc.append(r'\clearpage' + '\n')

    tex_doc.append(r'\end{document}')
    return '\n'.join(tex_doc)


def compile_latex_to_pdf(tex_path: Path) -> Path | None:
    """Compile a .tex file using XeLaTeX (2 passes for TOC and hyperref links)."""
    import shutil
    xelatex_bin = shutil.which("xelatex")
    if not xelatex_bin:
        print("[!] xelatex is not installed or not in PATH. Skipping PDF compilation.")
        return None

    print(f"\n[+] Compiling LaTeX document to PDF via XeLaTeX: {tex_path.name}")
    try:
        # Pass 1
        print("    -> Running XeLaTeX Pass 1/2...")
        res1 = subprocess.run(
            [xelatex_bin, "-interaction=nonstopmode", tex_path.name],
            cwd=tex_path.parent,
            capture_output=True,
            text=True,
            errors="replace"
        )
        if res1.returncode != 0:
            print(f"[!] XeLaTeX Pass 1 failed with return code {res1.returncode}")
            return None

        # Pass 2 (Resolves Table of Contents and Hyperlinks)
        print("    -> Running XeLaTeX Pass 2/2 (Generating Table of Contents & Hyperlinks)...")
        res2 = subprocess.run(
            [xelatex_bin, "-interaction=nonstopmode", tex_path.name],
            cwd=tex_path.parent,
            capture_output=True,
            text=True,
            errors="replace"
        )
        if res2.returncode != 0:
            print(f"[!] XeLaTeX Pass 2 failed with return code {res2.returncode}")
            return None

        pdf_path = tex_path.with_suffix(".pdf")
        if pdf_path.exists():
            size_mb = pdf_path.stat().st_size / (1024 * 1024)
            print(f"[✓] Successfully compiled LaTeX PDF: {pdf_path} ({size_mb:.2f} MB)")
            
            # Clean temporary auxiliary files (.aux, .log, .toc, .out)
            for ext in [".aux", ".log", ".toc", ".out"]:
                aux = tex_path.with_suffix(ext)
                if aux.exists():
                    try:
                        aux.unlink()
                    except Exception:
                        pass
            return pdf_path
    except Exception as e:
        print(f"[!] Exception during LaTeX compilation: {e}")
    return None


def generate_standalone_html(notes):
    """Generate the complete self-contained HTML with CSS and JS."""

    # Compute stats
    total_notes = len(notes)
    summary_count = sum(1 for n in notes if n["is_summary"])
    master_count = total_notes - summary_count - 1  # minus MOC

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    notes_json = json.dumps(notes, ensure_ascii=False)

    html_template = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>🧠 Second Brain | پایگاه جامع دانش و یادداشت‌ها</title>
  <meta name="description" content="پایگاه دانش آفلاین، ساختاریافته و جامع با خلاصه‌های هوشمند، لینک‌های داخلی و جستجوی آنی.">
  
  <style>
    /* ==========================================================================
       Obsidian-Inspired Theme & Core Typography (Zero External Dependencies)
       ========================================================================== */
    :root {{
      --font-stack: "Vazirmatn", "IRANSans", "Segoe UI", Tahoma, -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
      --transition-fast: 0.18s ease;
      --transition-smooth: 0.28s cubic-bezier(0.4, 0, 0.2, 1);
    }}

    /* Clean Paper Light Theme (Default) */
    html[data-theme="light"] {{
      --bg-app: #f8fafc;
      --bg-sidebar: #ffffff;
      --bg-card: #ffffff;
      --bg-card-hover: #f1f5f9;
      --bg-code: #f1f5f9;
      --border-color: #e2e8f0;
      --border-subtle: #f1f5f9;
      --text-main: #0f172a;
      --text-muted: #475569;
      --text-faint: #94a3b8;
      --accent: #7c3aed;
      --accent-hover: #6d28d9;
      --accent-soft: rgba(124, 58, 237, 0.08);
      --accent-glow: rgba(124, 58, 237, 0.2);
      --gold: #d97706;
      --gold-soft: rgba(217, 119, 6, 0.1);
      --callout-summary-bg: #eff6ff;
      --callout-summary-border: #0284c7;
      --callout-tip-bg: #ecfdf5;
      --callout-tip-border: #10b981;
      --callout-info-bg: #f5f3ff;
      --callout-info-border: #7c3aed;
      --callout-warning-bg: #fffbeb;
      --callout-warning-border: #f59e0b;
    }}

    /* Obsidian Dark Theme */
    html[data-theme="dark"] {{
      --bg-app: #141416;
      --bg-sidebar: #1a1a1e;
      --bg-card: #202026;
      --bg-card-hover: #26262e;
      --bg-code: #121215;
      --border-color: #2e2e38;
      --border-subtle: #24242d;
      --text-main: #f0f0f5;
      --text-muted: #9595a8;
      --text-faint: #676778;
      --accent: #8b5cf6;
      --accent-hover: #a78bfa;
      --accent-soft: rgba(139, 92, 246, 0.15);
      --accent-glow: rgba(139, 92, 246, 0.35);
      --gold: #fbbf24;
      --gold-soft: rgba(251, 191, 36, 0.15);
      --callout-summary-bg: rgba(56, 189, 248, 0.08);
      --callout-summary-border: #0284c7;
      --callout-tip-bg: rgba(52, 211, 153, 0.08);
      --callout-tip-border: #10b981;
      --callout-info-bg: rgba(139, 92, 246, 0.08);
      --callout-info-border: #8b5cf6;
      --callout-warning-bg: rgba(251, 191, 36, 0.08);
      --callout-warning-border: #f59e0b;
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      font-family: var(--font-stack);
      background-color: var(--bg-app);
      color: var(--text-main);
      display: flex;
      height: 100vh;
      overflow: hidden;
      line-height: 1.75;
      -webkit-font-smoothing: antialiased;
    }}

    /* Scrollbars */
    ::-webkit-scrollbar {{
      width: 6px;
      height: 6px;
    }}
    ::-webkit-scrollbar-track {{
      background: transparent;
    }}
    ::-webkit-scrollbar-thumb {{
      background: var(--border-color);
      border-radius: 4px;
    }}
    ::-webkit-scrollbar-thumb:hover {{
      background: var(--text-faint);
    }}

    /* ==========================================================================
       Sidebar Component
       ========================================================================== */
    .sidebar {{
      width: 380px;
      min-width: 320px;
      max-width: 480px;
      background: var(--bg-sidebar);
      border-left: 1px solid var(--border-color);
      display: flex;
      flex-direction: column;
      height: 100vh;
      transition: transform var(--transition-smooth);
      z-index: 100;
    }}

    .sidebar-header {{
      padding: 18px 20px;
      border-bottom: 1px solid var(--border-color);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }}

    .brand-title {{
      display: flex;
      align-items: center;
      gap: 10px;
      cursor: pointer;
    }}
    .brand-title .logo {{
      font-size: 26px;
      filter: drop-shadow(0 2px 8px var(--accent-glow));
    }}
    .brand-text h1 {{
      font-size: 15px;
      font-weight: 700;
      color: var(--text-main);
      letter-spacing: -0.3px;
    }}
    .brand-text p {{
      font-size: 11px;
      color: var(--text-muted);
    }}

    .header-actions {{
      display: flex;
      align-items: center;
      gap: 6px;
    }}

    .btn-icon {{
      background: transparent;
      border: 1px solid var(--border-color);
      border-radius: 8px;
      color: var(--text-muted);
      cursor: pointer;
      padding: 6px 9px;
      font-size: 13px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      transition: all var(--transition-fast);
    }}
    .btn-icon:hover {{
      background: var(--bg-card-hover);
      color: var(--text-main);
      border-color: var(--accent);
    }}

    /* Search Box */
    .search-container {{
      padding: 12px 18px;
      border-bottom: 1px solid var(--border-subtle);
      position: relative;
    }}
    .search-input-wrapper {{
      position: relative;
      display: flex;
      align-items: center;
    }}
    .search-input-wrapper input {{
      width: 100%;
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      color: var(--text-main);
      padding: 10px 38px 10px 36px;
      border-radius: 10px;
      font-size: 13px;
      font-family: inherit;
      outline: none;
      transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
    }}
    .search-input-wrapper input:focus {{
      border-color: var(--accent);
      box-shadow: 0 0 0 3px var(--accent-soft);
    }}
    .search-icon {{
      position: absolute;
      right: 12px;
      color: var(--text-muted);
      pointer-events: none;
    }}
    .search-clear {{
      position: absolute;
      left: 10px;
      background: none;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      font-size: 14px;
      display: none;
    }}

    /* Filter Chips */
    .filter-pills {{
      display: flex;
      gap: 6px;
      padding: 8px 18px 12px 18px;
      overflow-x: auto;
      border-bottom: 1px solid var(--border-subtle);
    }}
    .pill {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      color: var(--text-muted);
      padding: 4px 10px;
      border-radius: 20px;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
      white-space: nowrap;
      transition: all var(--transition-fast);
    }}
    .pill.active {{
      background: var(--accent);
      color: #ffffff;
      border-color: var(--accent);
      box-shadow: 0 2px 6px var(--accent-glow);
    }}
    .pill:hover:not(.active) {{
      background: var(--bg-card-hover);
      color: var(--text-main);
    }}

    /* Notes List / Tree */
    .notes-tree {{
      flex: 1;
      overflow-y: auto;
      padding: 10px 12px;
    }}

    .category-group {{
      margin-bottom: 10px;
    }}

    .category-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 10px;
      border-radius: 8px;
      cursor: pointer;
      user-select: none;
      font-size: 12.5px;
      font-weight: 700;
      color: var(--text-muted);
      transition: background var(--transition-fast);
    }}
    .category-header:hover {{
      background: var(--bg-card);
      color: var(--text-main);
    }}
    .category-title {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .category-chevron {{
      font-size: 10px;
      transition: transform var(--transition-fast);
      color: var(--text-faint);
    }}
    .category-group.open .category-chevron {{
      transform: rotate(-90deg);
    }}
    .category-count {{
      font-size: 11px;
      background: var(--border-subtle);
      color: var(--text-faint);
      padding: 1px 7px;
      border-radius: 12px;
    }}

    .category-items {{
      display: none;
      padding-right: 14px;
      margin-top: 2px;
    }}
    .category-group.open .category-items {{
      display: block;
    }}

    .note-item {{
      display: flex;
      align-items: center;
      gap: 9px;
      padding: 8px 12px;
      margin: 2px 0;
      border-radius: 8px;
      cursor: pointer;
      font-size: 12.5px;
      color: var(--text-main);
      text-decoration: none;
      transition: all var(--transition-fast);
      position: relative;
      border-right: 3px solid transparent;
      user-select: none;
      min-width: 0;
      min-height: 40px;
    }}
    .note-item:hover {{
      background: var(--bg-card-hover);
    }}
    .note-item.active {{
      background: var(--accent-soft);
      border-right-color: var(--accent);
      color: var(--accent);
      font-weight: 600;
    }}
    .note-icon {{
      font-size: 14px;
      line-height: 1;
      flex-shrink: 0;
      display: inline-flex;
      align-items: center;
    }}
    .note-item.is-summary {{
      background: rgba(217, 119, 6, 0.04);
      border-radius: 6px;
      margin-right: 8px;
    }}
    .note-item.is-summary.active {{
      background: var(--gold-soft);
      border-right-color: var(--gold);
      color: var(--gold);
    }}
    .note-item-text {{
      flex: 1;
      min-width: 0;
      overflow-x: auto;
      overflow-y: hidden;
      white-space: nowrap;
      scrollbar-width: none;
      -ms-overflow-style: none;
      -webkit-overflow-scrolling: touch;
      scroll-behavior: smooth;
      padding: 3px 0;
      touch-action: pan-x;
      cursor: grab;
    }}
    .note-item-text::-webkit-scrollbar {{
      display: none;
      width: 0;
      height: 0;
    }}
    .note-item-text:active {{
      cursor: grabbing;
    }}
    .summary-badge {{
      font-size: 10px;
      background: var(--gold-soft);
      color: var(--gold);
      padding: 1px 5px;
      border-radius: 4px;
      font-weight: 700;
      margin-left: 6px;
      flex-shrink: 0;
      display: inline-block;
      vertical-align: middle;
    }}

    /* Sidebar Footer */
    .sidebar-footer {{
      padding: 12px 18px;
      border-top: 1px solid var(--border-color);
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 11px;
      color: var(--text-faint);
    }}

    /* ==========================================================================
       Main Reader Area
       ========================================================================== */
    .main-reader {{
      flex: 1;
      height: 100vh;
      overflow-y: auto;
      background: var(--bg-app);
      display: flex;
      flex-direction: column;
      position: relative;
    }}

    .top-navbar {{
      position: sticky;
      top: 0;
      background: var(--bg-card);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border-color);
      padding: 12px 28px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      z-index: 50;
    }}

    .breadcrumbs {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      color: var(--text-muted);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .breadcrumbs span.current {{
      color: var(--text-main);
      font-weight: 600;
    }}

    .nav-actions {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}

    .btn-action {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      color: var(--text-muted);
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 12px;
      font-family: inherit;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all var(--transition-fast);
    }}
    .btn-action:hover {{
      background: var(--bg-card-hover);
      color: var(--text-main);
      border-color: var(--accent);
    }}
    .btn-action.btn-companion {{
      background: var(--gold-soft);
      border-color: var(--gold);
      color: var(--gold);
      font-weight: 600;
    }}
    .btn-action.btn-companion:hover {{
      background: var(--gold);
      color: #000000;
    }}
    .btn-action.btn-pdf-full {{
      background: var(--accent-soft);
      border-color: var(--accent);
      color: var(--accent);
      font-weight: 700;
    }}
    .btn-action.btn-pdf-full:hover {{
      background: var(--accent);
      color: #ffffff;
      box-shadow: 0 2px 8px var(--accent-glow);
    }}

    /* Note Content Body */
    .article-container {{
      max-width: 900px;
      width: 100%;
      margin: 0 auto;
      padding: 32px 32px 80px 32px;
    }}

    /* Obsidian Properties Card */
    .properties-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 16px 20px;
      margin-bottom: 28px;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
    }}
    .properties-header {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      font-weight: 700;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 12px;
      border-bottom: 1px solid var(--border-subtle);
      padding-bottom: 8px;
    }}
    .property-row {{
      display: flex;
      align-items: center;
      font-size: 12.5px;
      padding: 4px 0;
    }}
    .property-key {{
      width: 130px;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      gap: 6px;
      flex-shrink: 0;
    }}
    .property-val {{
      color: var(--text-main);
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}

    .tag-chip {{
      background: var(--accent-soft);
      color: var(--accent);
      border: 1px solid var(--accent);
      padding: 2px 9px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
      transition: all var(--transition-fast);
    }}
    .tag-chip:hover {{
      background: var(--accent);
      color: #ffffff;
    }}

    /* Companion Note Banner */
    .companion-banner {{
      background: var(--gold-soft);
      border: 1px solid var(--gold);
      border-radius: 10px;
      padding: 14px 18px;
      margin-bottom: 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }}
    .companion-text {{
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 13px;
      font-weight: 600;
      color: var(--text-main);
    }}

    /* ==========================================================================
       Bidirectional Typography & First-Vocab Alignment
       ========================================================================== */
    .markdown-body {{
      font-size: 15px;
      color: var(--text-main);
      line-height: 1.85;
    }}

    /* First-letter direction classes */
    .bidi-rtl {{
      direction: rtl !important;
      text-align: right !important;
    }}
    .bidi-ltr {{
      direction: ltr !important;
      text-align: left !important;
    }}

    .markdown-body h1 {{
      font-size: 26px;
      font-weight: 800;
      margin: 0 0 20px 0;
      line-height: 1.4;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 14px;
      color: var(--text-main);
    }}

    .markdown-body h2 {{
      font-size: 20px;
      font-weight: 700;
      margin: 36px 0 16px 0;
      padding-bottom: 6px;
      border-bottom: 1px solid var(--border-subtle);
      color: var(--text-main);
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .markdown-body h2.bidi-ltr {{
      justify-content: flex-start;
    }}
    .markdown-body h2.bidi-rtl {{
      justify-content: flex-start;
    }}

    .markdown-body h3 {{
      font-size: 16.5px;
      font-weight: 700;
      margin: 24px 0 12px 0;
      color: var(--accent);
    }}

    .markdown-body p {{
      margin-bottom: 14px;
    }}

    .markdown-body ul, .markdown-body ol {{
      margin: 12px 0 20px 0;
      padding-right: 24px;
      padding-left: 24px;
    }}

    .markdown-body li {{
      margin-bottom: 10px;
      line-height: 1.85;
      list-style-position: outside;
    }}
    .markdown-body li.bidi-rtl {{
      direction: rtl !important;
      text-align: right !important;
    }}
    .markdown-body li.bidi-ltr {{
      direction: ltr !important;
      text-align: left !important;
    }}

    .markdown-body blockquote {{
      border-right: 4px solid var(--accent);
      border-left: none;
      padding: 12px 18px;
      margin: 18px 0;
      background: var(--bg-card);
      border-radius: 8px;
    }}
    .markdown-body blockquote.bidi-ltr {{
      border-left: 4px solid var(--accent);
      border-right: none;
    }}

    .markdown-body strong {{
      font-weight: 700;
      color: var(--text-main);
    }}

    .markdown-body code {{
      font-family: Consolas, Monaco, monospace;
      font-size: 13px;
      background: var(--bg-code);
      border: 1px solid var(--border-color);
      padding: 2px 6px;
      border-radius: 5px;
      color: var(--accent);
      direction: ltr;
      unicode-bidi: isolate;
      display: inline-block;
    }}

    .markdown-body pre {{
      background: var(--bg-code);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 16px;
      overflow-x: auto;
      margin: 16px 0;
      direction: ltr;
      text-align: left;
    }}
    .markdown-body pre code {{
      display: block;
      border: none;
      background: transparent;
      padding: 0;
    }}

    .markdown-body hr {{
      border: none;
      height: 1px;
      background: var(--border-color);
      margin: 32px 0;
    }}

    /* Responsive Tables and Images */
    .markdown-body table {{
      width: 100%;
      border-collapse: collapse;
      margin: 18px 0;
      font-size: 13.5px;
      display: block;
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      scrollbar-width: thin;
    }}
    .markdown-body th, .markdown-body td {{
      border: 1px solid var(--border-color);
      padding: 10px 14px;
      text-align: right;
    }}
    .markdown-body th {{
      background: var(--bg-card);
      font-weight: 700;
      color: var(--text-main);
    }}
    .markdown-body tr:nth-child(even) {{
      background: var(--accent-soft);
    }}
    .markdown-body img {{
      max-width: 100%;
      height: auto;
      border-radius: 8px;
    }}

    /* Obsidian Callouts Styling */
    .callout {{
      border-radius: 10px;
      padding: 14px 18px;
      margin: 20px 0;
      border-right: 4px solid var(--accent);
      background: var(--accent-soft);
      direction: rtl;
      text-align: right;
    }}
    .callout.bidi-ltr {{
      direction: ltr;
      text-align: left;
      border-left: 4px solid var(--accent);
      border-right: none;
    }}

    .callout-header {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-weight: 700;
      font-size: 13.5px;
      margin-bottom: 6px;
    }}
    .callout-icon {{
      display: inline-flex;
      align-items: center;
      flex-shrink: 0;
    }}
    .callout-body {{
      font-size: 14px;
      color: var(--text-main);
    }}
    .callout-summary {{
      background: var(--callout-summary-bg);
      border-right-color: var(--callout-summary-border);
    }}
    .callout-summary .callout-header {{
      color: var(--callout-summary-border);
    }}
    .callout-tip {{
      background: var(--callout-tip-bg);
      border-right-color: var(--callout-tip-border);
    }}
    .callout-tip .callout-header {{
      color: var(--callout-tip-border);
    }}
    .callout-info {{
      background: var(--callout-info-bg);
      border-right-color: var(--callout-info-border);
    }}
    .callout-info .callout-header {{
      color: var(--callout-info-border);
    }}
    .callout-warning {{
      background: var(--callout-warning-bg);
      border-right-color: var(--callout-warning-border);
    }}
    .callout-warning .callout-header {{
      color: var(--callout-warning-border);
    }}

    /* Date Badges */
    .date-chip {{
      display: inline-flex;
      align-items: center;
      background: var(--border-subtle);
      border: 1px solid var(--border-color);
      color: var(--text-muted);
      font-size: 11.5px;
      font-weight: 600;
      padding: 1px 7px;
      border-radius: 12px;
      margin: 0 4px;
      white-space: nowrap;
      vertical-align: middle;
      direction: ltr;
      unicode-bidi: isolate;
    }}
    .date-group {{
      display: inline-flex;
      flex-wrap: wrap;
      gap: 4px;
      vertical-align: middle;
    }}

    /* Clickable Wikilinks */
    .wikilink {{
      color: var(--accent);
      background: var(--accent-soft);
      padding: 2px 8px;
      border-radius: 6px;
      text-decoration: none;
      font-weight: 600;
      border-bottom: 1px dashed var(--accent);
      transition: all var(--transition-fast);
      cursor: pointer;
      display: inline;
    }}
    .wikilink:hover {{
      background: var(--accent);
      color: #ffffff;
      border-bottom-style: solid;
      box-shadow: 0 2px 6px var(--accent-glow);
    }}

    /* Telegram Source Message Links */
    .telegram-msg-link {{
      display: inline-flex;
      align-items: center;
      gap: 3px;
      background: rgba(36, 161, 222, 0.12);
      color: #0088cc;
      border: 1px solid rgba(36, 161, 222, 0.28);
      font-size: 11px;
      font-weight: 600;
      padding: 1px 7px;
      border-radius: 12px;
      margin: 0 3px;
      text-decoration: none;
      white-space: nowrap;
      vertical-align: middle;
      direction: ltr;
      unicode-bidi: isolate;
      transition: all var(--transition-fast);
      cursor: pointer;
    }}
    .telegram-msg-link:hover {{
      background: #0088cc;
      color: #ffffff;
      border-color: #0088cc;
      box-shadow: 0 2px 8px rgba(0, 136, 204, 0.35);
      transform: translateY(-1px);
    }}
    [data-theme="dark"] .telegram-msg-link {{
      background: rgba(41, 182, 246, 0.16);
      color: #4fc3f7;
      border-color: rgba(41, 182, 246, 0.32);
    }}
    [data-theme="dark"] .telegram-msg-link:hover {{
      background: #29b6f6;
      color: #0f172a;
      border-color: #29b6f6;
      box-shadow: 0 2px 10px rgba(41, 182, 246, 0.45);
    }}

    /* Toast Notification */
    .toast {{
      position: fixed;
      bottom: 24px;
      left: 50%;
      transform: translateX(-50%) translateY(100px);
      background: var(--bg-card);
      border: 1px solid var(--accent);
      color: var(--text-main);
      padding: 10px 20px;
      border-radius: 30px;
      font-size: 13px;
      font-weight: 600;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
      transition: transform var(--transition-smooth);
      z-index: 1000;
      pointer-events: none;
    }}
    .toast.show {{
      transform: translateX(-50%) translateY(0);
    }}

    /* Mobile Backdrop & Header Toggle */
    .sidebar-backdrop {{
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(15, 23, 42, 0.55);
      backdrop-filter: blur(4px);
      -webkit-backdrop-filter: blur(4px);
      z-index: 95;
      opacity: 0;
      transition: opacity var(--transition-smooth);
      pointer-events: none;
    }}

    .mobile-menu-btn {{
      display: none;
    }}
    .mobile-sidebar-close {{
      display: none;
    }}

    @media (max-width: 860px) {{
      .sidebar-backdrop {{
        display: block;
      }}
      .sidebar-backdrop.active {{
        opacity: 1;
        pointer-events: auto;
      }}
      .sidebar {{
        position: fixed;
        right: 0;
        top: 0;
        bottom: 0;
        width: 88vw;
        max-width: 380px;
        min-width: 290px;
        height: 100%;
        height: 100dvh;
        transform: translateX(100%);
        box-shadow: -6px 0 28px rgba(0, 0, 0, 0.25);
        z-index: 100;
        border-left: 1px solid var(--border-color);
      }}
      .sidebar.open {{
        transform: translateX(0);
      }}
      .mobile-menu-btn {{
        display: inline-flex;
      }}
      .mobile-sidebar-close {{
        display: inline-flex;
      }}
      .top-navbar {{
        padding: 10px 14px;
        flex-direction: column;
        align-items: stretch;
        gap: 10px;
      }}
      .navbar-top-row {{
        display: flex;
        align-items: center;
        gap: 8px;
        width: 100%;
      }}
      .breadcrumbs {{
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 13px;
        color: var(--text-muted);
        overflow-x: auto;
        white-space: nowrap;
        scrollbar-width: none;
        -webkit-overflow-scrolling: touch;
        flex: 1;
        min-width: 0;
      }}
      .breadcrumbs::-webkit-scrollbar {{
        display: none;
      }}
      .nav-actions {{
        display: flex;
        align-items: center;
        gap: 6px;
        overflow-x: auto;
        white-space: nowrap;
        scrollbar-width: none;
        -webkit-overflow-scrolling: touch;
        padding-bottom: 2px;
        width: 100%;
      }}
      .nav-actions::-webkit-scrollbar {{
        display: none;
      }}
      .btn-action {{
        padding: 6px 11px;
        font-size: 11.5px;
        flex-shrink: 0;
        border-radius: 8px;
      }}
      .article-container {{
        padding: 16px 14px 70px 14px;
      }}
    }}

    @media (max-width: 480px) {{
      .sidebar {{
        width: 92vw;
        max-width: 340px;
      }}
      .properties-card {{
        padding: 12px 14px;
      }}
      .property-row {{
        flex-direction: column;
        align-items: flex-start;
        gap: 2px;
        margin-bottom: 6px;
      }}
      .property-key {{
        width: auto;
        font-weight: 700;
        font-size: 11.5px;
      }}
      .companion-banner {{
        flex-direction: column;
        align-items: flex-start;
        gap: 10px;
      }}
      .companion-banner button {{
        width: 100%;
        justify-content: center;
      }}
    }}

    /* ==========================================================================
       Export Modal Styles (LaTeX / PDF / Print)
       ========================================================================== */
    .modal-backdrop {{
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(15, 23, 42, 0.65);
      backdrop-filter: blur(5px);
      -webkit-backdrop-filter: blur(5px);
      z-index: 1000;
      opacity: 0;
      transition: opacity var(--transition-smooth);
    }}
    .modal-backdrop.active {{
      display: block;
      opacity: 1;
    }}
    .export-modal {{
      display: none;
      position: fixed;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%) scale(0.95);
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 16px;
      width: 90%;
      max-width: 620px;
      box-shadow: 0 20px 45px rgba(0, 0, 0, 0.3);
      z-index: 1001;
      opacity: 0;
      transition: all var(--transition-smooth);
      overflow: hidden;
      direction: rtl;
      text-align: right;
    }}
    .export-modal.active {{
      display: block;
      opacity: 1;
      transform: translate(-50%, -50%) scale(1);
    }}
    .export-modal-header {{
      padding: 16px 22px;
      border-bottom: 1px solid var(--border-color);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .export-modal-title {{
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 16px;
      font-weight: 700;
      color: var(--text-main);
    }}
    .export-modal-body {{
      padding: 22px;
    }}
    .export-modal-desc {{
      font-size: 13.5px;
      color: var(--text-muted);
      margin-bottom: 18px;
      line-height: 1.7;
    }}
    .export-options-grid {{
      display: flex;
      flex-direction: column;
      gap: 12px;
    }}
    .export-option-card {{
      display: flex;
      align-items: center;
      gap: 14px;
      padding: 14px 18px;
      background: var(--bg-app);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      text-decoration: none;
      color: inherit;
      position: relative;
      cursor: pointer;
      transition: all var(--transition-fast);
    }}
    .export-option-card:hover {{
      border-color: var(--accent);
      background: var(--bg-card-hover);
      transform: translateY(-2px);
      box-shadow: 0 4px 14px var(--accent-glow);
    }}
    .export-option-card.recommended {{
      border-color: var(--accent);
      background: var(--accent-soft);
    }}
    .option-badge {{
      position: absolute;
      top: -9px;
      left: 14px;
      background: var(--accent);
      color: #ffffff;
      font-size: 10px;
      font-weight: 700;
      padding: 1px 8px;
      border-radius: 10px;
    }}
    .option-icon {{
      font-size: 26px;
      flex-shrink: 0;
    }}
    .option-info {{
      flex: 1;
      min-width: 0;
    }}
    .option-info h4 {{
      font-size: 13.5px;
      font-weight: 700;
      color: var(--text-main);
      margin-bottom: 3px;
    }}
    .option-info p {{
      font-size: 11.5px;
      color: var(--text-muted);
      line-height: 1.5;
      margin: 0;
    }}
    .option-action-btn {{
      font-size: 11.5px;
      font-weight: 700;
      color: var(--accent);
      background: var(--bg-card);
      border: 1px solid var(--accent);
      padding: 6px 12px;
      border-radius: 8px;
      white-space: nowrap;
      flex-shrink: 0;
    }}
    .export-option-card:hover .option-action-btn {{
      background: var(--accent);
      color: #ffffff;
    }}
    @media (max-width: 600px) {{
      .export-modal {{
        width: 95%;
        max-height: 90vh;
        overflow-y: auto;
      }}
      .export-option-card {{
        flex-direction: column;
        align-items: flex-start;
        gap: 8px;
      }}
      .option-action-btn {{
        width: 100%;
        text-align: center;
      }}
    }}

    /* ==========================================================================
       Print & Complete PDF Book Styles
       ========================================================================== */
    @media print {{
      .sidebar, .top-navbar, .nav-actions, .mobile-menu-btn, .toast, .search-container {{
        display: none !important;
      }}
      body, .main-reader, .article-container {{
        height: auto !important;
        overflow: visible !important;
        background: #ffffff !important;
        color: #000000 !important;
        padding: 0 !important;
        margin: 0 !important;
        max-width: 100% !important;
        width: 100% !important;
      }}
      .properties-card, .callout {{
        border: 1px solid #cbd5e1 !important;
        background: #ffffff !important;
        page-break-inside: avoid;
        break-inside: avoid;
      }}
      .page-break {{
        page-break-after: always !important;
        break-after: page !important;
        height: 0;
        margin: 0;
        padding: 0;
      }}
      .pdf-cover-page {{
        height: 85vh;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        text-align: center;
        page-break-after: always;
        break-after: page;
      }}
      .pdf-cover-badge {{
        font-size: 16px;
        font-weight: 700;
        color: #7c3aed;
        margin-bottom: 24px;
      }}
      .pdf-cover-title {{
        font-size: 32px;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 16px;
        line-height: 1.4;
      }}
      .pdf-cover-subtitle {{
        font-size: 18px;
        color: #475569;
        margin-bottom: 32px;
      }}
      .pdf-cover-meta {{
        display: flex;
        gap: 20px;
        font-size: 14px;
        color: #64748b;
      }}
      .pdf-category-divider {{
        padding: 30px 0;
        border-bottom: 2px solid #7c3aed;
        margin-bottom: 24px;
        page-break-before: always;
        break-before: page;
      }}
      .pdf-category-divider h2 {{
        color: #7c3aed;
        font-size: 24px;
      }}
      .pdf-note-section {{
        padding-top: 10px;
        margin-bottom: 30px;
      }}
      .pdf-note-header {{
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 12px;
      }}
      .pdf-cat-badge {{
        font-size: 12px;
        background: #f1f5f9;
        padding: 2px 8px;
        border-radius: 4px;
        color: #475569;
      }}
      h1, h2, h3, .callout-header {{
        page-break-after: avoid;
        break-after: avoid;
      }}
    }}
  </style>
</head>
<body>

  <!-- Mobile Sidebar Backdrop Overlay -->
  <div class="sidebar-backdrop" id="sidebarBackdrop"></div>

  <!-- =========================================================================
       Left Sidebar: Knowledge Explorer & Filter Engine
       ========================================================================= -->
  <aside class="sidebar" id="sidebar">
    <div class="sidebar-header">
      <div class="brand-title" onclick="loadNote('00_Map_of_Content')">
        <span class="logo">🧠</span>
        <div class="brand-text">
          <h1>Second Brain</h1>
          <p>بانک دانش و یادداشت‌های یکپارچه</p>
        </div>
      </div>
      <div class="header-actions">
        <button class="btn-icon" id="themeToggle" title="تغییر تم شب / روز">🌙</button>
        <button class="btn-icon mobile-sidebar-close" id="sidebarCloseBtn" title="بستن منو">✕</button>
      </div>
    </div>

    <!-- Live Search Bar -->
    <div class="search-container">
      <div class="search-input-wrapper">
        <span class="search-icon">🔍</span>
        <input type="text" id="searchInput" placeholder="جستجو در {total_notes} یادداشت و نکات... (Ctrl+K)" autocomplete="off">
        <button class="search-clear" id="searchClear">×</button>
      </div>
    </div>

    <!-- Quick Filter Tabs -->
    <div class="filter-pills">
      <button class="pill active" data-filter="all">همه ({total_notes})</button>
      <button class="pill" data-filter="summary">⚡ خلاصه‌ها ({summary_count})</button>
      <button class="pill" data-filter="master">📚 اسناد اصلی ({master_count})</button>
    </div>

    <!-- Hierarchical Notes Tree -->
    <div class="notes-tree" id="notesTree">
      <!-- Generated by JavaScript -->
    </div>

    <!-- Sidebar Footer -->
    <div class="sidebar-footer">
      <span>تولید شده: {now_str}</span>
      <span>۱۰۰٪ آفلاین و مستقل</span>
    </div>
  </aside>

  <!-- =========================================================================
       Main Content Reader Panel
       ========================================================================= -->
  <main class="main-reader" id="mainReader">
    <div class="top-navbar">
      <div class="navbar-top-row">
        <button class="btn-icon mobile-menu-btn" id="mobileMenuBtn" title="فهرست یادداشت‌ها">☰</button>
        <div class="breadcrumbs">
          <span id="breadcrumbCategory">فهرست مطالب</span>
          <span>/</span>
          <span class="current" id="breadcrumbTitle">فهرست مطالب</span>
        </div>
      </div>

      <div class="nav-actions">
        <button class="btn-action btn-companion" id="companionBtn" style="display: none;" onclick="switchCompanion()">
          <span id="companionBtnText">⚡ نسخه خلاصه</span>
        </button>
        <button class="btn-action btn-pdf-full" onclick="openExportModal()" title="خروجی کتابچه جامع یادداشت‌ها با موتور حرفه‌ای LaTeX یا چاپ مرورگر">
          📚 خروجی کامل PDF (LaTeX)
        </button>
        <button class="btn-action" onclick="copyNoteUrl()" title="کپی لینک یادداشت">🔗 کپی لینک</button>
        <button class="btn-action" onclick="copyNoteText()" title="کپی متن یادداشت">📋 کپی متن</button>
        <button class="btn-action" onclick="printSingleNote()" title="چاپ یا ذخیره PDF این یادداشت">🖨️ چاپ این یادداشت</button>
      </div>
    </div>

    <div class="article-container">
      <!-- Properties Frontmatter Inspector -->
      <div class="properties-card" id="propertiesCard">
        <div class="properties-header">
          <span>📋 مشخصات و فراداده‌های سند (Properties)</span>
        </div>
        <div class="property-row">
          <span class="property-key">📁 دسته‌بندی:</span>
          <span class="property-val" id="propCategory">-</span>
        </div>
        <div class="property-row" id="propCreatedRow">
          <span class="property-key">📅 تاریخ ثبت:</span>
          <span class="property-val" id="propCreated">-</span>
        </div>
        <div class="property-row" id="propTagsRow">
          <span class="property-key">🏷️ برچسب‌ها:</span>
          <div class="property-val" id="propTags"></div>
        </div>
        <div class="property-row" id="propStatsRow">
          <span class="property-key">⏱️ زمان مطالعه:</span>
          <span class="property-val" id="propStats">-</span>
        </div>
      </div>

      <!-- Companion Banner -->
      <div class="companion-banner" id="companionBanner" style="display: none;">
        <div class="companion-text">
          <span id="bannerIcon">⚡</span>
          <span id="bannerText">نسخه خلاصه و دسته‌بندی‌شده این یادداشت در دسترس است.</span>
        </div>
        <button class="btn-action btn-companion" onclick="switchCompanion()">مشاهده</button>
      </div>

      <!-- Markdown Article Container -->
      <article class="markdown-body" id="articleBody">
        <!-- Rendered Note HTML Injected Here -->
      </article>
    </div>
  </main>

  <!-- Modal for Full PDF / LaTeX Export -->
  <div class="modal-backdrop" id="exportModalBackdrop" onclick="closeExportModal()"></div>
  <div class="export-modal" id="exportModal">
    <div class="export-modal-header">
      <div class="export-modal-title">
        <span>📚</span>
        <span>خروجی کتابچه جامع یادداشت‌ها</span>
      </div>
      <button class="btn-icon" onclick="closeExportModal()">✕</button>
    </div>
    <div class="export-modal-body">
      <p class="export-modal-desc">
        برای دسترسی به کتابچه کامل تمامی یادداشت‌ها با کیفیت عالی، فهرست مطالب ساخت‌یافته و هایپرلینک‌های فعال، می‌توانید از نسخه تولیدشده با موتور حروف‌چینی <b>LaTeX (XePersian)</b> یا چاپ مرورگر استفاده کنید:
      </p>
      
      <div class="export-options-grid">
        <!-- Option 1: Direct LaTeX PDF -->
        <a href="Second_Brain_Knowledge_Base.pdf" target="_blank" download="Second_Brain_Knowledge_Base.pdf" class="export-option-card recommended">
          <div class="option-badge">✨ کیفیت عالی (پیشنهادی)</div>
          <div class="option-icon">📕</div>
          <div class="option-info">
            <h4>دانلود کتاب کامل PDF (LaTeX)</h4>
            <p>تولیدشده با موتور قدرتمند XeLaTeX: دارای فهرست مطالب استاندارد با شماره صفحه، لینک‌های داخلی فعال و صفحه‌آرایی دوطرفه</p>
          </div>
          <div class="option-action-btn">دانلود PDF</div>
        </a>

        <!-- Option 2: LaTeX .tex Source -->
        <a href="Second_Brain_Knowledge_Base.tex" target="_blank" download="Second_Brain_Knowledge_Base.tex" class="export-option-card">
          <div class="option-badge">کد سورس</div>
          <div class="option-icon">📄</div>
          <div class="option-info">
            <h4>دانلود سورس کامل LaTeX (.tex)</h4>
            <p>سورس کامل زی‌پرشین (XePersian) آماده برای ویرایش، شخصی‌سازی و کامپایل در TeXStudio، Overleaf یا خط فرمان</p>
          </div>
          <div class="option-action-btn">دانلود .tex</div>
        </a>

        <!-- Option 3: Browser Print -->
        <div class="export-option-card" onclick="closeExportModal(); exportBrowserPrint();">
          <div class="option-badge">سریع</div>
          <div class="option-icon">🖨️</div>
          <div class="option-info">
            <h4>چاپ مستقیم در مرورگر (Browser Print)</h4>
            <p>باز کردن پیش‌نمایش چاپ مرورگر بدون نیاز به دانلود فایل خارجی</p>
          </div>
          <div class="option-action-btn">چاپ با مرورگر</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Toast Notification -->
  <div class="toast" id="toast">پیام ذخیره شد</div>

  <!-- Embedded Notes Data Store (Zero Network Requests) -->
  <script>
    const NOTES_DATA = {notes_json};
    const NOTES_MAP = {{}};

    // Normalize strings for resilient matching across quotes, apostrophes, and entities
    function normalizeKey(str) {{
      if (!str) return "";
      return str.toString()
        .replace(/&#x27;/g, "'")
        .replace(/&quot;/g, '"')
        .replace(/&amp;/g, '&')
        .replace(/[^a-zA-Z0-9\u0600-\u06FF]+/g, "")
        .toLowerCase()
        .trim();
    }}

    // Index all notes into lookup map with multiple normalized keys
    NOTES_DATA.forEach(n => {{
      NOTES_MAP[n.stem] = n;
      NOTES_MAP[n.id] = n;
      NOTES_MAP[n.title] = n;
      
      const normStem = normalizeKey(n.stem);
      if (normStem) NOTES_MAP[normStem] = n;

      const normTitle = normalizeKey(n.title);
      if (normTitle) NOTES_MAP[normTitle] = n;

      const normId = normalizeKey(n.id);
      if (normId) NOTES_MAP[normId] = n;
    }});

    let currentNote = null;
    let activeFilter = "all";

    // Theme Management: Defaults to LIGHT theme
    const themeToggleBtn = document.getElementById("themeToggle");
    const currentTheme = localStorage.getItem("sb_theme") || "light";
    document.documentElement.setAttribute("data-theme", currentTheme);
    themeToggleBtn.textContent = currentTheme === "dark" ? "☀️" : "🌙";

    themeToggleBtn.addEventListener("click", () => {{
      const nowTheme = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", nowTheme);
      localStorage.setItem("sb_theme", nowTheme);
      themeToggleBtn.textContent = nowTheme === "dark" ? "☀️" : "🌙";
    }});

    // Mobile Drawer Controller
    const mobileBtn = document.getElementById("mobileMenuBtn");
    const sidebar = document.getElementById("sidebar");
    const sidebarCloseBtn = document.getElementById("sidebarCloseBtn");
    const sidebarBackdrop = document.getElementById("sidebarBackdrop");

    function openSidebar() {{
      sidebar.classList.add("open");
      if (sidebarBackdrop) sidebarBackdrop.classList.add("active");
      document.body.style.overflow = "hidden";
    }}

    function closeSidebar() {{
      sidebar.classList.remove("open");
      if (sidebarBackdrop) sidebarBackdrop.classList.remove("active");
      document.body.style.overflow = "";
    }}

    function toggleSidebar() {{
      if (sidebar.classList.contains("open")) {{
        closeSidebar();
      }} else {{
        openSidebar();
      }}
    }}

    if (mobileBtn) mobileBtn.addEventListener("click", toggleSidebar);
    if (sidebarCloseBtn) sidebarCloseBtn.addEventListener("click", closeSidebar);
    if (sidebarBackdrop) sidebarBackdrop.addEventListener("click", closeSidebar);

    // Mobile Window Swipe Gestures (Swipe left from edge to open, swipe right to close)
    let winTouchStartX = 0;
    let winTouchStartY = 0;

    window.addEventListener("touchstart", (e) => {{
      if (e.touches && e.touches.length === 1) {{
        winTouchStartX = e.touches[0].clientX;
        winTouchStartY = e.touches[0].clientY;
      }}
    }}, {{ passive: true }});

    window.addEventListener("touchend", (e) => {{
      if (window.innerWidth > 860 || !e.changedTouches || e.changedTouches.length === 0) return;
      const winTouchEndX = e.changedTouches[0].clientX;
      const winTouchEndY = e.changedTouches[0].clientY;
      const diffX = winTouchEndX - winTouchStartX;
      const diffY = winTouchEndY - winTouchStartY;

      if (Math.abs(diffX) > 50 && Math.abs(diffX) > Math.abs(diffY) * 1.4) {{
        // If sidebar is open and swiped to the right -> close sidebar
        if (sidebar.classList.contains("open") && diffX > 40) {{
          closeSidebar();
        }}
        // If sidebar is closed and swiped to the left from right edge -> open sidebar
        else if (!sidebar.classList.contains("open") && diffX < -40 && winTouchStartX > (window.innerWidth - 65)) {{
          openSidebar();
        }}
      }}
    }}, {{ passive: true }});

    // Touch & Desktop Interaction Controller for Note Titles
    // Allows horizontal swipe on note titles without accidentally triggering tap navigation
    function setupNoteInteraction(itemEl, noteStem) {{
      let touchStartX = 0;
      let touchStartY = 0;
      let hasSwiped = false;
      let isMouseDown = false;
      let mouseStartX = 0;
      let mouseStartScroll = 0;
      const textEl = itemEl.querySelector(".note-item-text");

      // Mobile touch handler
      itemEl.addEventListener("touchstart", (e) => {{
        if (e.touches && e.touches.length === 1) {{
          touchStartX = e.touches[0].clientX;
          touchStartY = e.touches[0].clientY;
          hasSwiped = false;
        }}
      }}, {{ passive: true }});

      itemEl.addEventListener("touchmove", (e) => {{
        if (e.touches && e.touches.length === 1) {{
          const dx = Math.abs(e.touches[0].clientX - touchStartX);
          const dy = Math.abs(e.touches[0].clientY - touchStartY);
          if (dx > 8 || dy > 8) {{
            hasSwiped = true;
          }}
        }}
      }}, {{ passive: true }});

      // Desktop click-and-drag horizontal scroll
      if (textEl) {{
        textEl.addEventListener("mousedown", (e) => {{
          if (e.button !== 0) return;
          isMouseDown = true;
          mouseStartX = e.clientX;
          mouseStartScroll = textEl.scrollLeft;
          hasSwiped = false;
        }});
      }}

      window.addEventListener("mousemove", (e) => {{
        if (isMouseDown && textEl) {{
          const delta = e.clientX - mouseStartX;
          textEl.scrollLeft = mouseStartScroll - delta;
          if (Math.abs(delta) > 5) {{
            hasSwiped = true;
          }}
        }}
      }});

      window.addEventListener("mouseup", () => {{
        if (isMouseDown) {{
          setTimeout(() => {{ isMouseDown = false; }}, 60);
        }}
      }});

      // Tap / Click handler
      itemEl.addEventListener("click", (e) => {{
        if (hasSwiped) {{
          e.preventDefault();
          e.stopPropagation();
          hasSwiped = false;
          return;
        }}
        loadNote(noteStem);
        if (window.innerWidth <= 860) {{
          closeSidebar();
        }}
      }});
    }}

    // Dynamic First-Letter/Word BiDi Direction Engine
    function applyBiDiDirection(container) {{
      if (!container) return;
      const elements = container.querySelectorAll("h1, h2, h3, h4, h5, p, li, blockquote, .callout-header");
      elements.forEach(el => {{
        const letterMatch = el.textContent.match(/([a-zA-Z]|[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF])/);
        if (letterMatch) {{
          const isEnglish = /[a-zA-Z]/.test(letterMatch[1]);
          const dir = isEnglish ? "ltr" : "rtl";
          el.setAttribute("dir", dir);
          el.classList.remove("bidi-rtl", "bidi-ltr");
          el.classList.add("bidi-" + dir);
          el.style.direction = dir;
          el.style.textAlign = isEnglish ? "left" : "right";
        }}
      }});
    }}

    // Global Delegated Click Listener for Wikilinks (Prevents single quote syntax errors)
    document.addEventListener("click", (e) => {{
      const wl = e.target.closest(".wikilink");
      if (wl && wl.dataset.stem) {{
        e.preventDefault();
        loadNote(wl.dataset.stem);
      }}
    }});

    // Build Sidebar Category Tree
    function renderSidebar(filteredNotes = null) {{
      const list = filteredNotes || NOTES_DATA;
      const treeContainer = document.getElementById("notesTree");
      treeContainer.innerHTML = "";

      // Special item for 00_Map_of_Content (فهرست مطالب)
      const mocNote = list.find(n => n.is_moc);
      if (mocNote) {{
        const mocDiv = document.createElement("div");
        mocDiv.className = `note-item ${{currentNote && currentNote.id === mocNote.id ? 'active' : ''}}`;
        mocDiv.innerHTML = `<span class="note-icon">🧭</span><span class="note-item-text" dir="rtl" title="فهرست مطالب"><b>فهرست مطالب</b></span>`;
        mocDiv.dataset.stem = mocNote.stem;
        setupNoteInteraction(mocDiv, mocNote.stem);
        treeContainer.appendChild(mocDiv);
      }}

      // Group by category
      const categories = {{}};
      list.forEach(n => {{
        if (n.is_moc) return;
        if (!categories[n.category_display]) {{
          categories[n.category_display] = [];
        }}
        categories[n.category_display].push(n);
      }});

      for (const [catName, catNotes] of Object.entries(categories)) {{
        const group = document.createElement("div");
        group.className = "category-group open";

        const header = document.createElement("div");
        header.className = "category-header";
        let iconPrefix = "📁";
        if (catName.includes("➔")) {{
          iconPrefix = "🏢";
        }} else if (catName.includes("Report Cluster")) {{
          iconPrefix = "📊";
        }}
        header.innerHTML = `
          <div class="category-title">
            <span class="category-chevron">▼</span>
            <span>${{iconPrefix}} ${{catName}}</span>
          </div>
          <span class="category-count">${{catNotes.length}}</span>
        `;
        header.onclick = () => group.classList.toggle("open");

        const itemsDiv = document.createElement("div");
        itemsDiv.className = "category-items";

        catNotes.forEach(n => {{
          const item = document.createElement("div");
          const isAct = currentNote && currentNote.id === n.id;
          item.className = `note-item ${{n.is_summary ? 'is-summary' : ''}} ${{isAct ? 'active' : ''}}`;
          
          let icon = n.is_summary ? "⚡" : "📄";
          let badge = n.is_summary ? '<span class="summary-badge">خلاصه</span>' : '';

          // Determine direction based on first letter
          const cleanTitle = n.title.replace(/^[📁🧠📌⚡💡⚠️❌🧭\\s\\d\\(\\)\\[\\]\\.\\,\\:\\*\\#\\-\\–\\—\\|]+/, "").trim();
          const letterMatch = cleanTitle.match(/([a-zA-Z]|[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF])/);
          const isEnglish = letterMatch && /[a-zA-Z]/.test(letterMatch[1]);
          const dirAttr = isEnglish ? 'dir="ltr"' : 'dir="rtl"';
          const alignClass = isEnglish ? 'bidi-ltr' : 'bidi-rtl';

          const escapedTitle = n.title.replace(/"/g, '&quot;');

          item.innerHTML = `
            <span class="note-icon">${{icon}}</span>
            <span class="note-item-text ${{alignClass}}" ${{dirAttr}} title="${{escapedTitle}}">${{badge}}${{n.title}}</span>
          `;
          item.dataset.stem = n.stem;
          setupNoteInteraction(item, n.stem);
          itemsDiv.appendChild(item);
        }});

        group.appendChild(header);
        group.appendChild(itemsDiv);
        treeContainer.appendChild(group);
      }}
    }}

    // Filter Buttons
    document.querySelectorAll(".filter-pills .pill").forEach(pill => {{
      pill.addEventListener("click", () => {{
        document.querySelectorAll(".filter-pills .pill").forEach(p => p.classList.remove("active"));
        pill.classList.add("active");
        activeFilter = pill.dataset.filter;
        applySearchAndFilter();
      }});
    }});

    // Live Search
    const searchInput = document.getElementById("searchInput");
    const searchClear = document.getElementById("searchClear");

    searchInput.addEventListener("input", () => {{
      searchClear.style.display = searchInput.value ? "block" : "none";
      applySearchAndFilter();
    }});

    searchClear.addEventListener("click", () => {{
      searchInput.value = "";
      searchClear.style.display = "none";
      applySearchAndFilter();
    }});

    // Keyboard shortcut (Ctrl+K or /) to focus search
    window.addEventListener("keydown", (e) => {{
      if ((e.ctrlKey && e.key === "k") || (e.key === "/" && document.activeElement !== searchInput)) {{
        e.preventDefault();
        searchInput.focus();
      }} else if (e.key === "Escape" && document.activeElement === searchInput) {{
        searchInput.value = "";
        searchInput.blur();
        applySearchAndFilter();
      }}
    }});

    function applySearchAndFilter() {{
      const q = searchInput.value.trim().toLowerCase();
      let results = NOTES_DATA;

      if (activeFilter === "summary") {{
        results = results.filter(n => n.is_summary);
      }} else if (activeFilter === "master") {{
        results = results.filter(n => !n.is_summary && !n.is_moc);
      }}

      if (q) {{
        results = results.filter(n => {{
          return n.title.toLowerCase().includes(q) ||
                 n.category_display.toLowerCase().includes(q) ||
                 n.tags.some(t => t.toLowerCase().includes(q)) ||
                 n.html.toLowerCase().includes(q);
        }});
      }}

      renderSidebar(results);
    }}

    // Filter by Tag Click
    function filterByTag(tagName) {{
      searchInput.value = tagName;
      searchClear.style.display = "block";
      applySearchAndFilter();
      showToast(`فیلتر روی برچسب: #${{tagName}}`);
    }}

    // Resilient Note Resolution (Handles quotes, URL hashes, and stems)
    function findNote(identifier) {{
      if (!identifier) return null;
      let raw = identifier.toString().trim();
      
      // Direct exact match
      if (NOTES_MAP[raw]) return NOTES_MAP[raw];

      // Decoded URI match
      try {{
        const decoded = decodeURIComponent(raw);
        if (NOTES_MAP[decoded]) return NOTES_MAP[decoded];
      }} catch (e) {{}}

      // Normalized match
      const norm = normalizeKey(raw);
      if (norm && NOTES_MAP[norm]) return NOTES_MAP[norm];

      // Linear search across all notes
      return NOTES_DATA.find(n => {{
        return n.id === raw || n.stem === raw || n.title === raw ||
               normalizeKey(n.id) === norm || normalizeKey(n.stem) === norm || normalizeKey(n.title) === norm;
      }}) || null;
    }}

    // Load Specific Note
    function loadNote(stemOrId) {{
      const note = findNote(stemOrId);
      if (!note) {{
        console.warn("Could not find note for:", stemOrId);
        return;
      }}

      currentNote = note;
      try {{
        history.replaceState(null, "", "#" + encodeURIComponent(note.id));
      }} catch (e) {{
        window.location.hash = note.id;
      }}

      // Update Breadcrumbs
      const displayTitle = note.is_moc ? "فهرست مطالب" : note.title;
      document.getElementById("breadcrumbCategory").textContent = note.category_display;
      document.getElementById("breadcrumbTitle").textContent = displayTitle;

      // Update Properties Card
      document.getElementById("propCategory").textContent = note.category_display;
      document.getElementById("propCreated").textContent = note.created_at || "نامشخص";
      document.getElementById("propStats").textContent = `${{note.word_count}} کلمه • حدود ${{note.reading_time}} دقیقه مطالعه (${{note.bullet_count}} نکته کلیدی)`;

      const tagsContainer = document.getElementById("propTags");
      tagsContainer.innerHTML = "";
      if (note.tags && note.tags.length > 0) {{
        note.tags.forEach(t => {{
          const chip = document.createElement("span");
          chip.className = "tag-chip";
          chip.textContent = `#${{t}}`;
          chip.onclick = () => filterByTag(t);
          tagsContainer.appendChild(chip);
        }});
        document.getElementById("propTagsRow").style.display = "flex";
      }} else {{
        document.getElementById("propTagsRow").style.display = "none";
      }}

      // Companion Banner
      const companionBtn = document.getElementById("companionBtn");
      const companionBanner = document.getElementById("companionBanner");
      const bannerText = document.getElementById("bannerText");
      const bannerIcon = document.getElementById("bannerIcon");
      const compBtnText = document.getElementById("companionBtnText");

      if (note.is_summary && note.master_stem) {{
        companionBtn.style.display = "inline-flex";
        compBtnText.textContent = "📂 مشاهده سند اصلی";
        companionBanner.style.display = "flex";
        bannerIcon.textContent = "📂";
        bannerText.textContent = `این یادداشت نسخه خلاصه شده است. برای مشاهده تمامی جزئیات، تجربیات و متن کامل به سند اصلی مراجعه کنید.`;
      }} else if (!note.is_summary && note.summary_stem) {{
        companionBtn.style.display = "inline-flex";
        compBtnText.textContent = "⚡ نسخه خلاصه شده";
        companionBanner.style.display = "flex";
        bannerIcon.textContent = "⚡";
        bannerText.textContent = `نسخه پالایش‌شده، خلاصه و بدون تکرار این راهنما بر اساس تاریخ وقایع تدوین شده است.`;
      }} else {{
        companionBtn.style.display = "none";
        companionBanner.style.display = "none";
      }}

      // Inject Content HTML & Apply BiDi
      const articleEl = document.getElementById("articleBody");
      articleEl.innerHTML = note.html;
      applyBiDiDirection(articleEl);

      document.getElementById("mainReader").scrollTop = 0;

      // Refresh active class in sidebar
      applySearchAndFilter();
    }}

    // Switch between Master and Companion Summary
    function switchCompanion() {{
      if (!currentNote) return;
      if (currentNote.is_summary && currentNote.master_stem) {{
        loadNote(currentNote.master_stem);
      }} else if (!currentNote.is_summary && currentNote.summary_stem) {{
        loadNote(currentNote.summary_stem);
      }}
    }}

    // Toast & Utility Actions
    function showToast(msg) {{
      const toast = document.getElementById("toast");
      toast.textContent = msg;
      toast.classList.add("show");
      setTimeout(() => toast.classList.remove("show"), 2400);
    }}

    function copyNoteUrl() {{
      const url = window.location.href;
      navigator.clipboard.writeText(url).then(() => {{
        showToast("🔗 لینک مستقیم یادداشت کپی شد!");
      }}).catch(() => {{
        showToast("خطا در کپی لینک");
      }});
    }}

    function copyNoteText() {{
      const text = document.getElementById("articleBody").innerText;
      navigator.clipboard.writeText(text).then(() => {{
        showToast("📋 متن یادداشت در کلیپ‌بورد کپی شد!");
      }}).catch(() => {{
        showToast("خطا در کپی متن");
      }});
    }}

    function printSingleNote() {{
      window.print();
    }}

    function openExportModal() {{
      const bd = document.getElementById("exportModalBackdrop");
      const m = document.getElementById("exportModal");
      if (bd) bd.classList.add("active");
      if (m) m.classList.add("active");
    }}

    function closeExportModal() {{
      const bd = document.getElementById("exportModalBackdrop");
      const m = document.getElementById("exportModal");
      if (bd) bd.classList.remove("active");
      if (m) m.classList.remove("active");
    }}

    function exportBrowserPrint() {{
      exportFullPdf();
    }}

    // Export Full PDF Book (All 37 Notes in Sequence)
    function exportFullPdf() {{
      showToast("در حال آماده‌سازی خروجی کامل کتاب PDF...");
      
      const reader = document.getElementById("articleBody");
      const origContent = reader.innerHTML;
      const origBreadcrumb = document.getElementById("breadcrumbTitle").textContent;
      const propCard = document.getElementById("propertiesCard");
      const compBanner = document.getElementById("companionBanner");

      propCard.style.display = "none";
      compBanner.style.display = "none";

      let fullBookHtml = `
        <div class="full-pdf-book">
          <!-- Cover Page -->
          <div class="pdf-cover-page">
            <div class="pdf-cover-badge">🧠 Second Brain | Knowledge Base</div>
            <h1 class="pdf-cover-title">پایگاه جامع دانش و یادداشت‌های یکپارچه</h1>
            <p class="pdf-cover-subtitle">مجموعه کامل ${{NOTES_DATA.length}} یادداشت و راهنما در تمامی دسته‌بندی‌ها</p>
            <div class="pdf-cover-meta">
              <span>📅 تاریخ نسخه: ${now_str}</span>
              <span>⚡ شامل اسناد اصلی و نسخه‌های خلاصه‌سازی‌شده</span>
            </div>
          </div>
          <div class="page-break"></div>
      `;

      // 1. Render Table of Contents (فهرست مطالب) first
      const mocNote = NOTES_DATA.find(n => n.is_moc);
      if (mocNote) {{
        fullBookHtml += `
          <section class="pdf-note-section">
            ${{mocNote.html}}
          </section>
          <div class="page-break"></div>
        `;
      }}

      // 2. Render all categories and their notes
      const categories = {{}};
      NOTES_DATA.forEach(n => {{
        if (n.is_moc) return;
        if (!categories[n.category_display]) categories[n.category_display] = [];
        categories[n.category_display].push(n);
      }});

      for (const [catName, catNotes] of Object.entries(categories)) {{
        fullBookHtml += `
          <div class="pdf-category-divider">
            <h2>📁 دسته‌بندی: ${{catName}} (${{catNotes.length}} یادداشت)</h2>
          </div>
        `;

        catNotes.forEach((note) => {{
          fullBookHtml += `
            <section class="pdf-note-section">
              <div class="pdf-note-header">
                <span class="pdf-cat-badge">${{note.category_display}}</span>
                ${{note.is_summary ? '<span class="summary-badge">⚡ نسخه خلاصه</span>' : ''}}
                <span style="font-size:12px; color:#64748b;">📅 ${{note.created_at || ''}}</span>
              </div>
              ${{note.html}}
            </section>
            <div class="page-break"></div>
          `;
        }});
      }}

      fullBookHtml += `</div>`;

      // Inject full book content
      reader.innerHTML = fullBookHtml;
      document.getElementById("breadcrumbTitle").textContent = "کتاب کامل یادداشت‌ها (PDF)";
      applyBiDiDirection(reader);

      // Launch Print Dialog
      setTimeout(() => {{
        window.print();
        // Restore previous single note view smoothly
        setTimeout(() => {{
          reader.innerHTML = origContent;
          document.getElementById("breadcrumbTitle").textContent = origBreadcrumb;
          propCard.style.display = "block";
          applyBiDiDirection(reader);
        }}, 800);
      }}, 350);
    }}

    // Handle Deep Linking / Hash routing
    window.addEventListener("popstate", () => {{
      const hash = window.location.hash.replace("#", "");
      if (hash) {{
        loadNote(hash);
      }}
    }});

    // Initialize App
    window.addEventListener("DOMContentLoaded", () => {{
      renderSidebar();
      const initialHash = window.location.hash.replace("#", "");
      if (initialHash) {{
        loadNote(initialHash);
      }} else {{
        // Load Table of Contents (00_Map_of_Content) by default
        loadNote("00_Map_of_Content");
      }}
    }});
  </script>
</body>
</html>
"""
    return html_template


def export_vault():
    """Main execution function to export the vault to HTML, LaTeX, and compiled PDF."""
    print("\n" + "=" * 65)
    print(" 🚀 EXPORT OBSIDIAN VAULT -> STANDALONE HTML & LATEX PDF")
    print("=" * 65)
    print(f"Reading markdown notes from: {VAULT_DIR}")

    notes = build_notes_dataset()
    if not notes:
        print("[!] No markdown notes found in vault directory.")
        return False

    print(f"[+] Loaded {len(notes)} notes across categories.")

    # 1. Export HTML Application
    html_content = generate_standalone_html(notes)
    OUTPUT_FILE_EXPORTS.write_text(html_content, encoding="utf-8")
    OUTPUT_FILE_VAULT.write_text(html_content, encoding="utf-8")
    size_mb_html = len(html_content.encode("utf-8")) / (1024 * 1024)
    print(f"[✓] HTML Knowledge Base exported: {OUTPUT_FILE_EXPORTS} ({size_mb_html:.2f} MB)")

    # 2. Export LaTeX Document (.tex)
    tex_content = generate_latex_book(notes)
    OUTPUT_TEX_EXPORTS.write_text(tex_content, encoding="utf-8")
    OUTPUT_TEX_VAULT.write_text(tex_content, encoding="utf-8")
    size_mb_tex = len(tex_content.encode("utf-8")) / (1024 * 1024)
    print(f"[✓] LaTeX Source Book exported: {OUTPUT_TEX_EXPORTS} ({size_mb_tex:.2f} MB)")

    # 3. Compile LaTeX Document to PDF (.pdf) via XeLaTeX
    compiled_pdf = compile_latex_to_pdf(OUTPUT_TEX_EXPORTS)
    if compiled_pdf and compiled_pdf.exists():
        import shutil
        shutil.copy2(compiled_pdf, OUTPUT_PDF_VAULT)
        print(f"[✓] Copied LaTeX PDF to Obsidian_Vault: {OUTPUT_PDF_VAULT}")

    print("\n" + "=" * 65)
    print(" ✨ ALL EXPORTS COMPLETE!")
    print("=" * 65)
    print(f"1. Interactive Web App: {OUTPUT_FILE_EXPORTS}")
    print(f"2. LaTeX Source Code:   {OUTPUT_TEX_EXPORTS}")
    if OUTPUT_PDF_EXPORTS.exists():
        print(f"3. Compiled LaTeX PDF:  {OUTPUT_PDF_EXPORTS}")
    print("=" * 65 + "\n")
    return True


if __name__ == "__main__":
    export_vault()

