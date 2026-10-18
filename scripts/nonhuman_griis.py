#!/usr/bin/env python3
"""
Introduced and invasive species, country by country, for the Invasion of
non-humans map (nonhuman row in the Culprits map, maps repo
invasion-of-nonhumans.html).

Source: the Global Register of Introduced and Invasive Species (GRIIS), one
checklist per country, published on GBIF by the IUCN SSC Invasive Species
Specialist Group (publisher cdef28b1-db4e-4c58-aa71-3c5238c2d0b5), CC BY 4.0.
Pagad, S. et al. 2018, Scientific Data 5: 170202.

Each checklist's Darwin Core Archive is read whole: every taxon in it, with
the checklist's own invasiveness mark (species profile isInvasive) and its
establishment means. Counts per checklist; every species in a file per
checklist. Checklists whose place has no country shape on the map are kept
and listed as unplaced.

  nonhuman/griis.json            the counts, per country and unplaced
  nonhuman/griis/<code>.json     every species of one checklist
  nonhuman/griis.build.json      what was read, and any checklist that failed

Weekly (GRIIS checklists are updated now and then); GRIIS_REBUILD=1 or a run
by hand builds at once.
"""
import collections, csv, io, json, pathlib, re, sys, tempfile, xml.etree.ElementTree as ET, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402

NAME = "griis"
API = "https://api.gbif.org/v1"
ISSG = "cdef28b1-db4e-4c58-aa71-3c5238c2d0b5"
TITLE = "global register of introduced and invasive species"
YES = re.compile(r"^\s*(invasive|yes|true|y|1)\s*$", re.I)


def datasets():
    found = {}
    off = 0
    while True:
        j = nh.get_json(f"{API}/dataset/search?publishingOrg={ISSG}&type=CHECKLIST&limit=200&offset={off}")
        for d in j.get("results", []):
            found[d["key"]] = d
        off += 200
        if j.get("endOfRecords", True) or off > 5000:
            break
    # GRIIS checklists published by anyone else, found by title.
    off = 0
    while True:
        j = nh.get_json(f"{API}/dataset/search?q=%22Global%20Register%20of%20Introduced%20and%20Invasive%20Species%22&type=CHECKLIST&limit=200&offset={off}")
        for d in j.get("results", []):
            found.setdefault(d["key"], d)
        off += 200
        if j.get("endOfRecords", True) or off > 5000:
            break
    return [d for d in found.values() if (d.get("title") or "").lower().startswith(TITLE)]


def place_of(title):
    t = re.sub(r"^\s*global register of introduced and invasive species\s*[-–—:,]?\s*", "", title, flags=re.I)
    return t.strip() or title


def term(s):
    return re.split(r"[/#]", s or "")[-1]


def read_archive(path):
    z = zipfile.ZipFile(path)
    meta = ET.fromstring(z.read("meta.xml"))
    uri = meta.tag.split("}")[0] + "}" if meta.tag.startswith("{") else ""
    q = lambda t: uri + t

    def spec(el):
        files = el.find(q("files"))
        loc = files.find(q("location")).text.strip()
        fields = {term(f.get("term")): int(f.get("index")) for f in el.findall(q("field")) if f.get("index") is not None}
        idx = el.find(q("id")) if el.find(q("id")) is not None else el.find(q("coreid"))
        return {"file": loc, "fields": fields, "id": int(idx.get("index")) if idx is not None else 0,
                "sep": (el.get("fieldsTerminatedBy") or "\\t").encode().decode("unicode_escape"),
                "skip": int(el.get("ignoreHeaderLines") or 0), "enc": el.get("encoding") or "utf-8",
                "quote": (el.get("fieldsEnclosedBy") or "").encode().decode("unicode_escape"), "row": term(el.get("rowType"))}

    core = spec(meta.find(q("core")))
    exts = [spec(e) for e in meta.findall(q("extension"))]

    def rows(s):
        raw = z.read(s["file"]).decode(s["enc"], errors="replace")
        rd = csv.reader(io.StringIO(raw), delimiter=s["sep"], quotechar=s["quote"] or '"',
                        quoting=csv.QUOTE_MINIMAL if s["quote"] else csv.QUOTE_NONE)
        for i, r in enumerate(rd):
            if i < s["skip"]:
                continue
            yield r

    def val(r, s, name):
        i = s["fields"].get(name)
        return r[i].strip() if i is not None and i < len(r) else ""

    taxa = {}
    for r in rows(core):
        if not r:
            continue
        tid = r[core["id"]] if core["id"] < len(r) else ""
        taxa[tid] = {"n": val(r, core, "scientificName") or val(r, core, "acceptedNameUsage"), "k": val(r, core, "kingdom"),
                     "inv_raw": "", "h": val(r, core, "habitat"), "em": val(r, core, "establishmentMeans"), "os": val(r, core, "occurrenceStatus")}
    for s in exts:
        for r in rows(s):
            if not r:
                continue
            tid = r[s["id"]] if s["id"] < len(r) else ""
            t = taxa.get(tid)
            if t is None:
                continue
            for name, key in (("isInvasive", "inv_raw"), ("habitat", "h"), ("establishmentMeans", "em"), ("occurrenceStatus", "os")):
                v = val(r, s, name)
                if v and not t[key]:
                    t[key] = v
    return taxa, {"core": core["row"], "extensions": [e["row"] for e in exts], "columns": sorted(set(core["fields"]) | set().union(*[set(e["fields"]) for e in exts]))}


def main():
    csv.field_size_limit(sys.maxsize)
    if not nh.due(NAME, 7, "GRIIS_REBUILD"):
        return
    C = nh.Countries()
    work = pathlib.Path(tempfile.mkdtemp())
    out, unplaced, failed, columns = {}, [], [], collections.Counter()
    lists = datasets()
    print(f"griis: {len(lists)} checklists", flush=True)
    for d in sorted(lists, key=lambda x: x.get("title") or ""):
        key, title = d["key"], d.get("title") or ""
        try:
            full = nh.get_json(f"{API}/dataset/{key}")
            ep = next((e["url"] for e in full.get("endpoints", []) if e.get("type") == "DWC_ARCHIVE"), None)
            if not ep:
                raise RuntimeError("no Darwin Core Archive endpoint")
            path = nh.download(ep, work / f"{key}.zip", title[:60])
            taxa, how = read_archive(path)
            for c in how["columns"]:
                columns[c] += 1
        except Exception as e:
            failed.append({"title": title, "datasetKey": key, "error": str(e)[:300]})
            print(f"  {title}: {e}", flush=True)
            continue
        place = place_of(title)
        # Matched by the place its title names only: a checklist for an island
        # or a region is never folded into its country.
        iso = C.by_name(place)
        species, raw = [], collections.Counter()
        inv = notinv = unk = 0
        means = collections.Counter()
        for t in taxa.values():
            raw[t["inv_raw"] or "(blank)"] += 1
            means[t["em"] or "(not given)"] += 1
            if not t["inv_raw"]:
                flag = None
                unk += 1
            elif YES.match(t["inv_raw"]):
                flag = True
                inv += 1
            else:
                flag = False
                notinv += 1
            species.append({k: v for k, v in {"n": t["n"], "k": t["k"], "inv": flag, "h": t["h"], "em": t["em"]}.items() if v not in ("", None) or k == "inv"})
        species.sort(key=lambda s: s.get("n") or "")
        code = iso or "x_" + nh.slug(place)
        rel = f"griis/{code}.json"
        nh.write_json(rel, {"title": title, "datasetKey": key, "species": species})
        rec = {"name": place, "title": title, "datasetKey": key, "introduced": len(taxa), "invasive": inv, "notInvasive": notinv,
               "unknown": unk, "means": dict(means), "isInvasiveAsWritten": dict(raw), "file": rel}
        if iso and iso not in out:
            out[iso] = rec
        elif iso:
            # A second checklist for the same country (a part of it) is kept, not added in.
            unplaced.append(dict(rec, note=f"a second checklist matched to {iso}; kept separate"))
        else:
            unplaced.append(rec)
        print(f"  {title}: {len(taxa)} taxa, {inv} invasive -> {iso or 'unplaced'}", flush=True)
    if not out:
        nh.write_stamp(NAME, {"failed": True, "checklists": len(lists), "errors": failed})
        raise SystemExit("griis: nothing read")
    nh.write_json("griis.json", {"source": "GRIIS country checklists on GBIF (IUCN SSC ISSG), CC BY 4.0", "countries": out, "unplaced": unplaced,
                                 "made": nh.datetime.datetime.utcnow().strftime("%Y-%m-%d")})
    nh.write_stamp(NAME, {"checklists": len(lists), "countries": len(out), "unplaced": len(unplaced), "failed_checklists": failed,
                          "columns seen (in how many checklists)": dict(columns)})


if __name__ == "__main__":
    main()
