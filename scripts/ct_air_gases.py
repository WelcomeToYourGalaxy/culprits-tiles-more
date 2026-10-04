#!/usr/bin/env python3
"""
Each urban air-pollution source's yearly amount of every pollutant Climate TRACE
reports, copied weekly into ct_air/gases.json, so Culprits can draw one row per
pollutant with every source sized by that pollutant.

The sources are the ones in ct_air/sources.geojson (scripts/ct_air.py). Their
figures come from Climate TRACE's own asset service, the one its city pages
read, one source and one pollutant at a time:
    https://api.c10e.org/v7/app/asset/<id>?gas=<gas>&years=<year>
and the yearly amount is that answer's totals.value.

That is about 9,400 sources times eight pollutants. The script reads eight at a
time, the ones read longest ago first, stops starting new ones at 130 minutes
(the job is stopped at 160) and saves as it goes, so a run that does not finish
leaves every figure it did read, and the next run carries on from there. A
figure Climate TRACE will not give today keeps the one last copied.

Run weekly (Mondays) by refresh.yml, or by hand from the Actions tab.
"""
import concurrent.futures, json, os, pathlib, sys, time, urllib.error, urllib.request

API = "https://api.c10e.org/v7/app/asset/{id}?gas={gas}&years={year}"
YEAR = os.environ.get("CT_AIR_YEAR", "2024")
GASES = ["pm2_5", "bc", "oc", "so2", "vocs", "co", "nh3", "nox"]
SOURCES = pathlib.Path("ct_air/sources.geojson")
OUT = pathlib.Path("ct_air/gases.json")
BUDGET = float(os.environ.get("CT_AIR_BUDGET_MIN", "130")) * 60
START = time.monotonic()
UA = {"User-Agent": "Culprits atlas weekly copy", "Accept": "application/json"}


def one(sid, gas):
    """The yearly amount, None when Climate TRACE has no figure, or an Exception to keep the old one."""
    url = API.format(id=sid, gas=gas, year=YEAR)
    for i in range(2):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                t = (json.loads(r.read().decode("utf-8")) or {}).get("totals") or {}
                v = t.get("value")
                return float(v) if v is not None else None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code < 500 or i:
                return e
        except Exception as e:  # noqa: BLE001
            if i:
                return e
        time.sleep(3)
    return None


def save(store):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(store, separators=(",", ":")), encoding="utf-8")


def main():
    if time.gmtime().tm_wday != 0 and os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch") != "workflow_dispatch":
        print("ct_air_gases: not Monday; the figures are copied weekly.")
        return
    try:
        ids = [f["properties"]["id"] for f in json.loads(SOURCES.read_text(encoding="utf-8"))["features"]]
    except Exception as e:  # noqa: BLE001
        sys.exit(f"ct_air_gases: no source list to read ({e})")
    store = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    store.setdefault("values", {})
    store.setdefault("read", {})
    store["year"] = YEAR
    store["gases"] = GASES
    # The ones never read come first, then the longest ago.
    ids.sort(key=lambda i: store["read"].get(i, 0))
    done = kept = empty = 0
    stopped = False
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for at in range(0, len(ids), 6):
            if time.monotonic() - START > BUDGET:
                stopped = True
                break
            batch = ids[at:at + 6]
            jobs = {(sid, g): pool.submit(one, sid, g) for sid in batch for g in GASES}
            for sid in batch:
                row = store["values"].setdefault(sid, {})
                for g in GASES:
                    v = jobs[(sid, g)].result()
                    if isinstance(v, Exception):
                        kept += 1
                        continue
                    if v is None:
                        empty += 1
                    row[g] = v
                store["read"][sid] = int(time.time())
                done += 1
            if done % 240 < 6:
                save(store)
                print(f"ct_air_gases: {done:,} of {len(ids):,} sources read", flush=True)
    # Sources no longer in the list are dropped, so the file matches the map.
    live = set(ids)
    store["values"] = {k: v for k, v in store["values"].items() if k in live}
    store["read"] = {k: v for k, v in store["read"].items() if k in live}
    save(store)
    print(f"ct_air_gases: {done:,} of {len(ids):,} sources read this run; {empty:,} figures Climate TRACE does not give; "
          f"{kept:,} not answered today and kept from before" + ("; stopped at the time allowed, the rest next run" if stopped else ""),
          flush=True)


if __name__ == "__main__":
    main()
