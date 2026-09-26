#!/usr/bin/env python3
"""
Climate TRACE by gas: tiles/climate_trace_<gas>_<subsector>.pmtiles, one archive
per gas and subsector, and tiles/climate_trace_gases.json describing them.

The map's Climate TRACE archives carry each site's CO2-equivalent total. Climate
TRACE also publishes, per site and period, the tonnes of each gas on its own:
sector packages at latest/sector_packages/<gas>/<sector>.zip for co2, ch4 and
n2o. This runs the culprits harvest (pipeline/sources/climate_trace.py) once per
gas with CT_GAS set, normalises the rows, and splits them by subsector with the
culprits pipeline's own split_sectors.sh under the prefix climate_trace_<gas>.
Every site and every period is kept, exactly as in the CO2e build; nothing is
filtered. The archives land here rather than in culprits because there are
three gases' worth of them.

Exact for co2, ch4 and n2o. F-gases are not in the inventory; black carbon and
NOx are in Climate TRACE's air-pollution set (scripts/ct_air.py).

Each gas and sector keeps its own ETag state (climate_gases/etags_<gas>_<sector>.json),
so a release that has not changed is skipped. Put "ct_gases" in the workflow's box;
each run builds as many gas, sector and subsector units as fit, and records each as it goes. The culprits pipeline is cloned fresh
from main each run, so its harvester and splitter are always the current ones.
"""
import json, os, pathlib, shutil, subprocess, sys, tempfile, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import mines  # noqa: E402  tools() builds tippecanoe

ALL_GASES = ["co2", "ch4", "n2o"]
SECTORS = ["agriculture", "buildings", "forestry_and_land_use", "fossil_fuel_operations",
           "manufacturing", "power", "transportation", "waste"]
# One sector of one gas at a time (24 September). Carbon dioxide alone is
# 111,949,068 rows; harvesting, normalising and splitting the whole gas ran
# past the job's 160 minutes (it was stopped while splitting) and nothing was
# kept. Each run now works through the (gas, sector) pairs never built, oldest
# first, starting a new pair only while there is time for it, and records each
# pair as it finishes. Run "ct_gases" until the log says every pair is built.
# CT_GASES / CT_SECTORS narrow it by hand ("co2", "power,waste").
GASES = [g for g in os.environ.get("CT_GASES", "").split(",") if g] or ALL_GASES
ONLY_SECTORS = [x for x in os.environ.get("CT_SECTORS", "").split(",") if x] or SECTORS
START_BEFORE_S = 60 * 60      # no new unit starts after 60 minutes
NAMES = {"co2": "carbon dioxide", "ch4": "methane", "n2o": "nitrous oxide"}
TILES = pathlib.Path("tiles")
STATE = pathlib.Path("climate_gases")
REPO = "https://github.com/WelcomeToYourGalaxy/culprits.git"


def sh(cmd, **kw):
    print("  $", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def slug(x):
    return "".join(c if c.isalnum() else "_" for c in str(x or "").lower())


SCHEMA_URL = "https://downloads.climatetrace.org/latest/about_the_data/detailed_data_schema.csv"


def subsectors():
    """{sector: [subsector, ...]} from Climate TRACE's own schema, the list the
    harvester reads its definitions from. None if it cannot be read, and each
    sector is then built whole, as before."""
    import csv, io, urllib.request
    try:
        req = urllib.request.Request(SCHEMA_URL, headers={"User-Agent": "Culprits atlas refresh"})
        text = urllib.request.urlopen(req, timeout=120).read().decode("utf-8-sig")
    except Exception as e:  # noqa: BLE001
        print(f"ct_gases: Climate TRACE's schema could not be read ({e}); each sector is built whole", file=sys.stderr)
        return None
    want = {slug(x): x for x in SECTORS}
    out = {}
    for row in list(csv.reader(io.StringIO(text)))[1:]:
        if len(row) < 2 or not row[0].strip() or not row[1].strip():
            continue
        sec = want.get(slug(row[0]))
        if sec and row[1].strip() not in out.setdefault(sec, []):
            out[sec].append(row[1].strip())
    return out or None


def build_unit(gas, sector, sub, src, work, index, index_path):
    """Harvest, normalise and tile one subsector of one sector of one gas (sub ""
    for the whole sector); True if anything was built. Its archives are copied
    into tiles/ and recorded as soon as they are made, so a run stopped later
    keeps them (24 September: agriculture's first two subsectors were tiled and
    then lost when the job hit its time limit in the third)."""
    env = dict(os.environ, CT_GAS=gas, CT_SECTORS=sector)
    if sub:
        env["CT_SUBSECTORS"] = sub
    key = f"{sector}/{slug(sub)}" if sub else sector
    g = index.setdefault(gas, {"name": NAMES.get(gas, gas), "archives": [], "units": {}})
    units = g.setdefault("units", {})
    done = units.get(key) or {}
    # The harvest's record of what it read is kept only once this unit is built:
    # a failed run must not make the next one skip the release as unchanged.
    kept = STATE / f"etags_{gas}_{slug(key)}.json"
    state = work / kept.name
    if kept.exists() and done.get("archives") is not None:
        shutil.copy(kept, state)
    raw = src / "data" / "raw" / "climate_trace.jsonl.gz"
    raw.unlink(missing_ok=True)
    sh([sys.executable, "pipeline/harvest.py", "--only", "climate_trace", "--state", str(state.resolve())], cwd=src, env=env)
    if not raw.exists():
        print(f"  {gas}/{key}: unchanged since it was built; kept", flush=True)
        done["checked"] = int(time.time())
        units[key] = done
        return False
    norm = src / "data" / "normalized" / f"climate_trace_{gas}_{slug(key)}.geojsonl.gz"
    norm.parent.mkdir(parents=True, exist_ok=True)
    sh([sys.executable, "pipeline/normalize.py", "--source", f"climate_trace_{gas}", "--in", str(raw), "--out", str(norm)], cwd=src, env=env)
    raw.unlink(missing_ok=True)
    out = work / f"tiles_{gas}_{slug(key)}"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    try:
        sh(["bash", "pipeline/split_sectors.sh", str(norm), str(out)], cwd=src,
           env=dict(env, PREFIX=f"climate_trace_{gas}", SPLIT_KEY="x_subsector"))
    except subprocess.CalledProcessError as e:
        print(f"  {gas}/{key}: some subsectors did not build ({e}); the ones that did are kept", file=sys.stderr)
    norm.unlink(missing_ok=True)
    # An archive over GitHub's cap is cut by zoom by the pipeline into
    # <id>.pmtiles, <id>_2.pmtiles... with <id>.build.json listing them; the
    # map's pmtiles route reads that list. The parts travel with their archive
    # and are not rows of their own.
    parts = set()
    for b in out.glob("*.build.json"):
        try:
            parts.update(p["file"] for p in json.loads(b.read_text()).get("parts", [])[1:])
        except Exception:  # noqa: BLE001
            pass
    made, kept_names = [], set()
    for f in sorted(out.glob("*.pmtiles")):
        if f.name in parts:
            continue
        big = [x for x in [f] + [out / n for n in parts if n.startswith(f.stem + "_")] if x.stat().st_size > 95e6]
        if big:
            print(f"  {', '.join(x.name for x in big)} over what GitHub takes; NOT copied", file=sys.stderr)
            continue
        group = [f] + [out / n for n in sorted(parts) if n.startswith(f.stem + "_")]
        for old in TILES.glob(f"{f.stem}_*.pmtiles"):
            old.unlink()
        (TILES / f"{f.stem}.build.json").unlink(missing_ok=True)
        for x in group:
            shutil.copy(x, TILES / x.name)
        bj = out / f"{f.stem}.build.json"
        if bj.exists():
            shutil.copy(bj, TILES / bj.name)
        s = f.stem[len(f"climate_trace_{gas}_"):]
        kept_names.add(f.stem)
        made.append({"id": f.stem, "subsector": s, "label": s.replace("_", " "), "sector": sector,
                     "bytes": sum(x.stat().st_size for x in group), "files": len(group)})
    shutil.rmtree(out, ignore_errors=True)
    for old in done.get("archives") or []:
        if old not in kept_names:
            (TILES / f"{old}.pmtiles").unlink(missing_ok=True)
    units[key] = {"built": int(time.time()), "archives": [m["id"] for m in made]}
    ids = {m["id"] for m in made}
    g["archives"] = sorted([a for a in g.get("archives", []) if a["id"] not in ids] + made, key=lambda a: a["id"])
    g["built"] = int(time.time())
    index_path.write_text(json.dumps(index, indent=1))
    if state.exists():
        shutil.copy(state, kept)
    print(f"  {gas}/{key}: {len(made)} archives", flush=True)
    return True


def main():
    started = time.time()
    mines.tools()
    work = pathlib.Path(tempfile.mkdtemp())
    src = work / "culprits"
    sh(["git", "clone", "-q", "--depth", "1", "--filter=blob:none", "--sparse", REPO, str(src)])
    # Cone mode takes folders only; files at the top (sources.json) are always
    # included, and naming one stopped the first run (23 September).
    sh(["git", "sparse-checkout", "set", "pipeline"], cwd=src)
    sh([sys.executable, "-m", "pip", "install", "-q", "requests"])
    STATE.mkdir(exist_ok=True)
    TILES.mkdir(exist_ok=True)
    index_path = TILES / "climate_trace_gases.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    subs = subsectors()
    units = [(g, x, sub) for g in GASES for x in ONLY_SECTORS for sub in ((subs or {}).get(x) or [""])]
    key = lambda u: f"{u[1]}/{slug(u[2])}" if u[2] else u[1]
    last = lambda u: max(((index.get(u[0]) or {}).get("units", {}).get(key(u)) or {}).get(k, 0) for k in ("built", "checked"))
    units.sort(key=lambda u: (last(u), GASES.index(u[0]), ONLY_SECTORS.index(u[1])))
    todo = [u for u in units if last(u) == 0]
    print(f"ct_gases: {len(todo)} of {len(units)} gas, sector and subsector units never built; oldest first", flush=True)
    did = 0
    for gas, sector, sub in units:
        if did and time.time() - started > START_BEFORE_S:      # the first unit always runs
            print(f"ct_gases: {int((time.time() - started) / 60)} minutes gone; the rest wait for the next run", flush=True)
            break
        print(f"== {gas} ({NAMES.get(gas, gas)}), {sector}" + (f", {sub}" if sub else ""), flush=True)
        build_unit(gas, sector, sub, src, work, index, index_path)
        index_path.write_text(json.dumps(index, indent=1))
        did += 1
    left = sum(1 for u in units if last(u) == 0)
    print(f"ct_gases: {did} units looked at this run; {left} never built" + ("" if left else "; every unit is built"), flush=True)


if __name__ == "__main__":
    main()
