#!/usr/bin/env python3
"""
Copies of the Atlas for the End of the World's hotspot PDFs, for the Culprits
map to draw the placed first pages from the PDF itself: the pages are drawn
anew at every zoom (by pdf.js, in the browser), so their lines and names stay
sharp however close one goes, where the pictures made from them blur (the
owner, 26 September). The Atlas's own server does not let another site read
its files, so the map reads these copies.

  atlas/pdfs/<slug>.pdf     the PDF as the Atlas publishes it, unchanged
  atlas/pdfs.json           for each: bytes, pages, and when it was copied

A PDF is copied again only when the Atlas's file changes (its size or its
Last-Modified); one over 95 MB is not copied and is named in pdfs.json.
"""
import json, pathlib, sys, time, urllib.request

PDF_BASE = "https://atlas-for-the-end-of-the-world.com/hotspots/"
UA = {"User-Agent": "welcometoyourgalaxy-atlas/1.0 (+https://welcometoyourgalaxy.com)"}
SLUGS = ["atlantic_forests", "california_floristic_province", "cape_floristic_region", "caribbean_islands", "caucasus", "cerrado",
         "chilean_valdivian_forests", "coastal_forests_of_eastern_africa", "east_melanesian_islands", "eastern_afromontane",
         "forests_of_east_australia", "guinean_forests_of_west_africa", "himalaya", "horn_of_africa", "japan", "madagascar",
         "madrean_woodlands", "maputaland_pondoland_albany", "mediterranean_basin", "mesoamerica", "mountains_of_central_asia",
         "mountains_of_southwest_china", "new_caledonia", "new_zealand", "philippines", "north_american_coastal_plain",
         "southwest_australia", "succulent_karoo", "sundaland", "tropical_andes", "wallacea", "western_ghats_sri_lanka"]
OUT = pathlib.Path("atlas/pdfs")
LIMIT = 95 * 1024 * 1024


def head(url):
    req = urllib.request.Request(url, headers=UA, method="HEAD")
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.headers.get("Content-Length"), r.headers.get("Last-Modified")


def get(url):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=600) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == 3:
                raise
            print(f"    {url}: {e}", flush=True)
            time.sleep(20 * (i + 1))


def pages_of(b):
    try:
        import fitz
    except ImportError:
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pymupdf"], check=True)
        import fitz
    return fitz.open(stream=b, filetype="pdf").page_count


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index_path = OUT.parent / "pdfs.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    for slug in SLUGS:
        url = PDF_BASE + slug + ".pdf"
        try:
            size, modified = head(url)
        except Exception as e:  # noqa: BLE001
            size, modified = None, None
            print(f"  {slug}: no answer to a HEAD request ({e}); fetching", flush=True)
        was = index.get(slug, {})
        if (OUT / f"{slug}.pdf").exists() and size and was.get("remote_bytes") == size and was.get("last_modified") == modified:
            continue
        try:
            b = get(url)
        except Exception as e:  # noqa: BLE001
            print(f"  {slug}: could not be read ({e}); its last copy stays", flush=True)
            continue
        if len(b) > LIMIT:
            index[slug] = {"error": f"{len(b) / 1e6:.0f} MB, over the {LIMIT / 1e6:.0f} MB limit; not copied", "source": url}
            print(f"  {slug}: too large ({len(b) / 1e6:.0f} MB)", flush=True)
            continue
        (OUT / f"{slug}.pdf").write_bytes(b)
        index[slug] = {"source": url, "bytes": len(b), "pages": pages_of(b), "remote_bytes": size, "last_modified": modified,
                       "copied": time.strftime("%Y-%m-%d")}
        print(f"  {slug}: {len(b) / 1e6:.1f} MB, {index[slug]['pages']} pages", flush=True)
        index_path.write_text(json.dumps(index, indent=1))
    index_path.write_text(json.dumps(index, indent=1))


if __name__ == "__main__":
    main()
