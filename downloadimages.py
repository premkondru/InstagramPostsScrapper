#!/usr/bin/env python3
"""
download_images_and_update_csv.py


Reads an input CSV with columns: url, caption, hashtags
Downloads each image in `url` to an images folder
Writes an output CSV that adds a new column: image_name

Usage:
  python download_images_and_update_csv.py \
    --in-csv ./urls_captions_hashtags.csv \
    --out-csv ./urls_captions_hashtags_with_images.csv \
    --images-dir ./images \
    --timeout 15 \
    --retries 3
"""

import argparse
import base64
import csv
import hashlib
import mimetypes
import os
import re
import sys
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

import requests


def guess_ext_from_content_type(ct: Optional[str]) -> str:
    """Return a reasonable file extension (including the dot) from a Content-Type."""
    if not ct:
        return ".jpg"
    # Normalize e.g., 'image/jpg' -> '.jpg'
    ext = mimetypes.guess_extension(ct.split(";")[0].strip())
    if ext:
        # Some systems return .jpe for image/jpeg
        return ".jpg" if ext in [".jpe", ".jpeg", ".jpg"] else ext
    # default fallback
    if ct.startswith("image/"):
        subtype = ct.split("/", 1)[-1]
        if subtype in ("jpeg", "jpg"):
            return ".jpg"
        if subtype in ("png", "gif", "webp", "bmp", "tiff"):
            return "." + subtype
    return ".jpg"


def guess_name_and_ext_from_url(url: str) -> Tuple[str, str]:
    """
    Try to get a filename stem and extension from the URL path.
    If missing, return ("download", ".jpg") as a safe default.
    """
    parsed = urlparse(url)
    name = os.path.basename(parsed.path)  # may be empty
    if not name:
        return "download", ".jpg"
    # Strip query fragments
    name = re.sub(r"[?#].*$", "", name)
    stem, dot, ext = name.rpartition(".")
    if not dot:
        return name, ".jpg"
    # Normalize jpeg variations
    ext = ext.lower()
    if ext in ("jpeg", "jpe", "jpg"):
        ext = "jpg"
    return stem or "download", f".{ext}"


def sanitize_filename(s: str) -> str:
    """Keep filename filesystem-safe."""
    s = re.sub(r"[^\w\-.]+", "_", s, flags=re.UNICODE)
    s = s.strip("._")
    return s or "file"


def unique_path(dirpath: Path, filename: str) -> Path:
    """Ensure filename is unique inside dirpath by appending -1, -2, ... if needed."""
    base = Path(filename).stem
    ext = Path(filename).suffix
    candidate = dirpath / (base + ext)
    i = 1
    while candidate.exists():
        candidate = dirpath / f"{base}-{i}{ext}"
        i += 1
    return candidate


def save_data_url(data_url: str, out_dir: Path, url_hash: str) -> str:
    """
    Save a data: URL (e.g., data:image/png;base64,....)
    Returns the saved filename (not full path).
    """
    try:
        header, b64data = data_url.split(",", 1)
    except ValueError:
        # Malformed; save nothing
        return ""
    # Example header: data:image/png;base64
    m = re.match(r"data:(.*?)(;base64)?$", header)
    content_type = None
    is_b64 = False
    if m:
        content_type = (m.group(1) or "").strip() or None
        is_b64 = bool(m.group(2))
    ext = guess_ext_from_content_type(content_type)
    stem = f"img_{url_hash[:10]}"
    fname = sanitize_filename(stem) + ext
    out_path = unique_path(out_dir, fname)

    try:
        if is_b64:
            payload = base64.b64decode(b64data)
        else:
            # URL-encoded plain data; try best-effort decode
            payload = b64data.encode("utf-8")
        out_path.write_bytes(payload)
        return out_path.name
    except Exception:
        return ""


def download_http_image(url: str, out_dir: Path, timeout: int, retries: int) -> str:
    """
    Download an HTTP/HTTPS image, return saved filename (empty string on failure).
    """
    # Build a stable base name using URL hash for uniqueness
    url_hash = hashlib.sha1(url.encode("utf-8")).hexdigest()

    # initial name guess from URL
    stem, ext_from_url = guess_name_and_ext_from_url(url)
    stem = sanitize_filename(stem)
    # in case stem is too short or generic, prefer hash
    if stem.lower() in ("", "download", "image", "img"):
        stem = f"img_{url_hash[:10]}"

    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            with requests.get(url, stream=True, timeout=timeout) as r:
                r.raise_for_status()
                # Determine extension from content-type if possible
                ct = r.headers.get("Content-Type")
                ext = guess_ext_from_content_type(ct) or ext_from_url
                # If the URL has an image extension already, keep it
                if ext_from_url and ext_from_url != ".jpg":
                    ext = ext_from_url
                fname = f"{stem}{ext}"
                out_path = unique_path(out_dir, fname)

                with open(out_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                return out_path.name
        except Exception as e:
            last_exc = e
    # Failed after retries
    sys.stderr.write(f"[WARN] Failed to download {url}: {last_exc}\n")
    return ""


def process_csv(in_csv: Path, out_csv: Path, images_dir: Path, timeout: int, retries: int):
    images_dir.mkdir(parents=True, exist_ok=True)

    # We’ll preserve all original columns and append image_name at the end
    with in_csv.open("r", newline="", encoding="utf-8") as fin:
        reader = csv.DictReader(fin)
        fieldnames = list(reader.fieldnames) if reader.fieldnames else ["url", "caption", "hashtags"]
        if "image_name" not in fieldnames:
            fieldnames.append("image_name")

        rows_out = []
        for i, row in enumerate(reader, 1):
            url = (row.get("url") or "").strip()
            saved_name = ""

            if url:
                if url.startswith("data:"):
                    saved_name = save_data_url(url, images_dir, hashlib.sha1(url.encode("utf-8")).hexdigest())
                else:
                    parsed = urlparse(url)
                    if parsed.scheme in ("http", "https"):
                        saved_name = download_http_image(url, images_dir, timeout=timeout, retries=retries)
                    else:
                        # Could be file path or unsupported scheme; try to copy if local file exists
                        p = Path(url)
                        if p.exists() and p.is_file():
                            # Copy with unique name
                            ext = p.suffix or ".jpg"
                            stem = f"img_{hashlib.sha1(str(p).encode('utf-8')).hexdigest()[:10]}"
                            dest = unique_path(images_dir, sanitize_filename(stem) + ext)
                            dest.write_bytes(p.read_bytes())
                            saved_name = dest.name
                        else:
                            sys.stderr.write(f"[WARN] Unsupported/invalid URL: {url}\n")

            row["image_name"] = saved_name
            rows_out.append(row)

    with out_csv.open("w", newline="", encoding="utf-8") as fout:
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_out)

    print(f"Saved images to: {images_dir}")
    print(f"Wrote updated CSV: {out_csv}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-csv", required=True, help="Path to input CSV with columns including `url`")
    ap.add_argument("--out-csv", required=True, help="Path to output CSV to write")
    ap.add_argument("--images-dir", default="./images", help="Directory to save images (default: ./images)")
    ap.add_argument("--timeout", type=int, default=15, help="HTTP timeout in seconds (default: 15)")
    ap.add_argument("--retries", type=int, default=3, help="Number of download retries (default: 3)")
    args = ap.parse_args()

    in_csv = Path(args.in_csv)
    out_csv = Path(args.out_csv)
    images_dir = Path(args.images_dir)

    if not in_csv.exists():
        print(f"Input CSV not found: {in_csv}", file=sys.stderr)
        sys.exit(1)

    process_csv(in_csv, out_csv, images_dir, timeout=args.timeout, retries=args.retries)


if __name__ == "__main__":
    main()
