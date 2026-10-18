#!/usr/bin/env python3
"""
Pesticides banned in the EU that EU countries planned to export, 2024, for
the Invasion of non-humans map (round nh2, asked 16 October).

Source: Unearthed (Greenpeace UK) and Public Eye, "Interactive map: the EU's
banned pesticide trade" (16 December 2025), the spreadsheet the map offers
for download: nearly 2,000 export notifications for 2024, obtained under
freedom of information laws. The page states no licence; the owner chose to
use it (16 October 2026). Export notifications are plans, not proof that the
exports happened (Unearthed's own caveat).

Every row of every sheet is kept as it is. The columns that name the
exporting country, the destination, the active ingredient, the company and the
amount are found by their headings (written to the build file); countries are
matched to the map's country shapes by name, and a point inside each is given
for drawing the flows.

  nonhuman/banned_exports.json, nonhuman/banned_exports.build.json

Weekly (in case a new year's spreadsheet appears at the same address);
BANNEDEXPORTS_REBUILD=1 or a run by hand builds at once.
"""
import collections, json, math, pathlib, re, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402

NAME = "banned_exports"
XLSX = "https://storage.googleapis.com/unearthed-projects/pesticides-map/data/2024_EU_banned_pesticide_exports.xlsx"
PAGE = "https://unearthed.greenpeace.org/2025/12/16/interactive-map-eu-banned-pesticide-trade/"


def find(cols, *pats, avoid=None):
    """The first heading matching a pattern; where the spreadsheet gives a
    tidied copy of a column (its heading ending in CLEAN), that copy."""
    for p in pats:
        hits = [c for c in cols if re.search(p, str(c), re.I) and not (avoid and re.search(avoid, str(c), re.I))]
        if hits:
            return next((c for c in hits if re.search(r"\bclean\s*$", str(c), re.I)), hits[0])
    return None


def fnum(v):
    try:
        x = float(str(v).replace(",", "").strip())
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def main():
    if not nh.due(NAME, 7, "BANNEDEXPORTS_REBUILD"):
        return
    nh.pip("pandas", "openpyxl", "shapely")
    import pandas as pd
    from shapely.geometry import shape
    p = nh.download(XLSX, pathlib.Path(tempfile.mkdtemp()) / "exports.xlsx", "banned exports")
    book = pd.read_excel(p, sheet_name=None, dtype=str)
    C = nh.Countries()
    gj = nh.get_json(nh.BOUNDARIES)
    where = {}
    for f in gj["features"]:
        iso = (f.get("properties") or {}).get("iso3")
        if iso:
            try:
                pt = shape(f["geometry"]).representative_point()
                where[iso] = [round(pt.x, 3), round(pt.y, 3)]
            except Exception:
                pass
    sheets, report, notes = {}, {}, []
    for name, df in book.items():
        df = df.dropna(how="all")
        cols = [str(c) for c in df.columns]
        df.columns = cols
        exp = find(cols, r"export\w*\s*country|exporting|from\b|origin|member state|exporter country", avoid=r"compan|firm|address")
        dst = find(cols, r"destination|import\w*\s*country|importing|to\b|recipient", avoid=r"continent|income")
        ai = find(cols, r"chemical name|active|substance|ingredient|pesticide", avoid=r"concentration|more than one|mixture")
        co = find(cols, r"exporter name|compan|firm|business")
        qty = find(cols, r"expected yearly amount|tonne|\bkg\b|quantit|amount|volume|weight")
        used = {"exporting country": exp, "destination": dst, "active ingredient": ai, "company": co, "amount": qty}
        # Only sheets of notifications; a pivot table or a sheet of notes
        # is not one (the notes are kept as text).
        if not (exp and dst):
            if re.search(r"note", name, re.I):
                notes += [str(v).strip() for v in df.astype(str).values.ravel().tolist() + cols if str(v).strip() and str(v).strip().lower() not in ("nan", "notes:")]
            report[name] = {"rows": len(df), "columns": cols, "skipped": "not a sheet of notifications"}
            continue
        rows = []
        for _, r in df.iterrows():
            rec = {c: (None if (v is None or (isinstance(v, float) and math.isnan(v)) or str(v).strip().lower() == "nan") else str(v).strip()) for c, v in r.items()}
            rec["_from"] = C.by_name(rec.get(exp)) if exp else None
            rec["_to"] = C.by_name(rec.get(dst)) if dst else None
            rec["_amount"] = fnum(rec.get(qty)) if qty else None
            rows.append({k: v for k, v in rec.items() if v is not None})
        sheets[name] = {"columns": cols, "used": used, "rows": rows}
        report[name] = {"rows": len(rows), "columns": cols, "used": used,
                        "names not matched to a country": sorted({rec.get(c) for rec in rows for c, k in ((exp, "_from"), (dst, "_to")) if c and rec.get(c) and not rec.get(k)})}
    isos = {rec.get(k) for s in sheets.values() for rec in s["rows"] for k in ("_from", "_to") if rec.get(k)}
    out = {"source": "Unearthed (Greenpeace UK) and Public Eye, EU banned pesticide export notifications, 2024", "page": PAGE, "file": XLSX,
           "unit": "kg or litres a year, as notified", "notes": notes,
           "unit_column": {n: s["used"]["amount"] for n, s in sheets.items()}, "sheets": sheets, "points": {i: where[i] for i in isos if i in where},
           "made": nh.datetime.datetime.utcnow().strftime("%Y-%m-%d")}
    nh.write_json("banned_exports.json", out)
    nh.write_stamp(NAME, {"sheets": report, "failed": not any(s["rows"] for s in sheets.values())})


if __name__ == "__main__":
    main()
