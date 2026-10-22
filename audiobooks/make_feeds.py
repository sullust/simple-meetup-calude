#!/usr/bin/env python3
"""
Build podcast feeds from audiobooks in a Backblaze B2 bucket.

Default rule (mirrors your Audiobooks folder):
  - A loose audio file at the top level      -> its own feed
  - A folder at the top level                -> one feed with everything inside it
Override per folder with SPLIT_FOLDERS: each item directly inside a split
folder becomes its own feed (files -> one feed each, subfolders -> one feed each).
Splits can be nested, e.g. "Sci-Fi" and "Sci-Fi/The Expanse".

Usage:
  python3 make_feeds.py --dry-run     # show which feeds would be made, change nothing
  python3 make_feeds.py               # build feeds and upload them to B2
  python3 make_feeds.py --no-upload   # build feeds locally only

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
FEED_AUTHOR = "JT"

# Paths relative to your Audiobooks folder. Each item directly inside becomes its own feed.
SPLIT_FOLDERS = [
    # "Discworld",
    # "Sci-Fi/The Expanse",
]

# Paths relative to your Audiobooks folder to leave out of every feed.
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

ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ET.register_namespace("itunes", ITUNES)

LOCAL_FEEDS_DIR = Path(__file__).resolve().parent / "feeds"
SPLIT = {s.strip("/") for s in SPLIT_FOLDERS}
SKIPS = [s.strip("/") for s in SKIP]


def natkey(s):
    """Sort 'Chapter 2' before 'Chapter 10'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s or "feed"


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


def feed_key(rel):
    """Walk down the path; stop at the first folder that isn't split, or at the file."""
    parts = rel.split("/")
    base = ""
    for i, part in enumerate(parts):
        cand = f"{base}/{part}" if base else part
        if i == len(parts) - 1 or cand not in SPLIT:
            return cand
        base = cand


def pick_image(key, is_file, images):
    """Find artwork: same-named image for a single file, else cover/folder image."""
    p = PurePosixPath(key)
    folder = str(p.parent) if is_file else key
    folder = "" if folder == "." else folder
    candidates = images.get(folder, [])
    if is_file:
        for img in candidates:
            if PurePosixPath(img).stem.lower() == p.stem.lower():
                return img
    for img in candidates:
        if PurePosixPath(img).stem.lower() in COVER_NAMES:
            return img
    if not is_file and len(candidates) == 1:
        return candidates[0]
    return None


def url_for(rel):
    return f"{BASE_URL.rstrip('/')}/{quote(PREFIX + rel)}"


def build_feed(key, is_file, files, image_rel, feed_url):
    title = PurePosixPath(key).stem if is_file else PurePosixPath(key).name
    rss = ET.Element("rss", {"version": "2.0"})
    ch = ET.SubElement(rss, "channel")
    ET.SubElement(ch, "title").text = title
    ET.SubElement(ch, "description").text = title
    ET.SubElement(ch, "link").text = feed_url
    ET.SubElement(ch, "language").text = "en-us"
    ET.SubElement(ch, f"{{{ITUNES}}}author").text = FEED_AUTHOR
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

    ET.indent(rss)
    return b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(rss, encoding="utf-8")


def build_html(entries):
    from html import escape
    rows = "\n".join(
        f'    <li><strong>{escape(t)}</strong><br>'
        f'<input readonly value="{escape(u)}" onclick="this.select()"> '
        f'<button onclick="copy(this)">Copy</button></li>'
        for t, u in entries
    )
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
  ul {{ list-style: none; padding: 0; }}
  li {{ margin-bottom: 1.2rem; }}
  input {{ width: calc(100% - 5rem); font-size: 0.85rem; padding: 0.3rem; }}
  button {{ font-size: 0.85rem; padding: 0.3rem 0.6rem; }}
</style>
</head>
<body>
<h1>Audiobook feeds</h1>
<p>Copy a link and add it in your podcast app with "Add by URL".</p>
<ul>
{rows}
</ul>
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

    groups, images = {}, {}
    for f in list_bucket():
        name = f.get("fileName", "")
        if not name.startswith(PREFIX):
            continue
        rel = name[len(PREFIX):]
        if rel.startswith(FEEDS_SUBDIR + "/") or is_skipped(rel):
            continue
        ext = PurePosixPath(rel).suffix.lower()
        if ext in IMAGE_EXTS:
            parent = str(PurePosixPath(rel).parent)
            images.setdefault("" if parent == "." else parent, []).append(rel)
        elif ext in AUDIO_TYPES:
            groups.setdefault(feed_key(rel), []).append({
                "rel": rel,
                "size": f.get("size") or f.get("contentLength") or 0,
                "type": AUDIO_TYPES[ext],
            })

    if not groups:
        raise SystemExit("No audio files found. Check BUCKET and PREFIX.")

    # Assign unique slugs
    plan, used = [], set()
    for key in sorted(groups, key=natkey):
        is_file = len(groups[key]) == 1 and groups[key][0]["rel"] == key
        slug = slugify(str(PurePosixPath(key).with_suffix("")) if is_file else key)
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
        print("\nDry run: nothing written. Add folders to SPLIT_FOLDERS to break them up.")
        return

    LOCAL_FEEDS_DIR.mkdir(exist_ok=True)
    wanted, lines, entries, changed = set(), [], [], 0
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
        title = PurePosixPath(key).stem if is_file else PurePosixPath(key).name
        lines.append(f"{title}\n  {feed_url}")
        entries.append((title, feed_url))

    for old in LOCAL_FEEDS_DIR.glob("*.xml"):               # drop feeds for removed books
        if old.name not in wanted:
            old.unlink()

    list_path = LOCAL_FEEDS_DIR.parent / "feed_list.txt"
    list_path.write_text("\n\n".join(lines) + "\n")

    html_path = LOCAL_FEEDS_DIR / "index.html"
    html_data = build_html(entries).encode("utf-8")
    if not html_path.exists() or html_path.read_bytes() != html_data:
        html_path.write_bytes(html_data)
    html_url = f"{BASE_URL.rstrip('/')}/{quote(f'{PREFIX}{FEEDS_SUBDIR}/index.html')}"

    print("\nFeed URLs:\n")
    print("\n\n".join(lines))
    print(f"\n{changed} feed(s) new or changed. URL list also saved to {list_path}")
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
