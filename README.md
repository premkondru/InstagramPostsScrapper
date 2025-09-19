# Instagram Posts → Image Downloader & Event Organizer

This toolkit helps you:

1. **Ingest** an [Apify Instagram Post Scraper](https://apify.com/apify/instagram-post-scraper) export (Excel).
2. **Download** the representative image for each post.
3. **Convert** images into consistent `.jpg` format (optional).
4. **Organize** the images into **event-wise folders**.

---

## 📂 Repository Contents

* **`dataset_instagram-post-scraper_2025-09-15_12-33-25-425.xlsx`**
  Input dataset exported from **Apify Instagram Post Scraper** (contains post URLs, captions, etc.).

* **`downloadimages.py`**
  Downloads images from posts listed in a CSV input.

* **`downloadimagesasjpg.py`**
  Like above, but ensures downloaded files are converted to JPEG (with options to convert only WEBP/HEIC, or force everything).

* **`downloadimagesasjpgforce.py`**
  Strict variant that forces **all images** to a single format (e.g. `jpg`).

* **`copy_images_to_events.py`**
  Organizes downloaded images into `/events/<EventName>/` folders based on an `event` column in the CSV.

---

## 🔄 Workflow

1. **Convert Apify Excel → CSV**
   Scripts expect a CSV. Convert with Python:

   ```python
   import pandas as pd
   df = pd.read_excel("dataset_instagram-post-scraper_2025-09-15_12-33-25-425.xlsx")
   df.to_csv("posts_input.csv", index=False)
   ```

   Now you have `posts_input.csv` with columns like `url`, `caption`, etc.

2. **Download Images**
   Run one of the downloaders:

   ```bash
   # Basic downloader
   python downloadimages.py \
     --in-csv posts_input.csv \
     --out-csv posts_downloaded.csv \
     --images-dir ./images

   # Convert WEBP/HEIC to JPG
   python downloadimagesasjpg.py \
     --in-csv posts_input.csv \
     --out-csv posts_jpg.csv \
     --images-dir ./images_jpg \
     --convert-webp jpg \
     --convert-heic jpg

   # Force everything to JPG
   python downloadimagesasjpgforce.py \
     --in-csv posts_input.csv \
     --out-csv posts_force_jpg.csv \
     --images-dir ./images_force_jpg \
     --force-format jpg
   ```

   Each script produces:

   * An **images folder** (`--images-dir`)
   * A **CSV manifest** (`--out-csv`) with:

     ```
     post_url, image_url, caption, hashtags, local_image_path
     ```

3. **Add Events to Manifest**
   To organize images into event folders, your manifest must have an `event` column. You can:

   * Add it manually in Excel/Sheets, or
   * Enrich programmatically (e.g., map hashtags → events).

4. **Organize by Event**
   Once the manifest has `event` filled:

   ```bash
   python copy_images_to_events.py \
     --csv posts_with_events.csv \
     --images-dir ./images_force_jpg \
     --events-dir ./events
   ```

   Result:

   ```
   /events/
     Techniche/
       abc123.jpg
     CulturalNight/
       def456.jpg
   ```

---

## ⚙️ Script Parameters

### `downloadimages.py`

```
usage: downloadimages.py --in-csv IN_CSV --out-csv OUT_CSV
                         [--images-dir IMAGES_DIR] [--timeout TIMEOUT]
                         [--retries RETRIES]
```

* `--in-csv` *(required)*: Input CSV with `url` column.
* `--out-csv` *(required)*: Output CSV manifest.
* `--images-dir`: Destination folder (default `./images`).
* `--timeout`: HTTP timeout in seconds (default `15`).
* `--retries`: Download retries (default `3`).

---

### `downloadimagesasjpg.py`

```
usage: downloadimagesasjpg.py --in-csv IN_CSV --out-csv OUT_CSV
                              [--images-dir IMAGES_DIR] [--timeout TIMEOUT]
                              [--retries RETRIES]
                              [--convert-webp CONVERT_WEBP]
                              [--convert-heic CONVERT_HEIC]
                              [--force-format FORCE_FORMAT]
```

Extra options:

* `--convert-webp jpg|png`: Convert WEBP images.
* `--convert-heic jpg|png`: Convert HEIC/HEIF images.
* `--force-format jpg|png`: Convert **all** images.

---

### `downloadimagesasjpgforce.py`

```
usage: downloadimagesasjpgforce.py --in-csv IN_CSV --out-csv OUT_CSV
                                   [--images-dir IMAGES_DIR]
                                   [--timeout TIMEOUT] [--retries RETRIES]
                                   [--convert-webp CONVERT_WEBP]
                                   [--convert-heic CONVERT_HEIC]
                                   [--force-format FORCE_FORMAT]
```

Same as above — but defaults to enforcing a single format for every image.

---

### `copy_images_to_events.py`

```
usage: copy_images_to_events.py --csv CSV [--images-dir IMAGES_DIR]
                                [--events-dir EVENTS_DIR] [--dry-run]
```

* `--csv` *(required)*: CSV with `image` and `event` columns.
* `--images-dir`: Source images folder.
* `--events-dir`: Destination root folder (default `./events`).
* `--dry-run`: Print planned actions without copying.

---

## 📊 Example End-to-End

```bash
# Convert Apify Excel → CSV
python - <<'PY'
import pandas as pd
df = pd.read_excel("dataset_instagram-post-scraper_2025-09-15_12-33-25-425.xlsx")
df.to_csv("posts_input.csv", index=False)
print("CSV ready:", len(df), "rows")
PY

# Download and force JPG output
python downloadimagesasjpgforce.py \
  --in-csv posts_input.csv \
  --out-csv posts_force_jpg.csv \
  --images-dir images_force_jpg \
  --force-format jpg

# Organize into event folders (after adding `event` column)
python copy_images_to_events.py \
  --csv posts_with_events.csv \
  --images-dir images_force_jpg \
  --events-dir events
```

---

## 📝 Notes

* If downloads produce only Instagram logos → it means login/consent walls. Re-run with a stricter resolver (e.g. `instagram_download_images_strict.py` with `--embed-first --use-ddinstagram`).
* Always check Instagram/Apify’s terms before scraping or redistributing content.

---

Do you want me to also create a **sample `posts_with_events.csv` template** (from your dataset) so you can just fill in the `event` column and run the event organizer immediately?
