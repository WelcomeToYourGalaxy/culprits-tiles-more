#!/usr/bin/env python3
"""
A look at the Atlas for the End of the World's hotspot PDFs beyond the first
page, so their detailed maps (pages 8 to 12, the owner's note of 26
September: the city inset maps of urban growth and conflict) can be placed on
the Culprits map as the first pages already are.

For every hotspot PDF (the list is the map's own, as in culprits
pipeline/atlas_plates.py) this saves under probe/atlas_pages/:
  <slug>.json          page count; for each page from 2 on: its size, every
                       piece of text with its box and type size, every
                       picture on it with its box, and the rectangles drawn
                       on it (the frames of inset maps)
  <slug>_p<n>.webp     pages 8 to 12 drawn at 1200 px across, to look at

Nothing is published to the map from this. Runs by hand (Actions > refresh >
atlas_pages_probe) and does nothing for a hotspot already read.
"""
import io, json, os, pathlib, subprocess, sys, time, urllib.request

PDF_BASE = "https://atlas-for-the-end-of-the-world.com/hotspots/"
UA = {"User-Agent": "welcometoyourgalaxy-atlas/1.0 (+https://welcometoyourgalaxy.com)"}
SLUGS = ["atlantic_forests", "california_floristic_province", "cape_floristic_region", "caribbean_islands", "caucasus", "cerrado",
         "chilean_valdivian_forests", "coastal_forests_of_eastern_africa", "east_melanesian_islands", "eastern_afromontane",
         "forests_of_east_australia", "guinean_forests_of_west_africa", "himalaya", "horn_of_africa", "japan", "madagascar",
         "madrean_woodlands", "maputaland_pondoland_albany", "mediterranean_basin", "mesoamerica", "mountains_of_central_asia",
         "mountains_of_southwest_china", "new_caledonia", "new_zealand", "philippines", "north_american_coastal_plain",
         "southwest_australia", "succulent_karoo", "sundaland", "tropical_andes", "wallacea", "western_ghats_sri_lanka"]
PICTURE_PAGES = range(8, 13)
OUT = pathlib.Path("probe/atlas_pages")


def need():
    try:
        import fitz  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pymupdf", "pillow"], check=True)


def get(url):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == 3:
                raise
            print(f"    {url}: {e}", flush=True)
            time.sleep(20 * (i + 1))


def main():
    if os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch") != "workflow_dispatch":
        print("atlas_pages_probe: by hand only")
        return
    need()
    import fitz
    from PIL import Image
    OUT.mkdir(parents=True, exist_ok=True)
    for slug in SLUGS:
        if (OUT / f"{slug}.json").exists():
            continue
        try:
            doc = fitz.open(stream=get(PDF_BASE + slug + ".pdf"), filetype="pdf")
        except Exception as e:  # noqa: BLE001
            (OUT / f"{slug}.json").write_text(json.dumps({"error": str(e)}))
            continue
        info = {"pages": doc.page_count, "detail": {}}
        for n in range(2, doc.page_count + 1):
            page = doc[n - 1]
            text = []
            for b in page.get_text("dict")["blocks"]:
                for line in b.get("lines", []):
                    for sp in line.get("spans", []):
                        t = sp["text"].strip()
                        if t:
                            text.append([t, [round(v, 1) for v in sp["bbox"]], round(sp["size"], 1)])
            pics = [[round(v, 1) for v in page.get_image_bbox(img)] for img in page.get_images(full=True)
                    if page.get_image_bbox(img).is_valid]
            rects = []
            for d in page.get_drawings():
                r = d.get("rect")
                if r and r.width > 60 and r.height > 60:
                    rects.append([round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1)])
            info["detail"][n] = {"size": [round(page.rect.width, 1), round(page.rect.height, 1)], "text": text,
                                 "pictures": pics, "rectangles": rects[:400]}
            if n in PICTURE_PAGES:
                pix = page.get_pixmap(matrix=fitz.Matrix(1200 / page.rect.width, 1200 / page.rect.width))
                Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB").save(OUT / f"{slug}_p{n}.webp", "WEBP", quality=70)
        (OUT / f"{slug}.json").write_text(json.dumps(info, ensure_ascii=False))
        print(f"  {slug}: {doc.page_count} pages", flush=True)


if __name__ == "__main__":
    main()
