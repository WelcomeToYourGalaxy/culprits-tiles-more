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


def find_xlsx():
    found = []
    for page in PAGES:
        try:
            html = get(page, 120).decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            print(f"isds: {page} did not answer ({e})", flush=True)
            continue
        for h in re.findall(r'href="([^"]+\.xlsx?[^"]*)"', html, re.I):
            found.append(urllib.parse.urljoin(page, h))
        # A newer release is linked from the publications list by its title.
        for h in re.findall(r'href="([^"]*publications/\d+/investment-dispute-settlement-navigator-full[^"]*)"', html, re.I):
            try:
                sub = get(urllib.parse.urljoin(page, h), 120).decode("utf-8", "replace")
                found += [urllib.parse.urljoin(h, x) for x in re.findall(r'href="([^"]+\.xlsx?[^"]*)"', sub, re.I)]
            except Exception:  # noqa: BLE001
                pass
    if not found:
        raise SystemExit("isds: no excel link found on UNCTAD's pages")
    return found


def main():
    today = datetime.date.today()
    if (OUT / "cases.json").exists() and today.weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("isds: weekly; not Monday")
        return
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "openpyxl"], check=True)
    import openpyxl
    links = find_xlsx()
    wb, used = None, None
    for u in links:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(get(u)), data_only=True)
            used = u
            break
        except Exception as e:  # noqa: BLE001
            print(f"isds: {u} could not be read ({e})", flush=True)
    if not wb:
        raise SystemExit("isds: no excel file could be read")
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
    def iso(n):
        return names.get(re.sub(r"\s+", " ", str(n or "")).strip().lower())
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
    OUT.mkdir(exist_ok=True)
    resp, un1 = tally(cases, c_resp)
    home, un2 = tally(cases, c_home)
    ect_resp, un3 = tally(ect, c_resp)
    (OUT / "cases.json").write_text(json.dumps(cases, ensure_ascii=False, default=str))
    (OUT / "respondents.json").write_text(json.dumps(resp, ensure_ascii=False))
    (OUT / "home_states.json").write_text(json.dumps(home, ensure_ascii=False))
    (OUT / "ect_respondents.json").write_text(json.dumps(ect_resp, ensure_ascii=False))
    (OUT / "build.json").write_text(json.dumps({"from": used, "sheet": title, "columns": head, "cases": len(cases), "ect_cases": len(ect),
                                               "columns_used": {"respondent": c_resp, "home": c_home, "name": c_name, "year": c_year, "treaty": c_treaty, "outcome": c_out},
                                               "names_not_matched": {"respondent": un1, "home": un2, "ect": un3}, "read": today.isoformat()}, indent=1, ensure_ascii=False))
    print(f"isds: {len(cases)} cases ({len(ect)} under the Energy Charter Treaty), {len(resp)} states sued; unmatched {len(un1)}", flush=True)


if __name__ == "__main__":
    main()
