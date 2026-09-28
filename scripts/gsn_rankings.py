#!/usr/bin/env python3
"""
Global Safety Net's country rankings as the map's own country shading (round
91b, asked 27 September: the map showed the rankings page itself in a box on
the map; the owner asked for it to be remade from the real data).

Source: the rankings' own spreadsheet, "Nature Wealth Rankings (GSN1).xlsx",
linked from https://www.globalsafetynet.app/rankings/ (One Earth; from
Dinerstein et al. 2020, Science Advances). Each country's protection level,
0 to 10: the share of the land the Global Safety Net finds most important for
species and climate that the World Database on Protected Areas records as
protected (0 = under 5%, 5 = about half, 10 = over 95%). The spreadsheet ranks
countries by size, and the EU's members and US states on their own.

Every sheet is read; each row's name is matched to a country (ISO 3166). Every
column the spreadsheet gives is kept for the map's box. Rows that are not
countries (US states, the EU as a whole) have no country shape on the map and
are listed in gsn/unmatched.json, not guessed at.

  gsn/countries.json   ISO3 -> {score, sheet, x_<column>: value, ...}
  gsn/unmatched.json   names that are not countries, by sheet
  gsn/build.json       the file read, its sheets and their columns

Weekly (Mondays) or by hand.
"""
import datetime, io, json, os, pathlib, re, subprocess, sys, urllib.request

URL = ("https://assets.takeshape.io/237b7856-239f-4c62-9f9e-0b9ce73fa864/dev/52d9cc52-0ebf-4bfe-8382-9fcb8aea01b0/"
       "Nature%20Wealth%20Rankings%20(GSN1).xlsx")
OUT = pathlib.Path("gsn")
# Names the ISO list spells differently.
FIX = {"bolivia": "BOL", "venezuela": "VEN", "iran": "IRN", "russia": "RUS", "syria": "SYR", "laos": "LAO", "vietnam": "VNM",
       "tanzania": "TZA", "south korea": "KOR", "north korea": "PRK", "korea, republic of": "KOR", "moldova": "MDA",
       "macedonia": "MKD", "north macedonia": "MKD", "czech republic": "CZE", "czechia": "CZE", "ivory coast": "CIV",
       "cote d'ivoire": "CIV", "côte d'ivoire": "CIV", "democratic republic of the congo": "COD", "dr congo": "COD",
       "drc": "COD", "congo, democratic republic of the": "COD", "republic of the congo": "COG", "congo": "COG",
       "congo-brazzaville": "COG", "swaziland": "SWZ", "eswatini": "SWZ", "cape verde": "CPV", "cabo verde": "CPV",
       "burma": "MMR", "myanmar": "MMR", "east timor": "TLS", "timor-leste": "TLS", "brunei": "BRN", "micronesia": "FSM",
       "the gambia": "GMB", "gambia": "GMB", "the bahamas": "BHS", "bahamas": "BHS", "turkey": "TUR", "turkiye": "TUR",
       "türkiye": "TUR", "palestine": "PSE", "taiwan": "TWN", "kosovo": "XKX", "united states": "USA",
       "united states of america": "USA", "usa": "USA", "uk": "GBR", "united kingdom": "GBR", "falkland islands": "FLK",
       "saint kitts and nevis": "KNA", "saint lucia": "LCA", "saint vincent and the grenadines": "VCT", "sao tome and principe": "STP",
       "são tomé and príncipe": "STP", "vatican": "VAT", "holy see": "VAT"}


def main():
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "openpyxl", "pycountry"], check=True)
    import openpyxl
    import pycountry
    stamp = OUT / "build.json"
    if stamp.exists() and not os.environ.get("GSN_AGAIN") and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("gsn_rankings: weekly; not Monday")
        return
    with urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "Culprits atlas build (WelcomeToYourGalaxy)"}), timeout=120) as r:
        data = r.read()
    # Round 97b (28 September): read in full, not read_only. In read_only mode
    # openpyxl trusts each sheet's stated size, and a sheet that states it
    # wrongly gives back almost nothing (every sheet here was "skipped").
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)

    def iso_of(name):
        k = re.sub(r"\s+", " ", str(name or "")).strip().strip("*").strip()
        low = k.lower()
        if low in FIX:
            return FIX[low]
        try:
            return pycountry.countries.lookup(k).alpha_3
        except LookupError:
            pass
        try:
            hits = pycountry.countries.search_fuzzy(k)
            return hits[0].alpha_3 if len(hits) == 1 else None
        except LookupError:
            return None

    out, unmatched, sheets = {}, {}, {}
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        rows = [r for r in rows if any(c not in (None, "") for c in r)]
        print(f"gsn_rankings: sheet {ws.title!r}, {len(rows)} rows; the first rows:", flush=True)
        for r in rows[:6]:
            print(f"    {[c for c in r if c not in (None, '')][:14]}", flush=True)
        us_sheet = bool(re.search(r"\b(usa|us|united states)\b", ws.title, re.I))
        # The header row: the first with a column naming the country or place.
        head_word = r"\b(countr(y|ies)|nations?|states?|names?|place|jurisdiction|territory)\b"
        def is_head(c):
            # A header cell names the column; a place's own name ("United
            # States") is a row of figures, not the header.
            return isinstance(c, str) and bool(re.search(head_word, c, re.I)) and not iso_of(c)
        head_i = next((i for i, r in enumerate(rows[:30]) if any(is_head(c) for c in r)), None)
        name_c = None
        if head_i is not None:
            head = [str(c).strip() if c is not None else "" for c in rows[head_i]]
            name_c = next(i for i, c in enumerate(rows[head_i]) if is_head(c))
        else:
            # No header names the column: the column the names are in is the
            # one whose cells are most often a country (or, on the US sheet,
            # most often words); the header is the row above its first name.
            width = max((len(r) for r in rows), default=0)
            def words(c):
                return [i for i, r in enumerate(rows) if c < len(r) and isinstance(r[c], str) and re.search(r"[A-Za-z]{3}", r[c])]
            if us_sheet:
                best = max(range(width), key=lambda c: len(words(c)), default=None)
                hits = words(best) if best is not None else []
            else:
                scored_cols = {c: [i for i in words(c) if iso_of(rows[i][c])] for c in range(width)}
                best = max(scored_cols, key=lambda c: len(scored_cols[c]), default=None)
                hits = scored_cols.get(best, []) if best is not None else []
            if len(hits) >= 3:
                name_c = best
                head_i = max(hits[0] - 1, 0) if hits[0] > 0 else None
                if head_i is None:
                    rows.insert(0, [None] * width)
                    head_i = 0
                head = [str(c).strip() if c is not None else "" for c in rows[head_i]]
                head += [""] * (width - len(head))
                head = [h or (f"column {i + 1}" if i != name_c else "place") for i, h in enumerate(head)]
        if name_c is None:
            sheets[ws.title] = {"skipped": "no column of country names found"}
            continue
        score_c = next((i for i, h in enumerate(head) if re.search(r"protection\s*level", h, re.I)), None)
        if score_c is None:
            score_c = next((i for i, h in enumerate(head) if re.search(r"\b(score|level)\b", h, re.I)), None)
        # A sheet of US states: "Georgia" there is the state, not the country.
        states = us_sheet or (bool(re.search(r"\bstates?\b", ws.title + " " + head[name_c], re.I))
                              and not re.search(r"united states|member", ws.title + " " + head[name_c], re.I))
        sheets[ws.title] = {"columns": head, "name_column": head[name_c], "score_column": head[score_c] if score_c is not None else None,
                            **({"not countries": "US states"} if states else {})}
        for r in rows[head_i + 1:]:
            if name_c >= len(r) or not r[name_c]:
                continue
            name = str(r[name_c]).strip()
            iso = None if states else iso_of(name)
            if not iso:
                unmatched.setdefault(ws.title, []).append(name)
                continue
            rec = out.setdefault(iso, {"name": name})
            rec.setdefault("sheets", []).append(ws.title)
            for i, h in enumerate(head):
                if h and i < len(r) and r[i] not in (None, ""):
                    # A country ranked in two sheets (by size, and among the EU's
                    # members) keeps both sheets' figures, the second named.
                    k = f"x_{h}" if f"x_{h}" not in rec else f"x_{h} ({ws.title})"
                    rec[k] = r[i] if not isinstance(r[i], (datetime.date, datetime.datetime)) else str(r[i])
            if score_c is not None and score_c < len(r):
                try:
                    v = float(r[score_c])
                    if 0 <= v <= 10 and "score" not in rec:
                        rec["score"] = v
                except (TypeError, ValueError):
                    pass
    for rec in out.values():
        rec["sheet"] = ", ".join(dict.fromkeys(rec.pop("sheets", [])))
    scored = {k: v for k, v in out.items() if "score" in v}
    print(f"gsn_rankings: {len(out)} countries matched, {len(scored)} with a protection level; sheets {list(sheets)}", flush=True)
    for t, s in sheets.items():
        print(f"  {t}: {s}", flush=True)
    if not scored:
        raise SystemExit("gsn_rankings: no protection level read; see the columns above")
    OUT.mkdir(exist_ok=True)
    (OUT / "countries.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    (OUT / "unmatched.json").write_text(json.dumps(unmatched, indent=1, ensure_ascii=False))
    stamp.write_text(json.dumps({"from": URL, "read": datetime.date.today().isoformat(), "bytes": len(data), "sheets": sheets,
                                 "countries": len(out), "scored": len(scored)}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
