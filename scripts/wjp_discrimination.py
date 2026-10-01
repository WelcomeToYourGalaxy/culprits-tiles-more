"""Equal treatment and absence of discrimination, country by country
(World Justice Project Rule of Law Index, sub-factor 4.1).

Written 30 September (round 117b). The owner asked for the map in WJP's article
"Discrimination is Getting Worse Globally" to be redrawn on the Discrimination
heading; that map is a picture. It is drawn from WJP's own Index scores, so the
scores are read here from WJP's published historical data file (every edition,
every country) and the map draws them itself. The article's picture was not
read (the page could not be opened from the build chat), so which years it
compares is not known here; this copy keeps every edition's score for each
country and works out two changes from them: since the 2015 edition (the first
with a single year's survey for most countries) and since the edition before
the latest.

WJP scores run from 0 to 1; 1 is the strongest adherence to the rule of law,
here the least discrimination. Nothing is rescaled: each country's scores are
written as WJP gives them.

Writes discrimination/wjp.json ({ISO3: {...}}) and discrimination/build.json.
Terms of use of WJP's data were not verified when this was written.
"""
import io, json, pathlib, re, subprocess, sys, time, urllib.request

OUT = pathlib.Path("discrimination")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; github.com/WelcomeToYourGalaxy)"}
PAGES = ["https://worldjusticeproject.org/rule-of-law-index/downloads",
         "https://worldjusticeproject.org/rule-of-law-index/global",
         "https://worldjusticeproject.org/rule-of-law-index/"]
BASE_EDITION = 2015
SUB = re.compile(r"^\s*4\.1\b")


def fetch(url, timeout=120):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read(), r.geturl()


def candidates():
    """Links to the historical data file, from WJP's pages first, then the
    names WJP has used for it."""
    seen = []
    for page in PAGES:
        try:
            html, at = fetch(page, 60)
        except Exception as e:
            print(f"  {page}: {e}")
            continue
        for href in re.findall(r'href="([^"]+\.xlsx)"', html.decode("utf-8", "replace"), re.I):
            u = urllib.request.urljoin(at, href)
            if "histor" in u.lower() and u not in seen:
                seen.append(u)
    for y in range(time.gmtime().tm_year + 1, 2020, -1):
        for name in (f"FINAL_{y}_wjp_rule_of_law_index_HISTORICAL_DATA_FILE.xlsx", f"{y}_wjp_rule_of_law_index_HISTORICAL_DATA_FILE.xlsx",
                     f"{y}_wjp_rule_of_law_index_HISTORICAL_DATA_FILE_0.xlsx"):
            u = f"https://worldjusticeproject.org/rule-of-law-index/downloads/{name}"
            if u not in seen:
                seen.append(u)
    return seen


def first_year(v):
    m = re.search(r"(19|20)\d\d", str(v or ""))
    return int(m.group(0)) if m else None


def main():
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "openpyxl"], check=True)
    import openpyxl
    OUT.mkdir(exist_ok=True)
    tried, book, used = [], None, None
    for u in candidates():
        try:
            data, _ = fetch(u)
            book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            used = u
            break
        except Exception as e:
            tried.append(f"{u}: {str(e)[:120]}")
    if not book:
        (OUT / "build.json").write_text(json.dumps({"built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "found": False,
                                                    "tried": tried}, indent=1))
        sys.exit("WJP's historical data file was not found; discrimination/build.json lists the addresses tried.")
    best = None
    for ws in book.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        for i, r in enumerate(rows[:15]):
            heads = [str(c or "").strip() for c in r]
            code = next((j for j, h in enumerate(heads) if h.lower() in ("country code", "country_code", "iso3", "code")), None)
            sub = next((j for j, h in enumerate(heads) if SUB.match(h)), None)
            year = next((j for j, h in enumerate(heads) if h.lower() in ("year", "edition")), None)
            name = next((j for j, h in enumerate(heads) if h.lower() in ("country", "country/jurisdiction", "country name")), None)
            if code is not None and sub is not None and year is not None:
                if not best or len(rows) > len(best[1]):
                    best = (ws.title, rows, i, code, sub, year, name, heads[sub])
                break
    if not best:
        sys.exit("No sheet with a country code, a year and a 4.1 column was found in " + used)
    title, rows, h, code, sub, year, name, label = best
    per = {}
    for r in rows[h + 1:]:
        iso = str(r[code] or "").strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", iso):
            continue
        try:
            v = float(r[sub])
        except (TypeError, ValueError):
            continue
        per.setdefault(iso, {"name": r[name] if name is not None else iso, "scores": []})["scores"].append((str(r[year]).strip(), first_year(r[year]), round(v, 4)))
    out = {}
    for iso, c in per.items():
        sc = sorted((s for s in c["scores"] if s[1]), key=lambda s: s[1])
        if not sc:
            continue
        last = sc[-1]
        rec = {"name": c["name"], "score": last[2], "edition": last[0],
               "every_edition": "; ".join(f"{e}: {v}" for e, _, v in sc),
               "measure": label, "scale": "0 to 1; 1 is the least discrimination"}
        base = next((s for s in sc if s[1] == BASE_EDITION), None)
        if base and base is not last:
            rec["change_since_2015"] = round(last[2] - base[2], 4)
            rec["worse_since_2015"] = round(base[2] - last[2], 4)
        if len(sc) > 1:
            prev = sc[-2]
            rec["previous_edition"] = prev[0]
            rec["change_since_previous"] = round(last[2] - prev[2], 4)
        # Round 119b: each edition's score on its own, so any one edition can
        # be drawn (the owner's attached map is the 2022 edition's).
        for e, y, v in sc:
            rec[f"score_{y}"] = v
        out[iso] = rec
    for y in sorted({k[6:] for r in out.values() for k in r if k.startswith("score_") and k[6:].isdigit()}):
        ranked = sorted(((r[f"score_{y}"], iso) for iso, r in out.items() if f"score_{y}" in r), reverse=True)
        for i, (_, iso) in enumerate(ranked, 1):
            out[iso][f"rank_{y}"] = f"{i} of {len(ranked)} (1 = least discrimination)"
    (OUT / "wjp.json").write_text(json.dumps(out, indent=0, ensure_ascii=False))
    worse = sum(1 for r in out.values() if r.get("change_since_2015", 0) < 0)
    both = sum(1 for r in out.values() if "change_since_2015" in r)
    (OUT / "build.json").write_text(json.dumps({"built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "found": True,
                                                "file": used, "sheet": title, "column": label, "countries": len(out),
                                                "lower_than_2015": worse, "with_2015_and_later": both}, indent=1))
    print(f"  {len(out)} countries from {used} ({title}, {label}); {worse} of {both} score lower than in 2015")


if __name__ == "__main__":
    main()
