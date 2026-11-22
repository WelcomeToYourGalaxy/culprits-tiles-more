#!/usr/bin/env python3
"""
Deforestation funds, step one (round 61, 26 September): the two sources read
and matched, and a report of how well they match. Nothing is published to the
map yet; the owner sees the report first.

  Forest 500 (Global Canopy; CC BY-NC 4.0; cite "Forest 500 assessment data
  [Year], Global Canopy, Forest500.org"): the companies and financial
  institutions it assesses for deforestation risk, every field of every row,
  read from the API its own rankings page reads (api.forestiq.org). Saved to
  forest500/rankings.json, with what the API says it holds in
  probe/forestiq/openapi.json.

  SEC Form N-PORT data sets: every US-registered fund's holdings, the latest
  quarter. The SEC asks automated readers to name themselves with a contact
  address; the owner gave welcometoyourgalaxy@gmail.com (26 September), sent
  only to the SEC.

Matching, with no guessing (no fuzzy names):
  1. A Forest 500 company's ticker as Forest 500 writes it (e.g. "4452 JP")
     is looked for, exactly, among the tickers the funds report for their
     holdings.
  2. Where every holding found that way names one and the same issuer LEI,
     that LEI is the company's; every holding with that LEI is then the
     company's too, whatever ticker the fund wrote.
  3. Companies with no ticker, no exact ticker match, or ticker matches that
     disagree on the LEI are listed as unmatched, with the reason.
Saved to defor_funds/matches.json (per company: how matched, the LEI, how
many funds hold it and the value held) and defor_funds/report.json (the
counts, and every unmatched company with its reason). The holdings of matched
companies, fund by fund, go to defor_funds/holdings.json.gz.

Runs when the quarter or the Forest 500 year changes; DEFOR_AGAIN=1 runs again.
"""
import csv, gzip, io, json, os, pathlib, re, sys, time, urllib.parse, urllib.request, zipfile

UA = {"User-Agent": "WelcomeToYourGalaxy Culprits map welcometoyourgalaxy@gmail.com", "Accept-Encoding": "identity"}
F500_API = "https://api.forestiq.org/api/"
NPORT_PAGE = "https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets"
NPORT_ZIP = "https://www.sec.gov/files/dera/data/form-n-port-data-sets/{q}_nport.zip"
OUT = pathlib.Path("defor_funds")
PROBE = pathlib.Path("probe/forestiq")
F500_OUT = pathlib.Path("forest500")
csv.field_size_limit(1 << 30)


def get(url, tries=5, timeout=600, to=None):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                if to:
                    with open(to, "wb") as f:
                        while True:
                            b = r.read(1 << 20)
                            if not b:
                                break
                            f.write(b)
                    return True
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"    {url}: {e}; again in {30 * (i + 1)}s", flush=True)
            time.sleep(30 * (i + 1))


def forest500():
    PROBE.mkdir(parents=True, exist_ok=True)
    try:
        (PROBE / "openapi.json").write_bytes(get(F500_API, tries=2, timeout=120))
    except Exception as e:  # noqa: BLE001
        print(f"  Forest 500 API description not read: {e}", flush=True)
    rows, offset = [], 0
    while True:
        part = json.loads(get(F500_API + "f500_company_rankings?" + urllib.parse.urlencode({"limit": 1000, "offset": offset}), timeout=180))
        rows.extend(part)
        if len(part) < 1000:
            break
        offset += 1000
    F500_OUT.mkdir(exist_ok=True)
    (F500_OUT / "rankings.json").write_text(json.dumps({"read": time.strftime("%Y-%m-%d", time.gmtime()), "source": F500_API + "f500_company_rankings",
                                                         "licence": "CC BY-NC 4.0; Forest 500 assessment data, Global Canopy, Forest500.org",
                                                         "rows": rows}, ensure_ascii=False))
    latest = max(r["ayear"] for r in rows)
    # One row per company for the latest year (the API repeats a company once per commodity row).
    firms = {}
    for r in rows:
        if r["ayear"] == latest:
            firms.setdefault(r["flid"], r)
    print(f"  Forest 500: {len(rows):,} rows; {len(firms)} companies and institutions assessed in {latest}", flush=True)
    return latest, list(firms.values())


def norm_ticker(t):
    return re.sub(r"\s+", " ", str(t or "").strip().upper())


def nport_latest():
    page = get(NPORT_PAGE).decode("utf-8", "replace")
    qs = sorted(set(re.findall(r"/files/dera/data/form-n-port-data-sets/(\d{4}q\d)_nport\.zip", page)))
    if not qs:
        sys.exit("N-PORT: no quarterly files on the SEC's page")
    return qs[-1]


def table(z, stem):
    name = next((n for n in z.namelist() if pathlib.Path(n).stem.upper() == stem), None)
    if not name:
        sys.exit(f"N-PORT: no {stem} table in the file ({z.namelist()})")
    f = io.TextIOWrapper(z.open(name), encoding="utf-8", errors="replace", newline="")
    return csv.DictReader(f, delimiter="\t")


def main():
    stamp = OUT / "report.json"
    year, firms = forest500()
    q = nport_latest()
    old = json.loads(stamp.read_text()) if stamp.exists() else {}
    if old.get("quarter") == q and old.get("forest500_year") == year and not os.environ.get("DEFOR_AGAIN"):
        print(f"defor_funds: {q} and Forest 500 {year} already matched")
        return
    want = {}
    for f in firms:
        t = norm_ticker(f.get("coticker"))
        if t:
            want.setdefault(t, []).append(f["flid"])
    path = pathlib.Path("/tmp") / f"{q}_nport.zip"
    if not path.exists():
        print(f"  N-PORT: downloading {q}", flush=True)
        get(NPORT_ZIP.format(q=q), timeout=3600, to=path)
    with zipfile.ZipFile(path) as z:
        cols = {pathlib.Path(n).stem: None for n in z.namelist()}
        # 1. Which holdings carry a Forest 500 ticker.
        by_ticker, seen = {}, {}
        for r in table(z, "IDENTIFIERS"):
            t = norm_ticker(r.get("IDENTIFIER_TICKER"))
            if t and len(seen) < 2000:
                seen[t] = seen.get(t, 0) + 1
            if t in want:
                by_ticker.setdefault(r.get("HOLDING_ID"), t)
        # How the funds write tickers, for the report (what the matching is up against).
        pathlib.Path("probe/nport").mkdir(parents=True, exist_ok=True)
        pathlib.Path("probe/nport/tickers_sample.json").write_text(json.dumps(seen, indent=0))
        print(f"  N-PORT: {len(by_ticker):,} holdings carry a Forest 500 ticker", flush=True)
        holdings = {}
        lei_of_ticker = {}
        rows_h = list()  # holdings of matched LEIs, kept after pass 2
        for r in table(z, "FUND_REPORTED_HOLDING"):
            hid = r.get("HOLDING_ID")
            if hid in by_ticker:
                lei_of_ticker.setdefault(by_ticker[hid], {}).setdefault((r.get("ISSUER_LEI") or "").strip(), 0)
                lei_of_ticker[by_ticker[hid]][(r.get("ISSUER_LEI") or "").strip()] += 1
        # 2. A ticker whose holdings all name one LEI gives that LEI.
        lei_to_flids, reasons, how = {}, {}, {}
        for t, flids in want.items():
            leis = {k: v for k, v in lei_of_ticker.get(t, {}).items() if k and k.upper() not in ("N/A", "NA", "NONE")}
            for flid in flids:
                if t not in lei_of_ticker:
                    reasons[flid] = f"no fund reports a holding with the ticker {t}"
                elif len(leis) != 1:
                    reasons[flid] = (f"holdings with the ticker {t} name {len(leis)} different issuer LEIs" if leis
                                     else f"holdings with the ticker {t} give no issuer LEI")
                else:
                    lei = next(iter(leis))
                    lei_to_flids.setdefault(lei, []).append(flid)
                    how[flid] = {"ticker": t, "lei": lei, "holdings_with_ticker": sum(lei_of_ticker[t].values())}
        # 3. Every holding with a matched LEI.
        keep = []
        for r in table(z, "FUND_REPORTED_HOLDING"):
            lei = (r.get("ISSUER_LEI") or "").strip()
            if lei in lei_to_flids:
                keep.append({k: v for k, v in r.items() if v not in (None, "")})
        accs = {r.get("ACCESSION_NUMBER") for r in keep}
        funds = {}
        for r in table(z, "FUND_REPORTED_INFO"):
            if r.get("ACCESSION_NUMBER") in accs:
                funds[r["ACCESSION_NUMBER"]] = {k: v for k, v in r.items() if v not in (None, "")}
        regs = {}
        for r in table(z, "REGISTRANT"):
            if r.get("ACCESSION_NUMBER") in accs:
                regs[r["ACCESSION_NUMBER"]] = {k: v for k, v in r.items() if v not in (None, "")}
    matches = []
    for f in firms:
        flid = f["flid"]
        m = {"flid": flid, "company": f.get("coname"), "type": f.get("cotype"), "hq": f.get("cohq"), "ticker": f.get("coticker"),
             "forest500_year": year, "total_score": f.get("totalscore"), "total_max": f.get("totalmax")}
        if flid in how:
            lei = how[flid]["lei"]
            mine = [h for h in keep if h.get("ISSUER_LEI", "").strip() == lei]
            m.update({"matched_by": f"ticker {how[flid]['ticker']} exactly, then its issuer LEI", "lei": lei,
                      "holdings": len(mine), "funds": len({h.get('ACCESSION_NUMBER') for h in mine})})
        else:
            m["unmatched"] = reasons.get(flid, "Forest 500 gives no ticker")
        matches.append(m)
    OUT.mkdir(exist_ok=True)
    (OUT / "matches.json").write_text(json.dumps(matches, ensure_ascii=False, indent=1))
    with gzip.open(OUT / "holdings.json.gz", "wt", encoding="utf-8") as g:
        json.dump({"quarter": q, "holdings": keep, "funds": funds, "registrants": regs}, g, ensure_ascii=False)
    got = [m for m in matches if "lei" in m]
    stamp.write_text(json.dumps({"quarter": q, "forest500_year": year, "forest500_companies": len(firms), "matched": len(got),
                                 "holdings": len(keep), "funds": len(funds), "tables_in_file": sorted(cols),
                                 "unmatched": [{"company": m["company"], "ticker": m["ticker"], "why": m["unmatched"]} for m in matches if "unmatched" in m]},
                                ensure_ascii=False, indent=1))
    print(f"defor_funds: {len(got)} of {len(firms)} Forest 500 companies matched; {len(keep):,} holdings in {len(funds):,} fund reports")


if __name__ == "__main__":
    main()
