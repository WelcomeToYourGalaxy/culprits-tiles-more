#!/usr/bin/env python3
"""
Which pesticides each country has banned, for the Invasion of non-humans map
(round nh2, asked 16 October).

Source: PAN International, Consolidated List of Banned Pesticides (the
spreadsheet on pan-international.org, edition of December 2024; PAN updates it
about yearly; read its Explanatory Note before use). No licence is stated on
the page; the owner chose to use it (16 October 2026).

The spreadsheet's layout is read from its headings and written to the build
file: either a table with a row per active ingredient and a column per
country (a mark where it is banned), or rows naming a country and an
ingredient. Every country and every ingredient is kept. Countries are matched
to the map's country shapes by name; any not matched are listed as unplaced
with their bans. A country that does not list an ingredient has not
necessarily allowed it: the list records bans that PAN found.

  nonhuman/pan_bans.json, nonhuman/pan_bans.build.json

Weekly (PAN may publish a new edition at a new address: the script looks for
the newest spreadsheet linked from PAN's page); PANBANS_REBUILD=1 or a run by
hand builds at once.
"""
import collections, pathlib, re, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402

NAME = "pan_bans"
PAGE = "https://pan-international.org/pan-international-consolidated-list-of-banned-pesticides/"
KNOWN = "https://pan-international.org/wp-content/uploads/PAN-Consolidated-List-of-Bans_2024_FINAL.xlsx"
NOTE = "https://pan-international.org/wp-content/uploads/PAN-Consolidated-List-ExplanatoryNote-2024_FINAL.pdf"


def newest():
    try:
        html = nh.get(PAGE, 120).decode("utf-8", "replace")
        links = re.findall(r'href="([^"]+?\.xlsx?)"', html, re.I)
        links = [l for l in links if re.search(r"ban", l, re.I)]
        if links:
            return sorted(links, key=lambda l: re.findall(r"20\d\d", l) or ["0"])[-1]
    except Exception as e:
        print(f"pan bans: the page could not be read ({e}); using the known address")
    return KNOWN


def main():
    if not nh.due(NAME, 7, "PANBANS_REBUILD"):
        return
    nh.pip("pandas", "openpyxl", "xlrd")
    import pandas as pd
    url = newest()
    p = nh.download(url, pathlib.Path(tempfile.mkdtemp()) / url.rsplit("/", 1)[-1], "PAN list")
    book = pd.read_excel(p, sheet_name=None, header=None, dtype=str)
    C = nh.Countries()
    bans = collections.defaultdict(set)
    report = {"file": url, "sheets": {}}
    for sname, raw in book.items():
        raw = raw.dropna(how="all").dropna(axis=1, how="all")
        if raw.empty:
            continue
        # The heading row: the first of the top ten with the most cells that are country names.
        best, best_n = None, 0
        for i in range(min(10, len(raw))):
            n = sum(1 for v in raw.iloc[i] if isinstance(v, str) and C.by_name(v))
            if n > best_n:
                best, best_n = i, n
        if best is not None and best_n >= 5:
            head = list(raw.iloc[best])
            body = raw.iloc[best + 1:]
            ai_col = next((j for j, h in enumerate(head) if isinstance(h, str) and re.search(r"active|ingredient|pesticide|substance|chemical|name", h, re.I)), 0)
            countries = {j: h for j, h in enumerate(head) if isinstance(h, str) and j != ai_col and h.strip()}
            for _, r in body.iterrows():
                ai = r.iloc[ai_col]
                if not isinstance(ai, str) or not ai.strip():
                    continue
                for j, cname in countries.items():
                    v = r.iloc[j]
                    if isinstance(v, str) and v.strip() and v.strip().lower() not in ("nan", "0", "no", "-"):
                        bans[cname.strip()].add(ai.strip())
            report["sheets"][sname] = {"layout": "one column per country", "heading row": int(best) + 1, "country columns": len(countries),
                                       "ingredient column": str(head[ai_col])}
            continue
        # Otherwise: rows naming a country and an ingredient.
        head = [str(h) for h in raw.iloc[0]]
        cj = next((j for j, h in enumerate(head) if re.search(r"country", h, re.I)), None)
        aj = next((j for j, h in enumerate(head) if re.search(r"active|ingredient|pesticide|substance|chemical", h, re.I)), None)
        if cj is None or aj is None:
            report["sheets"][sname] = {"layout": "not read", "first row": head[:30]}
            continue
        for _, r in raw.iloc[1:].iterrows():
            c, a = r.iloc[cj], r.iloc[aj]
            if isinstance(c, str) and isinstance(a, str) and c.strip() and a.strip():
                bans[c.strip()].add(a.strip())
        report["sheets"][sname] = {"layout": "rows of country and ingredient", "country column": head[cj], "ingredient column": head[aj]}
    countries, unplaced = {}, {}
    for cname, ais in bans.items():
        iso = C.by_name(cname)
        target = countries if iso and iso not in countries else unplaced
        target[iso if iso and iso not in countries else cname] = {"name": cname, "banned": sorted(ais, key=str.lower)}
    ingredients = sorted({a for s in bans.values() for a in s}, key=str.lower)
    edition = (re.findall(r"20\d\d", url) or [None])[-1]
    nh.write_json("pan_bans.json", {"source": "PAN International, Consolidated List of Banned Pesticides", "edition": edition, "file": url, "note": NOTE,
                                    "page": PAGE, "ingredients": ingredients, "countries": countries, "unplaced": unplaced,
                                    "made": nh.datetime.datetime.utcnow().strftime("%Y-%m-%d")})
    nh.write_stamp(NAME, dict(report, countries=len(countries), unplaced=sorted(unplaced), ingredients=len(ingredients), failed=not countries))


if __name__ == "__main__":
    main()
