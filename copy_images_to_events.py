#!/usr/bin/env python3
"""
Copy images into events/<sanitized_event_name>/image_file

CSV columns expected (case-insensitive): image, event
- 'image' may include a path; we only use its basename to look inside images_dir
- Missing images are reported but won't crash the run

Usage:
  python copy_images_to_events.py --csv data.csv --images-dir ./images --events-dir ./events
"""

import argparse
import os
import re
import shutil
import sys
import unicodedata
import pandas as pd

def sanitize_name(name: str, max_len: int = 80) -> str:
    """
    Make a safe folder name:
      - normalize unicode
      - replace illegal chars with underscores
      - collapse repeated underscores
      - trim underscores and length
      - fall back to 'unknown' if empty
    """
    if not isinstance(name, str):
        name = str(name) if name is not None else ""

    # Normalize unicode (e.g., accents -> ASCII where possible)
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")

    # Replace anything not alnum, dash, space, underscore, or dot with underscore
    name = re.sub(r"[^A-Za-z0-9\-_ .]", "_", name)

    # Turn spaces and dots between words into single underscore (cleaner folder names)
    name = re.sub(r"[ .]+", "_", name)

    # Collapse multiple underscores
    name = re.sub(r"_+", "_", name)

    # Strip underscores and dashes from ends
    name = name.strip("_-")

    # Enforce max length
    if len(name) > max_len:
        name = name[:max_len].rstrip("_-")

    return name or "unknown"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Path to CSV with columns: image, event")
    ap.add_argument("--images-dir", default="images", help="Folder where source images live")
    ap.add_argument("--events-dir", default="events", help="Destination root folder")
    ap.add_argument("--dry-run", action="store_true", help="Print actions without copying")
    args = ap.parse_args()

    csv_path = args.csv
    images_dir = args.images_dir
    events_dir = args.events_dir

    if not os.path.exists(csv_path):
        print(f"❌ CSV not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(images_dir):
        print(f"❌ Images directory not found: {images_dir}", file=sys.stderr)
        sys.exit(1)

    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"❌ Failed to read CSV: {e}", file=sys.stderr)
        sys.exit(1)

    # Make column name access case-insensitive / tolerant
    cols = {c.lower(): c for c in df.columns}
    if "image_name" not in cols or "event" not in cols:
        print(f"❌ CSV must contain 'image' and 'event' columns. Found: {list(df.columns)}", file=sys.stderr)
        sys.exit(1)

    image_col = cols["image_name"]
    event_col = cols["event"]

    os.makedirs(events_dir, exist_ok=True)

    missing = 0
    copied = 0
    for i, row in df.iterrows():
        raw_img = str(row.get(image_col, "")).strip()
        raw_evt = str(row.get(event_col, "")).strip()

        if not raw_img:
            print(f"[row {i}] ⚠️ Empty image field; skipping")
            continue

        # We only look up by basename inside images_dir
        src_basename = os.path.basename(raw_img)
        src_path = os.path.join(images_dir, src_basename)

        evt_folder = sanitize_name(raw_evt)
        dest_folder = os.path.join(events_dir, evt_folder)
        dest_path = os.path.join(dest_folder, src_basename)

        if not os.path.isfile(src_path):
            print(f"[row {i}] ❌ Not found: {src_path}")
            missing += 1
            continue

        if args.dry_run:
            print(f"[DRY] Would copy: {src_path} -> {dest_path}")
            copied += 1
            continue

        os.makedirs(dest_folder, exist_ok=True)

        try:
            # copy2 preserves basic metadata (mtime, etc.)
            shutil.copy2(src_path, dest_path)
            print(f"✅ Copied: {src_path} -> {dest_path}")
            copied += 1
        except Exception as e:
            print(f"[row {i}] ❌ Failed copy {src_path} -> {dest_path}: {e}")

    print("\n--- Summary ---")
    print(f"Copied:  {copied}")
    print(f"Missing: {missing}")
    print(f"Events root: {os.path.abspath(events_dir)}")

if __name__ == "__main__":
    main()
