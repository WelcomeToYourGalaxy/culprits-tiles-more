#!/usr/bin/env python3
"""
Round 130b (2 October; outstanding since 115b): what drug and medical-device
companies pay doctors and other prescribers in the United States, from CMS's
Open Payments (US government data, public domain), state by state, year by
year.

For every program year CMS publishes "General Payment Data" (every payment:
meals, travel, speaking and consulting fees, gifts), CMS's own data service
(openpaymentsdata.cms.gov, DKAN) is asked to add up the payments by the state
the recipient practises in and by the company that paid, so no multi-gigabyte
file is downloaded. Each state is drawn as its own shape (the owner's copy of
geoBoundaries, cgaz-boundaries USA), one shape for each state and year,
shaded by the amount paid there that year.

  openpay/states.geojson          one feature per state and year: total paid,
                                  companies paying, the 50 largest payers
  openpay/years/<year>.json       every state's every company and amount (the
                                  full list, linked from each box)
  openpay/build.json              years read, what CMS refused, counts

Research payments and ownership interests are separate CMS files and are not
added here. Weekly (Mondays) or by hand.

Round 188o: CMS's service takes about fifty minutes a year, so the run of
5 October stopped at its 160-minute limit after three of seven years and drew
nothing. Now a year once read is kept (read again only when its copy is more
than half a year old, as CMS republishes each June), the years still to read
are read within a time budget, and the map is drawn from every year read so
far; the next run goes on where this one stopped (build.json "waiting").
"""
import datetime, json, os, pathlib, re, sys, time, urllib.request

START, BUDGET = time.time(), 130 * 60
STALE_DAYS = 183

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from attacks_plain import rounded  # noqa: E402  Douglas-Peucker outline simplifier

OUT = pathlib.Path("openpay")
API = "https://openpaymentsdata.cms.gov/api/1"
CGAZ = "https://raw.githubusercontent.com/WelcomeToYourGalaxy/cgaz-boundaries/main/USA.geojson"
UA = {"User-Agent": "Culprits atlas build (WelcomeToYourGalaxy; welcometoyourgalaxy@gmail.com)", "Content-Type": "application/json"}
STATE = "recipient_state"
CO = "applicable_manufacturer_or_applicable_gpo_making_payment_name"
USD = "total_amount_of_payment_usdollars"
PAGES_PUBLIC = "https://welcometoyourgalaxy.github.io/culprits-tiles-more/openpay/years/"
NAMES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut",
         "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
         "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
         "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
         "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
         "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
         "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
         "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
         "PR": "Puerto Rico", "GU": "Guam", "VI": "United States Virgin Islands", "AS": "American Samoa", "MP": "Commonwealth of the Northern Mariana Islands"}


def call(url, body=None, timeout=300):
    data = json.dumps(body).encode() if body is not None else None
    last = None
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=UA), timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(10 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def general_years():
    items = call(f"{API}/metastore/schemas/dataset/items")
    out = {}
    for it in items:
        m = re.match(r"^\s*(\d{4})\s+General Payment Data", str(it.get("title", "")), re.I)
        if m:
            out[int(m.group(1))] = it["identifier"]
    return dict(sorted(out.items()))


def totals(ds):
    """Every (state, company) sum for one year, added up by CMS's own service."""
    rows, offset, size = [], 0, 500
    while True:
        body = {"properties": [STATE, CO,
                               {"expression": {"operator": "sum", "operands": [USD]}, "alias": "paid"},
                               {"expression": {"operator": "count", "operands": [USD]}, "alias": "payments"}],
                "groupings": [STATE, CO], "limit": size, "offset": offset, "count": False, "schema": False}
        got = call(f"{API}/datastore/query/{ds}/0", body).get("results") or []
        rows += got
        if len(got) < size:
            return rows
        offset += size


def fmt(v):
    return f"${v:,.0f}"


def main():
    stamp = OUT / "build.json"
    if stamp.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("open_payments: weekly; not Monday")
        return
    OUT.mkdir(exist_ok=True)
    (OUT / "years").mkdir(exist_ok=True)
    try:
        old = json.loads(stamp.read_text())
    except Exception:  # noqa: BLE001
        old = {}
    status = {"read": datetime.date.today().isoformat(), "years": {}, "refused": {}, "waiting": []}
    today = datetime.date.today()
    shapes = {}
    with urllib.request.urlopen(urllib.request.Request(CGAZ, headers={"User-Agent": UA["User-Agent"]}), timeout=300) as r:
        for f in json.loads(r.read())["features"]:
            shapes[f["properties"].get("shapeName")] = rounded(f["geometry"], 3, 0.01)
    years = general_years()
    print(f"open_payments: general payment years {list(years)}", flush=True)
    # Years already read and recent are kept as they are; the rest, those never
    # read first and then the oldest copies, are read while the time lasts.
    def kept(year, ds):
        f = OUT / "years" / f"{year}.json"
        rec = (old.get("years") or {}).get(str(year)) or {}
        if not f.exists() or (rec.get("dataset") and rec["dataset"] != ds):
            return None
        when = rec.get("read_on")
        if when and (today - datetime.date.fromisoformat(when)).days > STALE_DAYS:
            return None
        return rec or {"dataset": ds, "read_on": None, "note": "read by an earlier run that stopped before writing its record"}
    todo = []
    for year, ds in years.items():
        rec = kept(year, ds)
        if rec:
            status["years"][str(year)] = rec
        else:
            todo.append((year, ds))
    todo.sort(key=lambda yd: ((OUT / "years" / f"{yd[0]}.json").exists(), yd[0]))
    for year, ds in todo:
        if time.time() - START > BUDGET:
            status["waiting"].append(year)
            if (OUT / "years" / f"{year}.json").exists():
                status["years"][str(year)] = (old.get("years") or {}).get(str(year)) or {"dataset": ds, "read_on": None}
            continue
        try:
            rows = totals(ds)
        except Exception as e:  # noqa: BLE001
            status["refused"][year] = str(e)[:300]
            print(f"::warning::open_payments {year}: {e}", flush=True)
            if (OUT / "years" / f"{year}.json").exists():
                status["years"][str(year)] = (old.get("years") or {}).get(str(year)) or {"dataset": ds, "read_on": None}
            continue
        by = {}
        for r in rows:
            st = str(r.get(STATE) or "").strip().upper() or "(no state)"
            try:
                paid = float(r.get("paid") or 0)
            except ValueError:
                paid = 0.0
            by.setdefault(st, []).append({"company": str(r.get(CO) or "").strip(), "paid": round(paid, 2), "payments": int(float(r.get("payments") or 0))})
        for st in by:
            by[st].sort(key=lambda x: -x["paid"])
        (OUT / "years" / f"{year}.json").write_text(json.dumps(by, ensure_ascii=False))
        status["years"][str(year)] = {"dataset": ds, "read_on": today.isoformat(), "rows": len(rows), "states": len(by),
                                      "total_paid": round(sum(x["paid"] for v in by.values() for x in v))}
        print(f"  {year}: {len(rows):,} state-company sums", flush=True)
        stamp.write_text(json.dumps(status, indent=1, ensure_ascii=False))   # kept even if the run is stopped
    if status["waiting"]:
        print(f"::warning::open_payments: time budget spent; still to read {status['waiting']} (next run)", flush=True)
    status["years"] = dict(sorted(status["years"].items()))
    feats, no_shape = [], set()
    for year in status["years"]:
        by = json.loads((OUT / "years" / f"{year}.json").read_text())
        for st, cos in by.items():
            name = NAMES.get(st)
            geom = shapes.get(name) if name else None
            if not geom:
                no_shape.add(st)
                continue
            total = sum(c["paid"] for c in cos)
            top = "; ".join(f"{c['company']}: {fmt(c['paid'])}" for c in cos[:50])
            feats.append({"type": "Feature", "geometry": geom, "properties": {
                "name": f"{name}, {year}", "state": name, "year": int(year), "paid (US$)": round(total),
                "payments": sum(c["payments"] for c in cos), "companies paying": len(cos),
                "largest payers (top 50)": top, "every company": f"{PAGES_PUBLIC}{year}.json",
                "what this counts": "General payments (meals, travel, speaking and consulting fees, gifts and the like) to doctors and other prescribers practising in this state, as companies reported them to CMS. Research payments and ownership interests are not included."}})
    (OUT / "states.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    status["features"] = len(feats)
    status["states_without_a_shape"] = sorted(no_shape)
    if not status["years"] and old.get("years"):
        print("::warning::open_payments: CMS refused every year; the last copy stays")
        return
    stamp.write_text(json.dumps(status, indent=1, ensure_ascii=False))
    print(f"open_payments: {len(feats)} state-years from {len(status['years'])} years; refused {list(status['refused'])}")


if __name__ == "__main__":
    main()
