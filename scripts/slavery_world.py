#!/usr/bin/env python3
"""
Enforcement against forced labour and trafficking, worldwide (round 103b,
asked 28 September: the anti-slavery map's enforcement layer is Brazil's
register of employers alone; the same for every other country, or as many as
possible).

1. UNODC's trafficking in persons data (the Global Report on Trafficking in
   Persons, UNODC's data portal): for each country and year, the victims its
   authorities detected and the people prosecuted and convicted. Every
   indicator, country and year the file gives is read; each country's latest
   year of each total is written, every other total in its record.

     slavery_world/unodc.json   ISO3 -> {detected, convicted, prosecuted, year_*, x_...}

2. US Customs and Border Protection's Withhold Release Orders and Findings:
   every company, region or fleet whose goods US customs holds or bans
   because they were made with forced labour, country by country, with the
   date, the goods, the status and its notes as CBP writes them. Each is placed
   at its country's label point (Natural Earth), which the box says.

     slavery_world/cbp_forced_labor.geojson

  slavery_world/build.json: what was read, the file's columns, what could not
  be placed.

Weekly (Mondays) or by hand.
"""
import datetime, html, io, json, os, pathlib, re, subprocess, sys, urllib.parse, urllib.request

OUT = pathlib.Path("slavery_world")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
UNODC_FILES = ["https://dataunodc.un.org/sites/dataunodc.un.org/files/data_glotip.xlsx",
               "https://data.unodc.org/sites/data.unodc.org/files/data_glotip.xlsx"]
UNODC_PAGES = ["https://dataunodc.un.org/dp-trafficking-persons", "https://data.unodc.org/dp-trafficking-persons",
               "https://www.unodc.org/unodc/en/data-and-analysis/glotip.html"]
CBP = "https://www.cbp.gov/trade/forced-labor/withhold-release-orders-and-findings"
NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"


def get(url, timeout=300):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def countries():
    names, labels = {}, {}
    for f in json.loads(get(NE))["features"]:
        p = f["properties"]
        iso = p.get("ADM0_A3") if p.get("ISO_A3") in (None, "-99") else p["ISO_A3"]
        for k in ("NAME", "NAME_LONG", "ADMIN", "FORMAL_EN", "NAME_SORT"):
            if p.get(k):
                names[str(p[k]).lower()] = iso
        if p.get("LABEL_X") is not None:
            labels[iso] = (p["LABEL_X"], p["LABEL_Y"])
    names.update({"democratic republic of the congo": "COD", "dominican republic": "DOM", "turkmenistan": "TKM"})
    return names, labels


def unodc(status):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "openpyxl"], check=False)
    import openpyxl
    urls = list(UNODC_FILES)
    for page in UNODC_PAGES:
        try:
            body = get(page, 120).decode("utf-8", "replace")
            urls += [urllib.parse.urljoin(page, h) for h in re.findall(r'href="([^"]+\.xlsx?)"', body, re.I)]
        except Exception as e:  # noqa: BLE001
            status.setdefault("pages", {})[page] = str(e)
    wb = None
    for u in dict.fromkeys(urls):
        try:
            wb = openpyxl.load_workbook(io.BytesIO(get(u)), read_only=True, data_only=True)
            status["unodc_file"] = u
            break
        except Exception as e:  # noqa: BLE001
            status.setdefault("tried", {})[u] = str(e)
    if not wb:
        raise RuntimeError("no UNODC trafficking file could be read")
    ws = wb.worksheets[0]
    rows = [[("" if c is None else str(c).strip()) for c in r] for r in ws.iter_rows(values_only=True)]
    hi = next(i for i, r in enumerate(rows[:30]) if any(re.search(r"iso", c, re.I) for c in r))
    head = [h.lower() for h in rows[hi]]
    status["unodc_columns"] = rows[hi]
    col = lambda *pats: next((j for j, h in enumerate(head) for p in pats if re.search(p, h)), None)
    ci, ind, dim, cat, sex, age, yr, val = (col(r"iso"), col(r"^indicator"), col(r"^dimension"), col(r"^category"), col(r"^sex"),
                                             col(r"^age"), col(r"^year"), col(r"^value", r"^obs"))
    tot = lambda r, j: j is None or r[j].lower() in ("total", "", "all")
    out, seen = {}, {}
    for r in rows[hi + 1:]:
        if ci is None or len(r) <= max(x for x in (ci, ind, yr, val) if x is not None):
            continue
        iso = r[ci].upper()
        if not re.fullmatch(r"[A-Z]{3}", iso):
            continue
        try:
            v = float(str(r[val]).replace(",", ""))
            y = int(float(r[yr]))
        except ValueError:
            continue
        name = r[ind]
        key = name + ("" if tot(r, dim) and tot(r, cat) else f" — {r[dim] if dim is not None else ''} {r[cat] if cat is not None else ''}".rstrip())
        if not (tot(r, sex) and tot(r, age)):
            key += f" — {r[sex] if sex is not None else ''} {r[age] if age is not None else ''}".rstrip()
        seen[key] = seen.get(key, 0) + 1
        rec = out.setdefault(iso, {})
        best = rec.get(key)
        if not best or y > best[0]:
            rec[key] = (y, v)
    final = {}
    for iso, rec in out.items():
        f = {}
        for key, (y, v) in rec.items():
            k = key.lower()
            plain = key == key.split(" — ")[0]
            if plain and "detected" in k and "victim" in k:
                f["detected"], f["year_detected"] = v, y
            elif plain and "convict" in k:
                f["convicted"], f["year_convicted"] = v, y
            elif plain and "prosecut" in k:
                f["prosecuted"], f["year_prosecuted"] = v, y
            f[f"x_{key}, {y}"] = v
        final[iso] = f
    OUT.mkdir(exist_ok=True)
    (OUT / "unodc.json").write_text(json.dumps(final, indent=1, ensure_ascii=False))
    status["unodc_countries"] = len(final)
    status["unodc_series"] = dict(sorted(seen.items(), key=lambda kv: -kv[1])[:60])


def cbp(status, names, labels):
    page = get(CBP, 120).decode("utf-8", "replace")
    feats, unplaced = [], []
    # Each table sits under a heading naming the country (and whether WROs or Findings).
    for m in re.finditer(r"<table[\s\S]*?</table>", page, re.I):
        before = page[:m.start()]
        heads = re.findall(r"<(h[1-6]|button|strong|summary)[^>]*>([\s\S]*?)</\1>", before[-6000:], re.I)
        title = text(heads[-1][1]) if heads else ""
        kind = "Finding" if re.search(r"finding", title, re.I) else "Withhold Release Order"
        country = re.sub(r"\b(WROs?|Findings?|Withhold Release Orders?)\b", "", title, flags=re.I).strip(" -:–")
        rows = re.findall(r"<tr[\s\S]*?</tr>", m.group(0), re.I)
        if not rows:
            continue
        head = [text(c) for c in re.findall(r"<t[hd][^>]*>([\s\S]*?)</t[hd]>", rows[0], re.I)]
        iso = names.get(country.lower())
        at = labels.get(iso)
        for r in rows[1:]:
            cells = [text(c) for c in re.findall(r"<td[^>]*>([\s\S]*?)</td>", r, re.I)]
            if not any(cells):
                continue
            props = dict(zip(head, cells))
            props.update({"name": props.get("Entities") or props.get("Entity") or country, "country": country, "kind": kind,
                          "group": f"{kind}s", "source": CBP})
            if at:
                props["position"] = "the middle of its country: CBP gives no place"
                feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(at[0], 4), round(at[1], 4)]}, "properties": props})
            else:
                unplaced.append(props)
    OUT.mkdir(exist_ok=True)
    (OUT / "cbp_forced_labor.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    status["cbp"] = {"placed": len(feats), "not_placed": unplaced}


def main():
    stamp = OUT / "build.json"
    if stamp.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("slavery_world: weekly; not Monday")
        return
    OUT.mkdir(exist_ok=True)
    status, failed = {"date": datetime.date.today().isoformat()}, []
    names, labels = countries()
    for label, job in (("UNODC", lambda: unodc(status)), ("CBP", lambda: cbp(status, names, labels))):
        try:
            job()
        except Exception as e:  # noqa: BLE001
            failed.append(f"{label}: {e}")
            print(f"slavery_world: {label}: {e}", flush=True)
    stamp.write_text(json.dumps(status, indent=1, ensure_ascii=False))
    if failed:
        sys.exit("slavery_world: " + "; ".join(failed))


if __name__ == "__main__":
    main()
