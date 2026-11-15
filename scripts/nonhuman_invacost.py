#!/usr/bin/env python3
"""
What invasive species have cost each country, year by year, for the Invasion
of non-humans map.

Source: InvaCost (Diagne, C. et al. 2020, "InvaCost, a public database of the
economic costs of biological invasions worldwide", Scientific Data 7: 277),
the newest release on figshare (article 12668570); which file and version are
written to the build file.

Every entry is kept. Each entry's cost per year (2017 US dollars, at the
exchange rate) is counted in every year from its probable starting year to
its probable ending year, as the InvaCost team's own expandYearlyCosts does,
in four piles: observed or potential, high or low method reliability.
Entries naming one country go to that country. Entries naming several
countries (written "A/B") are not divided: each named country carries them
separately as shared. Entries naming no country the map has a shape for are
listed as unplaced with their totals. Entries with no years are counted in
each country's figures as "no years given".

  nonhuman/invacost.json, nonhuman/invacost.build.json

Checked weekly for a new release; INVACOST_REBUILD=1 or a run by hand builds.
"""
import collections, math, pathlib, re, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402

NAME = "invacost"
ARTICLE = "https://api.figshare.com/v2/articles/12668570"


def col(cols, *names):
    low = {re.sub(r"[^a-z0-9]", "", c.lower()): c for c in cols}
    for n in names:
        k = re.sub(r"[^a-z0-9]", "", n.lower())
        if k in low:
            return low[k]
    return None


def fnum(v):
    try:
        x = float(str(v).replace(",", ""))
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def main():
    if not nh.due(NAME, 7, "INVACOST_REBUILD"):
        return
    nh.pip("pandas", "openpyxl")
    import pandas as pd
    art = nh.get_json(ARTICLE)
    files = art.get("files") or []
    cands = [f for f in files if re.search(r"\.(xlsx|csv)$", f.get("name", ""), re.I)]
    cands.sort(key=lambda f: (not re.search(r"invacost", f["name"], re.I), -int(f.get("size") or 0)))
    if not cands:
        nh.write_stamp(NAME, {"failed": True, "files": [f.get("name") for f in files]})
        raise SystemExit("invacost: no table in the article")
    f = cands[0]
    work = pathlib.Path(tempfile.mkdtemp())
    p = nh.download(f["download_url"], work / f["name"], f["name"])
    df = pd.read_excel(p, dtype=str) if p.suffix.lower() == ".xlsx" else pd.read_csv(p, dtype=str, encoding="utf-8", encoding_errors="replace")
    cols = list(df.columns)
    C_COUNTRY = col(cols, "Official_country")
    C_START = col(cols, "Probable_starting_year_adjusted", "Probable_starting_year")
    C_END = col(cols, "Probable_ending_year_adjusted", "Probable_ending_year")
    C_COST = col(cols, "Cost_estimate_per_year_2017_USD_exchange_rate")
    C_IMPL = col(cols, "Implementation")
    C_REL = col(cols, "Method_reliability")
    C_SP = col(cols, "Species")
    used = {"country": C_COUNTRY, "start": C_START, "end": C_END, "cost": C_COST, "implementation": C_IMPL, "reliability": C_REL, "species": C_SP}
    if not (C_COUNTRY and C_COST):
        nh.write_stamp(NAME, {"failed": True, "file": f["name"], "columns": cols, "used": used})
        raise SystemExit("invacost: country or cost column not found")
    C = nh.Countries()
    countries = collections.defaultdict(lambda: {"years": collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0.0]),
                                                 "shared": collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0.0]),
                                                 "entries": 0, "sharedEntries": 0, "noYears": [0.0, 0.0, 0.0, 0.0], "species": collections.Counter()})
    unplaced = collections.defaultdict(lambda: {"entries": 0, "total": 0.0})
    years_seen = []
    for _, r in df.iterrows():
        cost = fnum(r[C_COST])
        if cost is None:
            continue
        impl = str(r[C_IMPL] or "").strip().lower() if C_IMPL else ""
        rel = str(r[C_REL] or "").strip().lower() if C_REL else ""
        pile = (0 if impl.startswith("obs") else 2) + (0 if rel.startswith("high") else 1)
        y0, y1 = fnum(r[C_START]) if C_START else None, fnum(r[C_END]) if C_END else None
        span = list(range(int(y0), int(y1) + 1)) if y0 is not None and y1 is not None and y1 >= y0 and y1 - y0 < 400 else []
        years_seen += span[:1] + span[-1:]
        names = [n.strip() for n in re.split(r"/", str(r[C_COUNTRY] or "")) if n.strip() and n.strip().lower() != "nan"]
        found = {n: C.by_name(n) for n in names}
        isos = sorted({i for i in found.values() if i})
        # A value naming no country the map has (e.g. "Diverse/Unspecified")
        # is listed whole; a country it cannot place beside ones it can, alone.
        missed = [n for n, i in found.items() if not i]
        for n in ([str(r[C_COUNTRY]).strip()] if not isos and names else missed):
            unplaced[n]["entries"] += 1
            unplaced[n]["total"] += cost * max(1, len(span))
        sp = str(r[C_SP] or "").strip() if C_SP else ""
        for iso in isos:
            c = countries[iso]
            alone = len(names) == 1
            c["entries" if alone else "sharedEntries"] += 1
            target = c["years"] if alone else c["shared"]
            if span:
                for y in span:
                    target[y][pile] += cost
            elif alone:
                c["noYears"][pile] += cost
            if alone and sp and sp.lower() != "nan":
                c["species"][sp] += cost * max(1, len(span))
    out = {}
    for iso, c in countries.items():
        out[iso] = {"years": {str(y): [round(v, 2) for v in vals] for y, vals in sorted(c["years"].items())},
                    "shared": {str(y): [round(v, 2) for v in vals] for y, vals in sorted(c["shared"].items())},
                    "entries": c["entries"], "sharedEntries": c["sharedEntries"], "noYears": [round(v, 2) for v in c["noYears"]],
                    "species": [[s, round(v, 2)] for s, v in c["species"].most_common()]}
    version = re.search(r"v\s?(\d+(\.\d+)*)", f["name"], re.I)
    nh.write_json("invacost.json", {"source": "InvaCost (Diagne et al. 2020), figshare article 12668570", "version": version.group(0) if version else f["name"],
                                    "file": f["name"], "from": min(years_seen) if years_seen else 1960, "to": max(years_seen) if years_seen else 2020,
                                    "countries": out, "unplaced": [{"name": k, **v} for k, v in sorted(unplaced.items())],
                                    "made": nh.datetime.datetime.utcnow().strftime("%Y-%m-%d")})
    nh.write_stamp(NAME, {"file": f["name"], "article version": art.get("version"), "rows": int(len(df)), "columns used": used,
                          "countries": len(out), "unplaced names": len(unplaced)})


if __name__ == "__main__":
    main()
