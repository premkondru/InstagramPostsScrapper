#!/usr/bin/env python3
"""
download_images_and_update_csv_convert_webp.py

Reads an input CSV with columns incl. `url`, downloads images to an images dir,
converts .webp to a chosen format (default .jpg), and writes a new CSV
adding `image_name` with the final saved filename.

Usage:
  python download_images_and_update_csv_convert_webp.py \
    --in-csv ./urls_captions_hashtags.csv \
    --out-csv ./urls_captions_hashtags_with_images.csv \
    --images-dir ./images \
    --timeout 15 \
    --retries 3 \
    --convert-webp jpg
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
from PIL import Image, UnidentifiedImageError


def guess_ext_from_content_type(ct: Optional[str]) -> str:
    if not ct:
        return ".jpg"
    ext = mimetypes.guess_extension(ct.split(";")[0].strip())
    if ext in [".jpe", ".jpeg", ".jpg"]:
        return ".jpg"
    if ext:
        return ext
    if ct.startswith("image/"):
        subtype = ct.split("/", 1)[-1]
        if subtype in ("jpeg", "jpg"):
            return ".jpg"
        return "." + subtype
    return ".jpg"


def guess_name_and_ext_from_url(url: str) -> Tuple[str, str]:
    parsed = urlparse(url)
    name = os.path.basename(parsed.path)
    if not name:
        return "download", ".jpg"
    name = re.sub(r"[?#].*$", "", name)
    stem, dot, ext = name.rpartition(".")
    if not dot:
        return name, ".jpg"
    ext = ext.lower()
    if ext in ("jpeg", "jpe", "jpg"):
        ext = "jpg"
    return stem or "download", f".{ext}"


def sanitize_filename(s: str) -> str:
    s = re.sub(r"[^\w\-.]+", "_", s, flags=re.UNICODE).strip("._")
    return s or "file"


def unique_path(dirpath: Path, filename: str) -> Path:
    base = Path(filename).stem
    ext = Path(filename).suffix
    candidate = dirpath / (base + ext)
    i = 1
    while candidate.exists():
        candidate = dirpath / f"{base}-{i}{ext}"
        i += 1
    return candidate


def save_data_url(data_url: str, out_dir: Path, url_hash: str) -> str:
    try:
        header, b64data = data_url.split(",", 1)
    except ValueError:
        return ""
    m = re.match(r"data:(.*?)(;base64)?$", header)
    content_type = (m.group(1) or "").strip() if m else None
    is_b64 = bool(m and m.group(2))
    ext = guess_ext_from_content_type(content_type)
    stem = f"img_{url_hash[:10]}"
    fname = sanitize_filename(stem) + ext
    out_path = unique_path(out_dir, fname)
    try:
        payload = base64.b64decode(b64data) if is_b64 else b64data.encode("utf-8")
        out_path.write_bytes(payload)
        return out_path.name
    except Exception:
        return ""


def download_http_image(url: str, out_dir: Path, timeout: int, retries: int) -> str:
    url_hash = hashlib.sha1(url.encode("utf-8")).hexdigest()
    stem, ext_from_url = guess_name_and_ext_from_url(url)
    stem = sanitize_filename(stem)
    if stem.lower() in ("", "download", "image", "img"):
        stem = f"img_{url_hash[:10]}"

    headers = {
        # Nudge servers to send common raster types
        "Accept": "image/avif,image/webp,image/apng,image/*;q=0.8,*/*;q=0.5",
        "User-Agent": "Mozilla/5.0 (compatible; ImageFetcher/1.0)",
    }

    last_exc = None
    for _ in range(retries):
        try:
            with requests.get(url, stream=True, timeout=timeout, headers=headers) as r:
                r.raise_for_status()
                ct = r.headers.get("Content-Type")
                ext = guess_ext_from_content_type(ct) or ext_from_url
                # If URL already has a known ext, keep it
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
    sys.stderr.write(f"[WARN] Failed to download {url}: {last_exc}\n")
    return ""


def convert_if_webp(images_dir: Path, filename: str, target_ext: str) -> str:
    """
    If filename is .webp, convert to target_ext (e.g., 'jpg' or 'png').
    Handles RGBA by compositing onto white; takes first frame for animations.
    Returns the possibly-updated filename.
    """
    if not filename.lower().endswith(".webp"):
        return filename

    src_path = images_dir / filename
    if not src_path.exists():
        return filename

    # Prepare destination name (same stem, new ext)
    target_ext = target_ext.lower().lstrip(".")
    dst_path = unique_path(images_dir, src_path.stem + f".{target_ext}")

    try:
        with Image.open(src_path) as im:
            # Animated webp: just take the first frame
            if getattr(im, "is_animated", False):
                im.seek(0)

            # Convert mode for JPEG/PNG
            if target_ext in ("jpg", "jpeg"):
                # composite RGBA over white
                if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                    bg = Image.new("RGB", im.size, (255, 255, 255))
                    im = im.convert("RGBA")
                    bg.paste(im, mask=im.split()[-1])
                    im = bg
                else:
                    im = im.convert("RGB")
                im.save(dst_path, format="JPEG", quality=92, optimize=True)
            else:
                # PNG or others — preserve alpha if present
                if im.mode not in ("RGB", "RGBA"):
                    im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
                im.save(dst_path)

        # Remove original .webp after successful conversion
        try:
            src_path.unlink()
        except Exception:
            pass

        return dst_path.name
    except UnidentifiedImageError:
        sys.stderr.write(f"[WARN] Could not identify image for conversion: {src_path}\n")
        return filename
    except Exception as e:
        sys.stderr.write(f"[WARN] Failed to convert {src_path} -> {dst_path}: {e}\n")
        return filename


def process_csv(in_csv: Path, out_csv: Path, images_dir: Path, timeout: int, retries: int, convert_webp_to: str):
    images_dir.mkdir(parents=True, exist_ok=True)

    import pandas as pd
    df = pd.read_csv(in_csv)

    # Preserve all original columns; add/replace image_name
    if "image_name" not in df.columns:
        df["image_name"] = ""

    for i, row in df.iterrows():
        url = str(row.get("url", "") or "").strip()
        saved_name = ""

        if url:
            if url.startswith("data:"):
                saved_name = save_data_url(url, images_dir, hashlib.sha1(url.encode("utf-8")).hexdigest())
            else:
                parsed = urlparse(url)
                if parsed.scheme in ("http", "https"):
                    saved_name = download_http_image(url, images_dir, timeout=timeout, retries=retries)
                else:
                    p = Path(url)
                    if p.exists() and p.is_file():
                        ext = p.suffix or ".jpg"
                        stem = f"img_{hashlib.sha1(str(p).encode('utf-8')).hexdigest()[:10]}"
                        dest = unique_path(images_dir, sanitize_filename(stem) + ext)
                        dest.write_bytes(p.read_bytes())
                        saved_name = dest.name
                    else:
                        sys.stderr.write(f"[WARN] Unsupported/invalid URL: {url}\n")

        # Convert .webp if requested
        if saved_name and saved_name.lower().endswith(".webp") and convert_webp_to:
            saved_name = convert_if_webp(images_dir, saved_name, convert_webp_to)

        df.at[i, "image_name"] = saved_name

    df.to_csv(out_csv, index=False)
    print(f"Saved images to: {images_dir}")
    print(f"Wrote updated CSV: {out_csv}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-csv", required=True)
    ap.add_argument("--out-csv", required=True)
    ap.add_argument("--images-dir", default="./images")
    ap.add_argument("--timeout", type=int, default=15)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--convert-webp", default="jpg", help="Target format for .webp (e.g., 'jpg' or 'png'). Empty to disable.")
    args = ap.parse_args()

    in_csv = Path(args.in_csv)
    out_csv = Path(args.out_csv)
    images_dir = Path(args.images_dir)

    if not in_csv.exists():
        print(f"Input CSV not found: {in_csv}", file=sys.stderr)
        sys.exit(1)

    process_csv(
        in_csv=in_csv,
        out_csv=out_csv,
        images_dir=images_dir,
        timeout=args.timeout,
        retries=args.retries,
        convert_webp_to=args.convert_webp.strip().lower(),
    )


if __name__ == "__main__":
    main()
