#!/usr/bin/env python3
"""
Fish and other sea animals caught and farmed, country by country (round
139b, asked 2 October: the layers that make the marine meat picture complete).
FAO FishStat's global production files (CC BY-NC-SA 3.0 IGO), from
https://www.fao.org/fishery/static/Data/ (the newest Capture_*.zip and
Aquaculture_*.zip in its listing):

  fish/fao_capture.json      ISO3 -> {value: tonnes caught in the latest year
                             (live weight), that year, ten years before and
                             the change, sea and inland, by kind of animal
                             (FAO's ISSCAAP groups), the top 15 species, and
                             any animals FAO counts by head (whales, seals...)}
  fish/fao_aquaculture.json  the same for farming, by water (fresh, brackish,
                             sea)
  fish/fao_sharks.json       round 185o: sharks, rays and chimaeras caught (the
                             FAO group of that name), each country: tonnes in
                             the latest year and ten years before, every
                             species in the group, by sea area
  fish/fao_build.json        files read, the latest year, and the reporting
                             countries that are not one country (e.g. "Other
                             nei"), with their totals

Every record is counted; nothing is left out. Weekly (Sundays), or by hand.
"""
import csv, datetime, io, json, os, pathlib, re, urllib.request, zipfile

BASE = "https://www.fao.org/fishery/static/Data/"
OUT = pathlib.Path("fish")
UA = {"User-Agent": "Culprits atlas build (welcometoyourgalaxy@gmail.com)"}


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=600).read()


def newest(kind, listing):
    names = sorted(set(re.findall(rf'href="({kind}_(\d{{4}})\.(\d+)\.(\d+)\.zip)"', listing)), key=lambda m: tuple(int(x) for x in m[1:]))
    if not names:
        raise SystemExit(f"fao_fisheries: no {kind}_*.zip in {BASE}")
    return names[-1][0]


def table(z, name):
    n = next((x for x in z.namelist() if x.rsplit("/", 1)[-1].lower() == name.lower()), None)
    if not n:
        return []
    return list(csv.DictReader(io.TextIOWrapper(z.open(n), encoding="utf-8-sig", errors="replace")))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build(kind, z, stamp):
    data = table(z, f"{kind}_Quantity.csv")
    countries = {r["UN_Code"]: r for r in table(z, "CL_FI_COUNTRY_GROUPS.csv")}
    species = {(r.get("3A_Code") or r.get("X3A_Code")): r for r in table(z, "CL_FI_SPECIES_GROUPS.csv")}
    areas = {r["Code"]: r for r in table(z, "CL_FI_WATERAREA_GROUPS.csv")}
    envs = {r["Code"]: r.get("Name_En") for r in table(z, "CL_FI_PRODENVIRONMENT.csv")}
    years = sorted({int(r["PERIOD"]) for r in data if r.get("PERIOD", "").isdigit()})
    last = years[-1]
    before = last - 10
    out, odd = {}, {}
    for r in data:
        y = int(r["PERIOD"]) if r.get("PERIOD", "").isdigit() else None
        v = num(r.get("VALUE"))
        if y not in (last, before) or v is None:
            continue
        c = countries.get(r.get("COUNTRY.UN_CODE"), {})
        iso = c.get("ISO3_Code") or ""
        name = c.get("Name_En") or r.get("COUNTRY.UN_CODE")
        rec = out.setdefault(iso, {"name": name, "t": {}, "t0": 0.0, "groups": {}, "species": {}, "water": {}, "heads": {}}) if re.fullmatch(r"[A-Z]{3}", iso) \
            else odd.setdefault(name, {"t": 0.0})
        tonnes = r.get("MEASURE") == "Q_tlw"
        if not re.fullmatch(r"[A-Z]{3}", iso):
            if tonnes and y == last:
                rec["t"] += v
            continue
        sp = species.get(r.get("SPECIES.ALPHA_3_CODE"), {})
        spname = sp.get("Name_En") or r.get("SPECIES.ALPHA_3_CODE")
        if not tonnes:
            if y == last:
                rec["heads"][spname] = rec["heads"].get(spname, 0) + v
            continue
        if y == before:
            rec["t0"] += v
            continue
        rec["t"]["all"] = rec["t"].get("all", 0) + v
        g = sp.get("ISSCAAP_Group_En") or "not grouped"
        rec["groups"][g] = rec["groups"].get(g, 0) + v
        rec["species"][spname] = rec["species"].get(spname, 0) + v
        if kind == "Capture":
            w = (areas.get(r.get("AREA.CODE"), {}).get("InlandMarine_Group_En") or "not given")
        else:
            w = envs.get(r.get("ENVIRONMENT.ALPHA_2_CODE")) or r.get("ENVIRONMENT.ALPHA_2_CODE") or "not given"
        rec["water"][w] = rec["water"].get(w, 0) + v
    res = {}
    fmt = lambda d: "; ".join(f"{k}: {v:,.0f} t" for k, v in sorted(d.items(), key=lambda kv: -kv[1]))
    for iso, rec in out.items():
        t = rec["t"].get("all", 0.0)
        if t <= 0 and not rec["heads"]:
            continue
        e = {"value": round(t), "x_country as FAO names it": rec["name"], "x_year": last, f"x_tonnes in {before}": round(rec["t0"]),
             "x_change over ten years (%)": round(100 * (t - rec["t0"]) / rec["t0"], 1) if rec["t0"] > 0 else None,
             "x_by water": fmt(rec["water"]), "x_by kind of animal (FAO's groups)": fmt(rec["groups"]),
             "x_top 15 species": fmt(dict(sorted(rec["species"].items(), key=lambda kv: -kv[1])[:15])),
             "x_species recorded": len(rec["species"])}
        if rec["heads"]:
            e["x_animals FAO counts by head, not weight"] = "; ".join(f"{k}: {v:,.0f}" for k, v in sorted(rec["heads"].items(), key=lambda kv: -kv[1]))
        res[iso] = e
    stamp[kind] = {"latest_year": last, "countries": len(res), "not_one_country": {k: round(v["t"]) for k, v in odd.items()}}
    return res


def sharks(z, stamp):
    """Round 185o: the catch of FAO's ISSCAAP group "Sharks, rays, chimaeras",
    the group chosen by its own name in FAO's species list, nothing else."""
    data = table(z, "Capture_Quantity.csv")
    countries = {r["UN_Code"]: r for r in table(z, "CL_FI_COUNTRY_GROUPS.csv")}
    species = {(r.get("3A_Code") or r.get("X3A_Code")): r for r in table(z, "CL_FI_SPECIES_GROUPS.csv")}
    areas = {r["Code"]: r for r in table(z, "CL_FI_WATERAREA_GROUPS.csv")}
    groups = sorted({r.get("ISSCAAP_Group_En") for r in species.values() if r.get("ISSCAAP_Group_En") and re.search(r"shark", r["ISSCAAP_Group_En"], re.I)})
    if not groups:
        stamp["sharks"] = {"built": False, "why": "no FAO group with sharks in its name"}
        return {}
    codes = {k for k, r in species.items() if r.get("ISSCAAP_Group_En") in groups}
    years = sorted({int(r["PERIOD"]) for r in data if r.get("PERIOD", "").isdigit()})
    last, before = years[-1], years[-1] - 10
    out, odd = {}, {}
    for r in data:
        if r.get("SPECIES.ALPHA_3_CODE") not in codes or r.get("MEASURE") != "Q_tlw":
            continue
        y = int(r["PERIOD"]) if r.get("PERIOD", "").isdigit() else None
        v = num(r.get("VALUE"))
        if y not in (last, before) or v is None:
            continue
        c = countries.get(r.get("COUNTRY.UN_CODE"), {})
        iso = c.get("ISO3_Code") or ""
        name = c.get("Name_En") or r.get("COUNTRY.UN_CODE")
        if not re.fullmatch(r"[A-Z]{3}", iso):
            if y == last:
                odd[name] = odd.get(name, 0) + v
            continue
        rec = out.setdefault(iso, {"name": name, "t": 0.0, "t0": 0.0, "species": {}, "areas": {}})
        if y == before:
            rec["t0"] += v
            continue
        rec["t"] += v
        sp = species.get(r.get("SPECIES.ALPHA_3_CODE"), {})
        spn = sp.get("Name_En") or r.get("SPECIES.ALPHA_3_CODE")
        if sp.get("Scientific_Name"):
            spn = f"{spn} ({sp['Scientific_Name']})"
        rec["species"][spn] = rec["species"].get(spn, 0) + v
        a = areas.get(r.get("AREA.CODE"), {}).get("Name_En") or r.get("AREA.CODE") or "not given"
        rec["areas"][a] = rec["areas"].get(a, 0) + v
    fmt = lambda d: "; ".join(f"{k}: {v:,.0f} t" for k, v in sorted(d.items(), key=lambda kv: -kv[1]))
    res = {}
    for iso, rec in out.items():
        if rec["t"] <= 0 and rec["t0"] <= 0:
            continue
        res[iso] = {"value": round(rec["t"]), "x_country as FAO names it": rec["name"], "x_year": last,
                    f"x_tonnes in {before}": round(rec["t0"]),
                    "x_change over ten years (%)": round(100 * (rec["t"] - rec["t0"]) / rec["t0"], 1) if rec["t0"] > 0 else None,
                    "x_every species in the group": fmt(rec["species"]), "x_by fishing area": fmt(rec["areas"]),
                    "x_species recorded": len(rec["species"])}
    stamp["sharks"] = {"groups": groups, "latest_year": last, "countries": len(res),
                       "world_total_tonnes": round(sum(v["value"] for v in res.values())),
                       "not_one_country": {k: round(v) for k, v in odd.items()}}
    return res


def main():
    if (OUT / "fao_capture.json").exists() and (OUT / "fao_sharks.json").exists() and datetime.date.today().weekday() != 6 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("fao_fisheries: weekly; not Sunday")
        return
    listing = get(BASE).decode("utf-8", "ignore")
    OUT.mkdir(exist_ok=True)
    stamp = {"read": datetime.date.today().isoformat()}
    for kind, file in (("Capture", "fao_capture.json"), ("Aquaculture", "fao_aquaculture.json")):
        name = newest(kind, listing)
        z = zipfile.ZipFile(io.BytesIO(get(BASE + name)))
        stamp[f"{kind}_file"] = name
        res = build(kind, z, stamp)
        (OUT / file).write_text(json.dumps(res, ensure_ascii=False, indent=1))
        if kind == "Capture":
            sh = sharks(z, stamp)
            (OUT / "fao_sharks.json").write_text(json.dumps(sh, ensure_ascii=False, indent=1))
            print(f"fao_fisheries: sharks, rays and chimaeras: {len(sh)} countries", flush=True)
        print(f"fao_fisheries: {name}: {len(res)} countries, latest year {stamp[kind]['latest_year']}", flush=True)
    (OUT / "fao_build.json").write_text(json.dumps(stamp, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
