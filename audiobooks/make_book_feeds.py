#!/usr/bin/env python3
"""
Build one podcast feed per BOOK from audiobooks in a Backblaze B2 bucket.

How a book is found (walks down from the top of your Audiobooks folder):
  - A folder whose audio is all directly inside it              -> one book
  - A folder whose audio subfolders are only parts of one book  -> one book
      (CD 1, Disc 2, Part 3, Book 1, "1| ...", MP3, ...)
  - Anything else (author, collection, series, "Alternate versions",
    a book with several narrations, ...) is split and each subfolder
    is checked the same way.
  - A loose audio file sitting next to book folders (or at the top level) is a
    single-file book and gets its own feed.

Overrides (paths relative to your Audiobooks folder):
  BOOKS  - force a folder to be a single feed (everything under it)
  SPLIT  - force a folder to be split even if it looks like one book

Usage:
  python3 make_book_feeds.py --dry-run     # show which feeds would be made, change nothing
  python3 make_book_feeds.py               # build feeds and upload them to B2
  python3 make_book_feeds.py --no-upload   # build feeds locally only

Requires the b2 CLI, already logged in.
"""

import argparse
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path, PurePosixPath
from urllib.parse import quote
import xml.etree.ElementTree as ET

# ---------------- CONFIG ----------------
BUCKET = "podcasts-sullust"
PREFIX = "a7f3k9q2xm8vt4rw/"        # where your sync puts the Audiobooks folder contents
FEEDS_SUBDIR = "feeds"              # feeds go to b2://BUCKET/PREFIX/feeds/
BASE_URL = ""                       # blank = auto-detect from your b2 account
FEED_AUTHOR = "JT"                  # used only for loose files at the top level

# Force a folder to be ONE feed, e.g. a collection you want to hear in order.
BOOKS = [
    # "Hardcore History Compilation 1-39",
    "Always Coming Home 1-86"
]

# Force a folder to be split into one feed per subfolder.
SPLIT = [
    # "Stephen King/1990 - Four Past Midnight (4 novellas)",
]

# Leave these out of every feed.
SKIP = [
    # "Unsorted",
]
# ----------------------------------------

AUDIO_TYPES = {
    ".mp3": "audio/mpeg", ".m4a": "audio/x-m4a", ".m4b": "audio/x-m4a",
    ".aac": "audio/aac", ".ogg": "audio/ogg", ".opus": "audio/opus",
    ".flac": "audio/flac", ".wav": "audio/wav",
}
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
COVER_NAMES = {"cover", "folder", "front", "artwork"}

# Subfolder names that are pieces of one book rather than separate books.
PART_RE = re.compile(
    r"^\d+\s*\|"                                              # "1| Part One - ..."
    r"|^(cd|disc|disk|part|book|vol(ume)?|side|tape)[\s._-]*"
    r"([0-9]+|[ivxlc]+|one|two|three|four|five|six|seven|eight|nine|ten)\b"
    r"|^(mp3|m4a|m4b|aac|audio)$",
    re.IGNORECASE,
)
# " 64k 18.17.19 {504mb}" style rip info on the end of folder names
RIP_INFO_RE = re.compile(r"\s+\d+k\s+[\d.]+\s*\{[^}]*\}\s*$", re.IGNORECASE)

ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ET.register_namespace("itunes", ITUNES)

LOCAL_FEEDS_DIR = Path(__file__).resolve().parent / "feeds"
BOOK_SET = {s.strip("/") for s in BOOKS}
SPLIT_SET = {s.strip("/") for s in SPLIT}
SKIPS = [s.strip("/") for s in SKIP]


def natkey(s):
    """Sort 'Chapter 2' before 'Chapter 10'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:120].strip("-") or "feed"


def parent_of(rel):
    p = str(PurePosixPath(rel).parent)
    return "" if p == "." else p


def detect_base_url():
    for cmd in (["b2", "account", "get"], ["b2", "get-account-info"]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
            dl = json.loads(out).get("downloadUrl")
            if dl:
                return f"{dl.rstrip('/')}/file/{BUCKET}"
        except Exception:
            continue
    raise SystemExit("Couldn't detect download URL. Set BASE_URL in the script.")


def list_bucket():
    out = subprocess.run(
        ["b2", "ls", "--json", "-r", f"b2://{BUCKET}/{PREFIX}"],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out)


def is_skipped(rel):
    return any(rel == s or rel.startswith(s + "/") for s in SKIPS)


def group_books(audio):
    """Map feed key -> list of audio files. Key is a folder, or a file for single-file feeds."""
    direct, kids = {}, {}           # folder -> audio files in it / audio-bearing subfolders
    for f in audio:
        d = parent_of(f["rel"])
        direct.setdefault(d, []).append(f)
        while d:                    # register every ancestor as audio-bearing
            up = parent_of(d)
            kids.setdefault(up, set()).add(d)
            d = up

    def everything_under(folder):
        pre = folder + "/"
        return [f for f in audio if f["rel"].startswith(pre)]

    groups = {}

    def walk(folder):
        files, subs = direct.get(folder, []), sorted(kids.get(folder, ()))
        if folder and folder not in SPLIT_SET and (
            folder in BOOK_SET
            or not subs
            or all(PART_RE.match(PurePosixPath(s).name) for s in subs)
        ):
            groups[folder] = everything_under(folder)
            return
        for f in files:                         # loose file next to book folders
            groups[f["rel"]] = [f]              # = a single-file book
        for s in subs:
            walk(s)

    walk("")
    return groups


def pick_image(key, is_file, images):
    """Find artwork: same-named image for a single file, else a cover in the
    book folder, inside it (CD1/cover.jpg), or in a folder above it."""
    p = PurePosixPath(key)
    folder = parent_of(key) if is_file else key
    candidates = images.get(folder, [])
    if is_file:
        for img in candidates:
            if PurePosixPath(img).stem.lower() == p.stem.lower():
                return img

    def cover_in(imgs):
        for img in sorted(imgs, key=natkey):
            if PurePosixPath(img).stem.lower() in COVER_NAMES:
                return img
        return None

    found = cover_in(candidates)
    if found:
        return found
    if not is_file:
        if len(candidates) == 1:
            return candidates[0]
        found = cover_in(img for d, imgs in images.items()
                         if d.startswith(folder + "/") for img in imgs)
        if found:
            return found
    up = parent_of(folder)
    while up:
        found = cover_in(images.get(up, []))
        if found:
            return found
        up = parent_of(up)
    return None


def url_for(rel):
    return f"{BASE_URL.rstrip('/')}/{quote(PREFIX + rel)}"


def feed_title(key, is_file):
    p = PurePosixPath(key)
    return RIP_INFO_RE.sub("", p.stem if is_file else p.name)


def build_feed(key, is_file, files, image_rel, feed_url):
    title = feed_title(key, is_file)
    parts = PurePosixPath(key).parts
    author = parts[0] if len(parts) > 1 else FEED_AUTHOR
    rss = ET.Element("rss", {"version": "2.0"})
    ch = ET.SubElement(rss, "channel")
    ET.SubElement(ch, "title").text = title
    ET.SubElement(ch, "description").text = " / ".join(parts)
    ET.SubElement(ch, "link").text = feed_url
    ET.SubElement(ch, "language").text = "en-us"
    ET.SubElement(ch, f"{{{ITUNES}}}author").text = author
    ET.SubElement(ch, f"{{{ITUNES}}}type").text = "serial"
    ET.SubElement(ch, f"{{{ITUNES}}}block").text = "Yes"
    if image_rel:
        ET.SubElement(ch, f"{{{ITUNES}}}image", {"href": url_for(image_rel)})

    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    for i, f in enumerate(sorted(files, key=lambda f: natkey(f["rel"]))):
        if is_file:
            ep_title = PurePosixPath(f["rel"]).stem
        else:
            inner = PurePosixPath(f["rel"]).relative_to(key)
            ep_title = " – ".join(inner.with_suffix("").parts)
        item = ET.SubElement(ch, "item")
        ET.SubElement(item, "title").text = ep_title
        ET.SubElement(item, "enclosure", {
            "url": url_for(f["rel"]), "length": str(f["size"]), "type": f["type"],
        })
        ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = f["rel"]
        ET.SubElement(item, "pubDate").text = format_datetime(start + timedelta(days=i))
        ET.SubElement(item, f"{{{ITUNES}}}episode").text = str(i + 1)

    ET.indent(rss)
    return b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(rss, encoding="utf-8")


def build_html(sections):
    from html import escape
    blocks = []
    for author, entries in sections:
        rows = "\n".join(
            f'    <li><strong>{escape(t)}</strong> '
            f'<span class="count">({n} episode{"" if n == 1 else "s"})</span><br>'
            f'<input readonly value="{escape(u)}" onclick="this.select()"> '
            f'<button onclick="copy(this)">Copy</button></li>'
            for t, n, u in entries
        )
        blocks.append(f"<details>\n  <summary>{escape(author)} ({len(entries)})</summary>\n"
                      f"  <ul>\n{rows}\n  </ul>\n</details>")
    body = "\n".join(blocks)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Audiobook feeds</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 720px;
         margin: 2rem auto; padding: 0 1rem; line-height: 1.4; }}
  summary {{ font-size: 1.1rem; font-weight: 600; cursor: pointer; padding: 0.4rem 0; }}
  ul {{ list-style: none; padding: 0 0 0 1rem; }}
  li {{ margin-bottom: 1.2rem; }}
  .count {{ color: #777; font-size: 0.9rem; }}
  input {{ width: calc(100% - 5rem); font-size: 0.85rem; padding: 0.3rem; }}
  button {{ font-size: 0.85rem; padding: 0.3rem 0.6rem; }}
</style>
</head>
<body>
<h1>Audiobook feeds</h1>
<p>Copy a link and add it in your podcast app with "Add by URL".</p>
{body}
<script>
function copy(btn) {{
  const input = btn.previousElementSibling;
  navigator.clipboard.writeText(input.value).then(() => {{
    btn.textContent = "Copied"; setTimeout(() => btn.textContent = "Copy", 1500);
  }});
}}
</script>
</body>
</html>
"""


def main():
    global BASE_URL
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="show the feed plan only")
    ap.add_argument("--no-upload", action="store_true", help="build locally, don't upload")
    args = ap.parse_args()

    if not BASE_URL:
        BASE_URL = detect_base_url()

    audio, images = [], {}
    for f in list_bucket():
        name = f.get("fileName", "")
        if not name.startswith(PREFIX):
            continue
        rel = name[len(PREFIX):]
        if rel.startswith(FEEDS_SUBDIR + "/") or is_skipped(rel):
            continue
        ext = PurePosixPath(rel).suffix.lower()
        if ext in IMAGE_EXTS:
            images.setdefault(parent_of(rel), []).append(rel)
        elif ext in AUDIO_TYPES:
            audio.append({
                "rel": rel,
                "size": f.get("size") or f.get("contentLength") or 0,
                "type": AUDIO_TYPES[ext],
            })

    if not audio:
        raise SystemExit("No audio files found. Check BUCKET and PREFIX.")
    groups = group_books(audio)

    # Assign unique slugs
    plan, used = [], set()
    for key in sorted(groups, key=natkey):
        is_file = len(groups[key]) == 1 and groups[key][0]["rel"] == key
        name = str(PurePosixPath(key).with_suffix("")) if is_file else key
        slug = slugify("/".join(RIP_INFO_RE.sub("", p) for p in name.split("/")))
        base, n = slug, 2
        while slug in used:
            slug, n = f"{base}-{n}", n + 1
        used.add(slug)
        plan.append((key, is_file, slug))

    print(f"{len(plan)} feeds:\n")
    for key, is_file, slug in plan:
        kind = "file  " if is_file else "folder"
        print(f"  [{kind}] {key}  ({len(groups[key])} episodes)")
    if args.dry_run:
        print("\nDry run: nothing written. Use BOOKS / SPLIT in the script to adjust.")
        return

    LOCAL_FEEDS_DIR.mkdir(exist_ok=True)
    wanted, lines, sections, changed = set(), [], {}, 0
    for key, is_file, slug in plan:
        fname = f"{slug}.xml"
        wanted.add(fname)
        feed_url = f"{BASE_URL.rstrip('/')}/{quote(f'{PREFIX}{FEEDS_SUBDIR}/{fname}')}"
        data = build_feed(key, is_file, groups[key],
                          pick_image(key, is_file, images), feed_url)
        path = LOCAL_FEEDS_DIR / fname
        if not path.exists() or path.read_bytes() != data:   # only touch changed feeds
            path.write_bytes(data)
            changed += 1
        title = feed_title(key, is_file)
        parts = PurePosixPath(key).parts
        lines.append(f"{key}\n  {feed_url}")
        sections.setdefault(parts[0] if len(parts) > 1 else "Singles", []).append(
            (" / ".join(parts[1:-1] + (title,)) if len(parts) > 1 else title,
             len(groups[key]), feed_url))

    for old in LOCAL_FEEDS_DIR.glob("*.xml"):               # drop feeds that no longer exist
        if old.name not in wanted:
            old.unlink()

    list_path = LOCAL_FEEDS_DIR.parent / "feed_list.txt"
    list_path.write_text("\n\n".join(lines) + "\n")

    html_path = LOCAL_FEEDS_DIR / "index.html"
    html_data = build_html(sorted(sections.items(), key=lambda kv: natkey(kv[0]))).encode("utf-8")
    if not html_path.exists() or html_path.read_bytes() != html_data:
        html_path.write_bytes(html_data)
    html_url = f"{BASE_URL.rstrip('/')}/{quote(f'{PREFIX}{FEEDS_SUBDIR}/index.html')}"

    print(f"\n{changed} feed(s) new or changed. URL list saved to {list_path}")
    if args.no_upload:
        print(f"\nShareable page (not uploaded, --no-upload): {html_path}")
        return
    print("Uploading feeds...")
    subprocess.run(
        ["b2", "sync", "--delete", str(LOCAL_FEEDS_DIR),
         f"b2://{BUCKET}/{PREFIX}{FEEDS_SUBDIR}/"],
        check=True,
    )
    print("\nDone. Uploaded feeds and index.html.")
    print(f"\nShareable page (send this link to a friend):\n  {html_url}")
    print(f"Local copy: {html_path}")


if __name__ == "__main__":
    main()
