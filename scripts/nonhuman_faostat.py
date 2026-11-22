#!/usr/bin/env python3
"""
Pesticide use and trade, country by country, every year FAO publishes, for
the Invasion of non-humans map.

Source: FAO, FAOSTAT, Pesticides Use (domain RP) and Pesticides Trade
(domain RT), from FAOSTAT's bulk downloads (the normalized CSVs). Every item,
every measure (element) and every year is kept. Countries are matched to the
map's country shapes by their UN M49 code; FAO's regional and world totals,
and areas with no shape (former countries such as "Sudan (former)"), are kept
in the file under "aggregates" and "unplaced".

  nonhuman/pest_use.json, nonhuman/pest_trade.json, nonhuman/faostat.build.json

Weekly; FAOSTAT_REBUILD=1 or a run by hand builds at once.
"""
import collections, csv, io, pathlib, re, sys, tempfile, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402

NAME = "faostat"
BULK = "https://bulks-faostat.fao.org/production/"
DOMAINS = [("pest_use.json", "Inputs_Pesticides_Use_E_All_Data_(Normalized).zip", "RP"),
           ("pest_trade.json", "Inputs_Pesticides_Trade_E_All_Data_(Normalized).zip", "RT")]


def read_csv(zpath):
    z = zipfile.ZipFile(zpath)
    names = [n for n in z.namelist() if n.lower().endswith(".csv") and "flag" not in n.lower() and "areacode" not in n.lower().replace(" ", "")]
    names.sort(key=lambda n: (not re.search(r"all_data", n, re.I), -z.getinfo(n).file_size))
    raw = z.read(names[0])
    for enc in ("utf-8-sig", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    return names[0], list(csv.DictReader(io.StringIO(text)))


def build(C, fname, zname, code, work):
    p = nh.download(BULK + zname, work / zname, code)
    inner, rows = read_csv(p)
    if not rows:
        raise RuntimeError("the table is empty")
    cols = list(rows[0].keys())
    series = collections.OrderedDict()
    aggregates = collections.defaultdict(lambda: collections.defaultdict(dict))
    unplaced = collections.Counter()
    years = []
    for r in rows:
        try:
            y = int(str(r.get("Year") or r.get("Year Code") or "").strip()[:4])
            v = float(str(r.get("Value", "")).replace(",", ""))
        except ValueError:
            continue
        item, el, unit = r.get("Item", "").strip(), r.get("Element", "").strip(), r.get("Unit", "").strip()
        area = r.get("Area", "").strip()
        m49 = (r.get("Area Code (M49)") or "").replace("'", "").strip()
        try:
            fao_code = int(str(r.get("Area Code") or "0").strip())
        except ValueError:
            fao_code = 0
        key = (item, el)
        s = series.setdefault(key, {"item": item, "element": el, "unit": unit, "data": collections.defaultdict(dict)})
        iso = None if fao_code >= 5000 else C.by_m49(m49)
        if iso:
            s["data"][iso][str(y)] = v
            years.append(y)
        elif fao_code >= 5000:
            aggregates[f"{item} | {el} ({unit})"][area][str(y)] = v
        else:
            unplaced[area] += 1
    out = {"source": f"FAO, FAOSTAT {code} (bulk download {zname})", "file": inner, "from": min(years) if years else None, "to": max(years) if years else None,
           "series": [dict(s, data=dict(s["data"])) for s in series.values()],
           "aggregates": {k: dict(v) for k, v in aggregates.items()}, "unplaced": dict(unplaced),
           "made": nh.datetime.datetime.utcnow().strftime("%Y-%m-%d")}
    nh.write_json(fname, out)
    return {"file": inner, "columns": cols, "rows": len(rows), "series": len(series), "items": sorted({k[0] for k in series}),
            "elements": sorted({k[1] for k in series}), "years": [out["from"], out["to"]], "unplaced areas": dict(unplaced)}


def main():
    if not nh.due(NAME, 7, "FAOSTAT_REBUILD"):
        return
    C = nh.Countries()
    work = pathlib.Path(tempfile.mkdtemp())
    report, ok = {}, 0
    for fname, zname, code in DOMAINS:
        try:
            report[code] = build(C, fname, zname, code, work)
            ok += 1
        except Exception as e:
            report[code] = {"error": str(e)[:300]}
            print(f"faostat {code}: {e}", flush=True)
    nh.write_stamp(NAME, dict(report, failed=ok == 0))
    if not ok:
        raise SystemExit("faostat: nothing read")


if __name__ == "__main__":
    main()
