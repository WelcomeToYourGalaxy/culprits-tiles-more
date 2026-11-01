"""Round 123b (asked 2 October: the ISDS tracker and the Energy Charter Treaty
rows only opened outside pages; "any way to add their data directly to the
map in their entirety?"). Neither the Global ISDS Tracker nor the Energy
Charter "dirty secrets" site offers a download. UN Trade and Development
(UNCTAD) publishes its full case list free of charge, to be cited as:
UNCTAD, Investment Dispute Settlement Navigator: full data release (excel
format), https://investmentpolicy.unctad.org/investment-dispute-settlement.

Every case and every column of the newest release is kept (isds/cases.json).
Per country (isds/respondents.json, ISO3): how many cases name it as the
state sued, and each case's name, year and outcome; how many investors from
it sued another state (isds/home_states.json). The same again for the cases
brought under the Energy Charter Treaty, chosen by the release's own treaty
column (isds/ect_respondents.json). Weekly (Mondays) or by hand.
"""
import datetime, io, json, os, pathlib, re, subprocess, sys, urllib.parse, urllib.request

OUT = pathlib.Path("isds")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; WelcomeToYourGalaxy)"}
PAGES = ["https://investmentpolicy.unctad.org/publications/1303/investment-dispute-settlement-navigator-full-isds-data-release-as-of-31-12-2023-in-excel-format-",
         "https://investmentpolicy.unctad.org/investment-dispute-settlement"]
NAMES = "https://raw.githubusercontent.com/WelcomeToYourGalaxy/culprits/main/pipeline/shapes/names_iso3.json"


def get(url, timeout=300):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def links_on(page, html):
    """Every link on a page that could be the excel file: an .xlsx/.xls address,
    UNCTAD's uploaded-files folder, or a "download" link (the publication page's
    Download publication button)."""
    out = []
    for h in re.findall(r'href=["\']([^"\']+)["\']', html, re.I):
        if re.search(r"\.xlsx?(\?|$)|uploaded-files|/download", h, re.I):
            out.append(urllib.parse.urljoin(page, h))
    return out


def find_xlsx(tried):
    """Candidate addresses of the newest release, newest publication first."""
    found = []
    for page in PAGES:
        try:
            html = get(page, 120).decode("utf-8", "replace")
            tried.append({"page": page, "answered": True})
        except Exception as e:  # noqa: BLE001
            tried.append({"page": page, "answered": f"{type(e).__name__}: {e}"})
            print(f"isds: {page} did not answer ({e})", flush=True)
            continue
        found += links_on(page, html)
        # A newer release is linked by its title; open each such page too.
        for h in re.findall(r'href=["\']([^"\']*publications/\d+/investment-dispute-settlement-navigator-full[^"\']*)["\']', html, re.I):
            sub_url = urllib.parse.urljoin(page, h)
            try:
                found += links_on(sub_url, get(sub_url, 120).decode("utf-8", "replace"))
                tried.append({"page": sub_url, "answered": True})
            except Exception as e:  # noqa: BLE001
                tried.append({"page": sub_url, "answered": f"{type(e).__name__}: {e}"})
    seen, ordered = set(), []
    for u in found:
        if u not in seen:
            seen.add(u)
            ordered.append(u)
    return ordered


def main():
    today = datetime.date.today()
    if (OUT / "cases.json").exists() and today.weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("isds: weekly; not Monday")
        return
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "openpyxl"], check=True)
    import openpyxl
    OUT.mkdir(exist_ok=True)
    tried, wb, used = [], None, None
    # Round 185o: no build had ever been written (isds/ never appeared), so
    # why was unknown. A copy downloaded by hand into isds/download/ is read
    # first; otherwise every page and link tried is written to isds/build.json.
    local = sorted((OUT / "download").glob("*.xls*"), key=lambda p: p.stat().st_mtime)
    for p in reversed(local):
        try:
            wb = openpyxl.load_workbook(p, data_only=True)
            used = f"the copy uploaded by hand: {p}"
            break
        except Exception as e:  # noqa: BLE001
            tried.append({"file": str(p), "read": f"{type(e).__name__}: {e}"})
    if not wb:
        for u in find_xlsx(tried):
            try:
                raw = get(u)
            except Exception as e:  # noqa: BLE001
                tried.append({"link": u, "read": f"{type(e).__name__}: {e}"})
                continue
            if raw[:2] != b"PK":
                tried.append({"link": u, "read": f"not an excel file (starts {raw[:40]!r})"})
                continue
            try:
                wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
                used = u
                break
            except Exception as e:  # noqa: BLE001
                tried.append({"link": u, "read": f"{type(e).__name__}: {e}"})
    if not wb:
        (OUT / "build.json").write_text(json.dumps({"built": False, "read": today.isoformat(), "tried": tried,
                                                   "what to do": "download the excel file from https://investmentpolicy.unctad.org/investment-dispute-settlement "
                                                                 "(the ISDS data set in excel format link) and upload it to isds/download/"}, indent=1))
        print(f"::warning::isds: no excel file could be read; {len(tried)} pages and links tried, listed in isds/build.json")
        return
    # The sheet and heading row that name the respondent state.
    best = None
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        for i, r in enumerate(rows[:30]):
            cells = [str(c or "").strip() for c in r]
            if any(re.search(r"respondent", c, re.I) for c in cells) and sum(1 for c in cells if c) >= 5:
                best = (ws.title, i, cells, rows)
                break
        if best:
            break
    if not best:
        raise SystemExit("isds: no sheet with a respondent column")
    title, hi, head, rows = best
    head = [h or f"column {k + 1}" for k, h in enumerate(head)]
    cases = []
    for r in rows[hi + 1:]:
        rec = {head[k]: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in enumerate(r) if k < len(head) and v not in (None, "")}
        if len(rec) >= 3:
            cases.append(rec)
    col = lambda pat: next((h for h in head if re.search(pat, h, re.I)), None)  # noqa: E731
    c_resp, c_home = col(r"respondent"), col(r"home state")
    c_name, c_year = col(r"short case name|case name|^case"), col(r"year of initiation|^year|initiat")
    c_treaty, c_out = col(r"applicable (iia|treaty)|treaty"), col(r"outcome|status")
    names = json.loads(get(NAMES, 120))
    # Round 188o: UNCTAD's own spellings of three places the names file lacks.
    # The European Union is sued as a party of its own and is no one country;
    # its cases stay listed under names_not_matched in isds/build.json.
    unctad = {"congo, democratic republic of the": "COD", "hong kong, china sar": "HKG", "macao, china sar": "MAC"}
    def iso(n):
        k = re.sub(r"\s+", " ", str(n or "")).strip().lower()
        return names.get(k) or unctad.get(k)
    def tally(chosen, key):
        out, unmatched = {}, set()
        for c in chosen:
            for part in re.split(r";|\n|\s/\s", str(c.get(key) or "")):
                part = part.strip()
                if not part:
                    continue
                i = iso(part)
                if not i:
                    unmatched.add(part)
                    continue
                d = out.setdefault(i, {"x_name": part, "x_cases": 0, "x_case_list": []})
                d["x_cases"] += 1
                d["x_case_list"].append(" · ".join(str(c.get(k)) for k in (c_name, c_year, c_out) if k and c.get(k) not in (None, "")))
        for d in out.values():
            d["x_case_list"] = "; ".join(d["x_case_list"])
        return out, sorted(unmatched)
    ect = [c for c in cases if c_treaty and re.search(r"energy charter", str(c.get(c_treaty) or ""), re.I)]
    resp, un1 = tally(cases, c_resp)
    home, un2 = tally(cases, c_home)
    ect_resp, un3 = tally(ect, c_resp)
    (OUT / "cases.json").write_text(json.dumps(cases, ensure_ascii=False, default=str))
    (OUT / "respondents.json").write_text(json.dumps(resp, ensure_ascii=False))
    (OUT / "home_states.json").write_text(json.dumps(home, ensure_ascii=False))
    (OUT / "ect_respondents.json").write_text(json.dumps(ect_resp, ensure_ascii=False))
    (OUT / "build.json").write_text(json.dumps({"built": True, "tried": tried, "from": used, "sheet": title, "columns": head, "cases": len(cases), "ect_cases": len(ect),
                                               "columns_used": {"respondent": c_resp, "home": c_home, "name": c_name, "year": c_year, "treaty": c_treaty, "outcome": c_out},
                                               "names_not_matched": {"respondent": un1, "home": un2, "ect": un3}, "read": today.isoformat()}, indent=1, ensure_ascii=False))
    print(f"isds: {len(cases)} cases ({len(ect)} under the Energy Charter Treaty), {len(resp)} states sued; unmatched {len(un1)}", flush=True)


if __name__ == "__main__":
    main()
