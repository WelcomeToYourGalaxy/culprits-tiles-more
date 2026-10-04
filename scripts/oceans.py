#!/usr/bin/env python3
"""
Oceans, for the Culprits map (round 94b, asked 27 September: other subjects
worth adding to Oceans, from the best worldwide data).

  oceans/dead_zones.geojson    WRI's eutrophic and hypoxic coastal areas (Diaz,
                               Selman and Chique 2011; the 762 systems of WRI's
                               "Eutrophication and Hypoxia" map), from Resource
                               Watch's table wat_041_eutrophication_hypoxia;
                               group = its classification (hypoxic, eutrophic,
                               improved)
  oceans/seabed_mining.geojson The International Seabed Authority's
                               exploration contract areas for polymetallic
                               nodules, polymetallic sulphides and cobalt-rich
                               crusts, the areas reserved for the Authority,
                               and its Areas of Particular Environmental
                               Interest (closed to mining), from the shapefiles
                               on isa.org.jm/exploration-contracts/maps/;
                               group = which of these
  oceans/build.json            what each read

Weekly (Mondays), or by hand.
"""
import datetime, io, json, os, pathlib, sys, tempfile, urllib.request, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
OUT = pathlib.Path("oceans")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
DEAD = "https://wri-rw.carto.com/api/v2/sql?q=SELECT%20*%20FROM%20wat_041_eutrophication_hypoxia&format=geojson"
ISA = [("Exploration contract: polymetallic nodules", "https://www.isa.org.jm/wp-content/uploads/2024/10/ISAwebsite_fclContractAreasPMN.zip"),
       ("Exploration contract: polymetallic sulphides", "https://www.isa.org.jm/wp-content/uploads/2024/10/ISAwebsite_fclContractAreasPMS.zip"),
       ("Exploration contract: cobalt-rich crusts", "https://isa.org.jm/wp-content/uploads/2026/03/ISAwebsite_fclContractAreasCRFC.zip"),
       ("Reserved for the Authority: nodules", "https://www.isa.org.jm/wp-content/uploads/2024/10/ISAwebsite_fclContractAreasPMNres.zip"),
       ("Reserved for the Authority: crusts", "https://www.isa.org.jm/wp-content/uploads/2024/10/ISAwebsite_fclContractAreasCRFCres.zip"),
       ("Protected from mining (Areas of Particular Environmental Interest)", "https://www.isa.org.jm/wp-content/uploads/2024/10/ISAwebsite_APEIs.zip")]


def get(url, timeout=300):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def main():
    stamp_p = OUT / "build.json"
    if stamp_p.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("oceans: weekly; not Monday")
        return
    OUT.mkdir(exist_ok=True)
    stamp = json.loads(stamp_p.read_text()) if stamp_p.exists() else {}
    try:
        gj = json.loads(get(DEAD))
        for f in gj.get("features", []):
            p = f.get("properties") or {}
            p["group"] = p.get("classification") or "not classified"
            p["name"] = p.get("system") or ""
        (OUT / "dead_zones.geojson").write_text(json.dumps(gj, ensure_ascii=False))
        stamp["dead_zones"] = {"from": DEAD, "features": len(gj.get("features", [])), "read": datetime.date.today().isoformat()}
    except Exception as e:  # noqa: BLE001
        stamp["dead_zones"] = {"error": f"{type(e).__name__}: {e}"}
    try:
        import mines
        mines.tools()
        work = pathlib.Path(tempfile.mkdtemp())
        feats, read = [], {}
        for group, url in ISA:
            try:
                z = zipfile.ZipFile(io.BytesIO(get(url)))
                d = work / str(len(read))
                z.extractall(d)
                shp = next(d.rglob("*.shp"))
                out = d / "out.geojson"
                mines.sh("ogr2ogr", "-f", "GeoJSON", "-t_srs", "EPSG:4326", "-lco", "RFC7946=YES", str(out), str(shp))
                got = json.loads(out.read_text()).get("features", [])
                for f in got:
                    p = f.get("properties") or {}
                    p["group"] = group
                    p["name"] = p.get("Contractor") or p.get("CONTRACTOR") or p.get("Name") or p.get("NAME") or group
                    feats.append(f)
                read[group] = len(got)
            except Exception as e:  # noqa: BLE001
                read[group] = f"did not answer ({type(e).__name__}: {e})"
        if feats:
            (OUT / "seabed_mining.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
        stamp["seabed_mining"] = {"read": read, "features": len(feats), "on": datetime.date.today().isoformat()}
    except Exception as e:  # noqa: BLE001
        stamp["seabed_mining"] = {"error": f"{type(e).__name__}: {e}"}
    stamp_p.write_text(json.dumps(stamp, indent=1, default=str))
    print(json.dumps(stamp, indent=1, default=str))


if __name__ == "__main__":
    main()
