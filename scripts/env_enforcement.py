#!/usr/bin/env python3
"""
Environmental crimes punished by governments, as their own registers publish
them (round 84b, asked 27 September: "Brazil's environment agency, IBAMA, and
any others like it for regions and countries worldwide ... only environmental
crime related").

No worldwide register of environmental offences exists; each country keeps its
own, where it keeps one at all. This copies the ones that publish places:

  Brazil, IBAMA (open licence): every embargo (an area IBAMA has shut down
  for an environmental offence: illegal clearing, burning, mining, fishing)
  and every infraction notice (auto de infração), each at the coordinates
  IBAMA records for it.
    tiles/ibama_embargos.pmtiles, tiles/ibama_infractions.pmtiles
      layer = the file name; each point its id, date and kind
    enforcement/ibama_embargos/<hh>.json.gz, enforcement/ibama_infractions/...
      every field of every record, 256 pieces, found by id (FNV-1a, as the map)
    enforcement/status.json   counts, files read, what was left and why

Other countries' registers are read and their first rows saved to
probe/enforcement/ (Canada's Environmental Offenders Registry, England's
Environment Agency prosecutions and enforcement actions, the US EPA's criminal
enforcement cases, Peru's OEFA register of sanctioned offenders), so the next
round can map them from what they really hold.

Weekly (or ENFORCEMENT_REBUILD=1).
"""
import csv, gzip, io, json, os, pathlib, re, subprocess, sys, tempfile, time, urllib.parse, urllib.request, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
csv.field_size_limit(1 << 30)
OUT = pathlib.Path("enforcement")
TILES = pathlib.Path("tiles")
PROBE = pathlib.Path("probe/enforcement")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas; welcometoyourgalaxy@gmail.com)"}
CKAN = "https://dadosabertos.ibama.gov.br/api/3/action/package_show?id="
WEEK = 7 * 24 * 3600


def get(url, timeout=900):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == 2:
                raise
            print(f"    {url[:110]}: {e}; again", flush=True)
            time.sleep(20 * (i + 1))


def piece_of(key):
    h = 0x811C9DC5
    for b in str(key).encode():
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return f"{h % 256:02x}"


def table(raw):
    """Rows of a CSV (any separator, UTF-8 or Latin-1), a JSON list, or a zip holding one."""
    if raw[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(raw))
        name = sorted((n for n in z.namelist() if re.search(r"\.(csv|json)$", n, re.I)), key=lambda n: -z.getinfo(n).file_size)[0]
        raw = z.read(name)
    head = raw[:4].lstrip()
    if head[:1] in (b"[", b"{"):
        j = json.loads(raw.decode("utf-8-sig", "replace"))
        if isinstance(j, dict):
            j = next((v for v in j.values() if isinstance(v, list)), [])
        return j
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    first = text.split("\n", 1)[0]
    sep = max([";", ",", "\t", "|"], key=first.count)
    return list(csv.DictReader(io.StringIO(text), delimiter=sep))


def num(v):
    try:
        return float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def latlon(row):
    lat = lon = None
    for k, v in row.items():
        kl = str(k).lower()
        if lat is None and re.search(r"lat", kl) and not re.search(r"grau|min|seg", kl):
            lat = num(v)
        if lon is None and re.search(r"lon", kl) and not re.search(r"grau|min|seg", kl):
            lon = num(v)
    if lat is None or lon is None or not (-35 <= lat <= 7 and -75 <= lon <= -28):   # inside Brazil's box
        return None
    return lon, lat


def wkt_point(w):
    nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", str(w or ""))]
    if len(nums) < 2:
        return None
    xs, ys = nums[0::2], nums[1::2]
    lon, lat = sum(xs) / len(xs), sum(ys) / len(ys)
    return (lon, lat) if (-35 <= lat <= 7 and -75 <= lon <= -28) else None


def resources(pkg):
    try:
        j = json.loads(get(CKAN + urllib.parse.quote(pkg), 120))
    except Exception as e:  # noqa: BLE001
        print(f"    {pkg}: IBAMA's catalogue did not answer ({e}); known addresses tried", flush=True)
        return []
    res = (j.get("result") or {}).get("resources") or []
    for r in res:
        print(f"    {pkg}: {r.get('name')} -> {r.get('url')}", flush=True)
    return res


def pick(res, want, avoid=None, fmt=("CSV", "ZIP", "JSON")):
    for f in fmt:
        for r in res:
            n = f"{r.get('name', '')} {r.get('url', '')}".lower()
            if re.search(want, n, re.I) and not (avoid and re.search(avoid, n, re.I)) and (r.get("format") or "").upper() == f:
                return r["url"]
    return None


def write_layer(name, feats, pieces_of):
    import mines  # noqa: E402  sh() and tools()
    mines.tools()
    OUT.mkdir(exist_ok=True)
    base = OUT / name
    base.mkdir(exist_ok=True)
    buckets = {}
    for key, props in pieces_of.items():
        buckets.setdefault(piece_of(key), {})[str(key)] = {"properties": props}
    for hh, d in buckets.items():
        (base / f"{hh}.json.gz").write_bytes(gzip.compress(json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode()))
    work = pathlib.Path(tempfile.mkdtemp())
    lines = work / f"{name}.geojsonl"
    with open(lines, "w", encoding="utf-8") as fo:
        for f in feats:
            fo.write(json.dumps(f, ensure_ascii=False, separators=(",", ":")) + "\n")
    out = work / f"{name}.pmtiles"
    # Round 123b: the infraction notices failed here (exit 110, 28 September).
    # A second try lets tippecanoe thin the busiest squares wide out (every
    # notice still shows close in) and prints its own complaint to the log.
    try:
        mines.sh("tippecanoe", "-o", str(out), "--force", "-q", "-l", name, "-Z0", "-z12", "-r1",
                 "--no-feature-limit", "--no-tile-size-limit", str(lines))
    except Exception as e:  # noqa: BLE001
        print(f"  {name}: tippecanoe failed ({e}); trying again, thinning only the busiest squares wide out", flush=True)
        mines.sh("tippecanoe", "-o", str(out), "--force", "-l", name, "-Z0", "-z12", "-r1",
                 "--drop-densest-as-needed", "--extend-zooms-if-still-dropping", str(lines))
    if out.stat().st_size > 95 * 1024 * 1024:
        raise RuntimeError(f"{name}: {out.stat().st_size / 1e6:.0f} MB is over GitHub's limit")
    TILES.mkdir(exist_ok=True)
    os.replace(out, TILES / f"{name}.pmtiles")


def ibama_embargos(status):
    res = resources("fiscalizacao-termo-de-embargo")
    main = pick(res, r"termo_de_embargo\.(csv|json)|termos de embargo$", r"coorden|itens|anexo|decis|enquadr|hist")
    # Round 123b: the old blob address answers 404 (28 September); IBAMA's
    # files now sit under dadosabertos.ibama.gov.br/dados/SIFISC/.
    tried = [main] if main else []
    tried += ["https://dadosabertos.ibama.gov.br/dados/SIFISC/termo_embargo/termo_embargo/termo_embargo.csv",
              "https://dadosabertos.ibama.gov.br/dados/SIFISC/termo_embargo/termo_embargo/termo_embargo.json",
              "https://dadosabertos.ibama.gov.br/dados/SIFISC/termo_embargo/termo_embargo/termo_embargo.zip",
              "https://stibamadadosabertosprd.blob.core.windows.net/dados-abertos/dados/TERMOS/TERMO_EMBARGO/termo_de_embargo.csv"]
    rows, errs = None, []
    for u in tried:
        try:
            rows = table(get(u))
            main = u
            break
        except Exception as e:  # noqa: BLE001
            errs.append(f"{u}: {e}")
    if rows is None:
        raise RuntimeError("no embargo file answered: " + " | ".join(errs))
    print(f"  embargos: {len(rows):,} rows from {main}; columns {list(rows[0])[:40] if rows else []}", flush=True)
    idk = next((k for k in (rows[0] if rows else {}) if re.fullmatch(r"(seq_tad|num_tad|seq_termo.*|id)", str(k), re.I)), None)
    coords = {}
    cu = pick(res, r"coorden") or "https://dadosabertos.ibama.gov.br/dados/SIFISC/termo_embargo/coordenada/coordenada.json"
    if cu:
        try:
            for r in table(get(cu)):
                k = r.get(idk) if idk else None
                if k is None:
                    continue
                at = latlon(r) or wkt_point(r.get("DS_WKT") or r.get("WKT") or r.get("GEOM"))
                if at and k not in coords:
                    coords[k] = at
        except Exception as e:  # noqa: BLE001
            print(f"  embargo coordinates: {e}", flush=True)
    feats, pieces, nowhere = [], {}, 0
    for i, r in enumerate(rows):
        key = str(r.get(idk) if idk else i)
        at = latlon(r) or (coords.get(r.get(idk)) if idk else None)
        if not at:
            nowhere += 1
            continue
        date = next((str(v)[:10] for k, v in r.items() if re.search(r"^(dat|dt)_", str(k), re.I) and v), "")
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(at[0], 6), round(at[1], 6)]},
                      "properties": {"id": key, "x_date": date}})
        pieces[key] = dict({k: v for k, v in r.items() if v not in (None, "")}, title="IBAMA embargo " + key)
    write_layer("ibama_embargos", feats, pieces)
    status["ibama_embargos"] = {"rows": len(rows), "placed": len(feats), "no_position": nowhere, "from": main}


def ibama_infractions(status):
    res = resources("fiscalizacao-auto-de-infracao")
    main = pick(res, r"auto.?de.?infra", r"coorden|itens|anexo|decis|enquadr|hist|mob|amostr")
    main = main or "https://dadosabertos.ibama.gov.br/dados/SIFISC/auto_infracao/auto_infracao/auto_infracao_csv.zip"
    rows = table(get(main))
    print(f"  infractions: {len(rows):,} rows from {main}; columns {list(rows[0])[:40] if rows else []}", flush=True)
    cu = pick(res, r"coorden") or "https://stibamadadosabertosprd.blob.core.windows.net/dados-abertos/dados/SIFISC/auto_infracao/coordenada/coordenada.json"
    coords = {}
    for r in table(get(cu)):
        k = r.get("SEQ_AUTO_INFRACAO")
        if k is None or k in coords:
            continue
        at = latlon(r) or wkt_point(r.get("DS_WKT"))
        if at:
            coords[k] = at
    feats, pieces, nowhere = [], {}, 0
    for r in rows:
        key = r.get("SEQ_AUTO_INFRACAO")
        at = latlon(r) or coords.get(key)
        if key is None or not at:
            nowhere += 1
            continue
        date = str(r.get("DAT_HORA_AUTO_INFRACAO") or r.get("DT_LANCAMENTO") or "")[:10]
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(at[0], 6), round(at[1], 6)]},
                      "properties": {"id": str(key), "x_date": date, "x_kind": str(r.get("TIPO_INFRACAO") or r.get("DES_TIPO_INFRACAO") or "")[:60]}})
        pieces[str(key)] = dict({k: v for k, v in r.items() if v not in (None, "")}, title="IBAMA infraction notice " + str(r.get("NUM_AUTO_INFRACAO") or key))
    write_layer("ibama_infractions", feats, pieces)
    status["ibama_infractions"] = {"rows": len(rows), "placed": len(feats), "no_position": nowhere, "from": main, "coordinates": cu}


PROBES = {
    "canada_offenders_registry": ["https://environmental-protection.canada.ca/offenders-registry/Home/Export"],
    "england_ea_prosecutions": ["https://ckan.publishing.service.gov.uk/api/action/package_show?id=environment-agency-prosecutions",
                                "https://www.data.gov.uk/api/action/package_show?id=environment-agency-prosecutions"],
    "england_ea_enforcement": ["https://environment.data.gov.uk/public-register/downloads/enforcement-action"],
    "us_epa_echo_downloads": ["https://echo.epa.gov/tools/data-downloads"],
    "peru_oefa_sanctioned": ["https://www.datosabiertos.gob.pe/api/3/action/package_search?q=infractores%20ambientales%20sancionados"],
    # Round 85b (asked 27 September: "is that all you could find?"): more
    # countries' own registers, probed first like the others.
    "us_epa_echo_cases": ["https://echo.epa.gov/files/echodownloads/case_downloads.zip"],
    "chile_sma_sanctions": ["https://drive.google.com/embeddedfolderview?id=1q6MG4sfGxLisRuusnYKpUxmi9jgkSU4F",
                            "https://drive.google.com/embeddedfolderview?id=1O7o60LzQ-qH8xiK_-Ofqw_mZzti_gbEr"],
    "mexico_profepa": ["https://www.datos.gob.mx/api/3/action/package_search?q=profepa&rows=50",
                       "https://datos.gob.mx/busca/api/3/action/package_search?q=profepa&rows=50"],
    "colombia_sanctions": ["https://www.datos.gov.co/api/catalog/v1?q=sanciones%20ambientales&limit=50",
                           "https://www.datos.gov.co/api/catalog/v1?q=infractores%20ambientales&limit=50"],
    "ireland_epa": ["https://data.epa.ie/api/v1/"],
    "scotland_sepa_enforcement": ["https://www.sepa.org.uk/regulations/enforcement/enforcement-action-register/"],
    "australia_nsw_epa": ["https://apps.epa.nsw.gov.au/prpoeoapp/"],
    "iuu_vessel_list": ["https://www.iuu-vessels.org/Home/Search"],
}


def head_bytes(url, n):
    """The first n bytes of a file: a probe needs to see what it is, not all of it."""
    req = urllib.request.Request(url, headers=dict(UA, Range=f"bytes=0-{n - 1}"))
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read(n)


def probes(status):
    PROBE.mkdir(parents=True, exist_ok=True)
    for name, urls in PROBES.items():
        got = []
        for u in urls:
            try:
                raw = head_bytes(u, 2_000_000)
                text = "" if raw[:2] == b"PK" else raw.decode("utf-8", "replace")
                got.append({"url": u, "bytes": len(raw), "zip": raw[:2] == b"PK", "start": text[:6000],
                            "drive_files": sorted(set(re.findall(r"/file/d/([A-Za-z0-9_-]{20,})", text)))[:200],
                            "links": sorted(set(re.findall(r'https?://[^"\'<> ]+\.(?:csv|zip|xlsx|json)', raw.decode("utf-8", "replace"))))[:200]})
            except Exception as e:  # noqa: BLE001
                got.append({"url": u, "error": str(e)[:300]})
        (PROBE / f"{name}.json").write_text(json.dumps(got, indent=1, ensure_ascii=False))
        status.setdefault("probes", {})[name] = [g.get("bytes") or g.get("error") for g in got]


def main():
    OUT.mkdir(exist_ok=True)
    stamp = OUT / "status.json"
    try:
        status = json.loads(stamp.read_text())
    except Exception:  # noqa: BLE001
        status = {}
    # Round 123b: a layer that has never been built is tried every day.
    unbuilt = any(not (TILES / f"{n}.pmtiles").exists() for n in ("ibama_embargos", "ibama_infractions"))
    if time.time() - status.get("at", 0) < WEEK and not unbuilt and not os.environ.get("ENFORCEMENT_REBUILD"):
        print("enforcement: copied less than a week ago")
        return
    status.pop("errors", None)
    for name, fn in (("ibama_embargos", ibama_embargos), ("ibama_infractions", ibama_infractions), ("probes", probes)):
        print(f"enforcement: {name}", flush=True)
        try:
            fn(status)
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL {name}: {e}; the last copy stays", flush=True)
            status.setdefault("errors", {})[name] = str(e)[:300]
    status["at"] = time.time()
    status["when"] = time.strftime("%Y-%m-%d")
    stamp.write_text(json.dumps(status, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
