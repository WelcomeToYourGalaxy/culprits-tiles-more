#!/usr/bin/env python3
"""
Banking on Climate Chaos 2026: the 65 banks, placed at their headquarters.

  * Figures: the report's two league tables, read from the report itself
    (Rainforest Action Network's copy of the PDF): fossil fuel financing and
    fossil fuel expansion financing, each bank's rank, every year 2021-2025,
    the five-year total, and the change 2024-2025, as the report prints them.
    The site offers no data file; the tables are the published figures.
  * Which company each bank is: the parent the report aggregates to, matched
    to its entry in the Global Legal Entity Identifier register (GLEIF), by
    the LEI or exact legal name approved on 25 September (PAIRS below).
  * Where: the headquarters address that register gives, found in
    OpenStreetMap (Nominatim); if the street is not found, the city.

Writes bocc/banks.geojson and bocc/banks.build.json (every pairing, what was
found for each address). A table that does not read as 65 banks stops the
build rather than guessing. Built once; BOCC_REBUILD=1 builds again.
"""
import io, json, os, pathlib, re, subprocess, sys, time, unicodedata, urllib.parse, urllib.request

PDF = "https://www.ran.org/wp-content/uploads/2026/06/BOCC_2026_vFINAL-1.pdf"
OUT = pathlib.Path("bocc")
UA = {"User-Agent": "Culprits atlas (github.com/WelcomeToYourGalaxy) Banking on Climate Chaos map build"}

# Report name -> (LEI if already seen in the register, else exact legal names
# to look for, in order; the country the entity is registered in).
PAIRS = {
    "JPMorgan Chase": ("8I5DZWZKVSZI1NUHU748", [], "US"),
    "Bank of America": ("9DJT3UXIJIZJI4WXO774", [], "US"),
    "Mitsubishi UFJ Financial": ("353800V2V8PUY9TK3E06", [], "JP"),
    "Mizuho Financial": ("353800CI5L6DDAN5XZ33", [], "JP"),
    "Citigroup": (None, ["Citigroup Inc."], "US"),
    "Wells Fargo": (None, ["Wells Fargo & Company"], "US"),
    "Royal Bank of Canada": (None, ["Royal Bank of Canada"], "CA"),
    "Barclays": (None, ["Barclays PLC"], "GB"),
    "SMBC Group": ("35380028MYWPB6AUO129", [], "JP"),
    "Morgan Stanley": (None, ["Morgan Stanley"], "US"),
    "Goldman Sachs": (None, ["The Goldman Sachs Group, Inc."], "US"),
    "Toronto-Dominion Bank": ("PT3QB789TSUIDF371261", [], "CA"),
    "Scotiabank": (None, ["The Bank of Nova Scotia"], "CA"),
    "Truist Financial": ("549300DRQQI75D2JP341", [], "US"),
    "CIBC": (None, ["Canadian Imperial Bank of Commerce"], "CA"),
    "CITIC": (None, ["CITIC Group Corporation", "中国中信集团有限公司"], "CN"),
    "Bank of China": (None, ["Bank of China Limited", "中国银行股份有限公司"], "CN"),
    "PNC Financial Services": ("CFGNEKW0P8842LEUIA51", [], "US"),
    "US Bancorp": (None, ["U.S. Bancorp"], "US"),
    "Deutsche Bank": (None, ["Deutsche Bank Aktiengesellschaft"], "DE"),
    "Santander": (None, ["Banco Santander, S.A."], "ES"),
    "HSBC": (None, ["HSBC Holdings plc"], "GB"),
    "BMO Financial Group": (None, ["Bank of Montreal"], "CA"),
    "Industrial and Commercial Bank of China": ("2549005QXSCD8MSHQU78", [], "CN"),
    "Standard Chartered": ("U4LOSYZ7YG4W3S5F2G91", [], "GB"),
    "China Merchants Bank": ("254900SEWBR5POA0TF02", [], "CN"),
    "China Construction Bank": ("2549006EHFY98CQJZN84", [], "CN"),
    "ING Group": ("549300NYKK9MWM7GGW15", [], "NL"),
    "Société Générale": (None, ["Societe Generale"], "FR"),
    "Crédit Agricole": (None, ["Crédit Agricole S.A."], "FR"),
    "Banco Bilbao Vizcaya Argentaria (BBVA)": (None, ["Banco Bilbao Vizcaya Argentaria, S.A."], "ES"),
    "Industrial Bank Company": ("300300C1030935001303", [], "CN"),
    "BNP Paribas": (None, ["BNP Paribas"], "FR"),
    "Agricultural Bank of China": (None, ["Agricultural Bank of China Limited", "中国农业银行股份有限公司"], "CN"),
    "Shanghai Pudong Development Bank": ("300300C1031031001330", [], "CN"),
    "Groupe BPCE": (None, ["BPCE"], "FR"),
    "China Everbright": (None, ["China Everbright Group Ltd.", "中国光大集团股份公司"], "CN"),
    "Capital One Financial": (None, ["Capital One Financial Corporation"], "US"),
    "State Bank of India": (None, ["State Bank of India"], "IN"),
    "Intesa Sanpaolo": (None, ["Intesa Sanpaolo S.p.A.", "Intesa Sanpaolo Società per Azioni"], "IT"),
    "Bank of Beijing": ("300300C1080211000042", [], "CN"),
    "UniCredit": (None, ["UniCredit S.p.A.", "UniCredit, Società per Azioni"], "IT"),
    "China Minsheng Banking": ("549300HBUGSQD1VCXG94", [], "CN"),
    "DBS": ("5493007FKT78NKPM5V55", [], "SG"),
    "Ping An Insurance Group": ("529900M9MC28JLN35U89", [], "CN"),
    "UBS": ("549300SZJ9VS8SGXAN81", [], "CH"),
    "Bank of Jiangsu": ("300300C1086832000046", [], "CN"),
    "Rabobank": (None, ["Coöperatieve Rabobank U.A."], "NL"),
    "NatWest": (None, ["NatWest Group plc"], "GB"),
    "Commerzbank": (None, ["Commerzbank Aktiengesellschaft"], "DE"),
    "ANZ": (None, ["Australia and New Zealand Banking Group Limited"], "AU"),
    "Bank of Communications": ("984500C4F39MFEE54196", [], "CN"),
    "KB Financial Group": ("529900TKE4MXG3Q6GW86", [], "KR"),
    "Lloyds Banking Group": ("549300PPXHEU2JF0AM85", [], "GB"),
    "DZ Bank": (None, ["DZ BANK AG Deutsche Zentral-Genossenschaftsbank, Frankfurt am Main"], "DE"),
    "Postal Savings Bank of China": ("300300C1040311005298", [], "CN"),
    "Danske Bank": (None, ["Danske Bank A/S"], "DK"),
    "La Caixa Group": (None, ["CaixaBank, S.A."], "ES"),
    "National Australia Bank": ("F8SB4JFBSYQFRQEH3Z21", [], "AU"),
    "Hua Xia Bank": ("300300AKNDEHIGVDZW37", [], "CN"),
    "Westpac": ("EN5TNI6CI43VEPAMHL14", [], "AU"),
    "Nordea": ("529900ODI3047E2LIV03", [], "FI"),
    "Commonwealth Bank of Australia": ("MSFSBD3QN1GSN7Q6C537", [], "AU"),
    "Crédit Mutuel": ("9695000CG7B84NLR5984", [], "FR"),
    "La Banque Postale": (None, ["La Banque Postale"], "FR"),
}

MONEY = r"(?:\$[\d.,]+ [BMT]|-)"
NAME_LINE = re.compile(r"^(\d{1,2}) (.+?) ([+-]\$[\d.,]+ [BMT]) ([+-][\d.]+ ?%)$")
VALUE_LINE = re.compile(rf"^({MONEY}) ({MONEY}) ({MONEY}) ({MONEY}) ({MONEY}) ({MONEY})$")
YEARS = [2021, 2022, 2023, 2024, 2025]


def get(url, timeout=120, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404 or i == tries - 1:
                raise
        except Exception:  # noqa: BLE001
            if i == tries - 1:
                raise
        time.sleep(10 * (i + 1))


def dollars(t):
    if t == "-":
        return None
    m = re.match(r"\$([\d.,]+) ([BMT])", t)
    return round(float(m.group(1).replace(",", "")) * {"M": 1e6, "B": 1e9, "T": 1e12}[m.group(2)])


def league_tables(pages):
    """{'fossil': {name: row}, 'expansion': {...}} from the report's text."""
    tables = {"fossil": [], "expansion": []}
    section, pending = None, []
    for text in pages:
        if "League Table: Banking on Fossil Fuels" in text:
            section = "fossil"
        elif "League Table: Expansion Financing" in text:
            section = "expansion"
        lines = [l.strip() for l in text.splitlines()]
        names = [NAME_LINE.match(l) for l in lines]
        names = [m for m in names if m]
        values = [VALUE_LINE.match(l) for l in lines]
        values = [m for m in values if m]
        if names and section:
            pending = [(section, m) for m in names]
        elif values and pending:
            if len(values) < len(pending):
                sys.exit(f"bocc: a page has {len(pending)} banks but {len(values)} rows of figures; not guessed")
            for (sec, n), v in zip(pending, values):
                tables[sec].append({"rank": int(n.group(1)), "bank": n.group(2), "change_2024_2025": n.group(3), "change_pct_2024_2025": n.group(4).replace(" ", ""),
                                    **{f"y{y}": v.group(i + 1) for i, y in enumerate(YEARS)}, "total_2021_2025": v.group(6)})
            pending = []
    out = {}
    for sec, rows in tables.items():
        if len(rows) != 65 or sorted(r["rank"] for r in rows) != list(range(1, 66)):
            sys.exit(f"bocc: the {sec} table read as {len(rows)} rows, not the 65 banks; not guessed")
        # Each row's figures belong to its bank if 2025 minus 2024 is the
        # change the report prints beside the bank's name.
        for r in rows:
            a, b = dollars(r["y2025"]) or 0, dollars(r["y2024"]) or 0
            c = r["change_2024_2025"]
            cv = dollars(c[1:]) * (1 if c[0] == "+" else -1)
            if abs((a - b) - cv) > max(0.12e9, abs(cv) * 0.1):
                sys.exit(f"bocc: {sec} table, {r['bank']}: the figures do not match its printed change; not guessed")
        out[sec] = {r["bank"]: r for r in rows}
    return out


def norm(s):
    s = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", s or "")).casefold()
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[\W_]+", "", s)


def gleif_record(lei):
    return json.loads(get(f"https://api.gleif.org/api/v1/lei-records/{lei}", 60))["data"]


def gleif_by_name(name, country):
    """Records whose legal or other name is exactly this name (ignoring case, accents, punctuation)."""
    found = {}
    for field in ("entity.legalName", "entity.names"):
        q = urllib.parse.urlencode({f"filter[{field}]": name, "page[size]": 50})
        try:
            data = json.loads(get(f"https://api.gleif.org/api/v1/lei-records?{q}", 60)).get("data", [])
        except Exception as e:  # noqa: BLE001
            print(f"    GLEIF {field}={name}: {e}", flush=True)
            continue
        for r in data:
            ent = r["attributes"]["entity"]
            names = [ent["legalName"]["name"]] + [o.get("name", "") for o in (ent.get("otherNames") or []) + (ent.get("transliteratedOtherNames") or [])]
            if any(norm(n) == norm(name) for n in names):
                found[r["id"]] = r
        time.sleep(1)
    rows = list(found.values())
    for r in rows:
        r["_why"] = []
    return rows


def choose(rows, country):
    """The main company among exact-name matches: registered in the expected
    country, active, not a branch, LEI issued; then the earliest registered."""
    def key(r):
        a, e = r["attributes"], r["attributes"]["entity"]
        return (
            (e.get("legalAddress") or {}).get("country") != country,
            e.get("status") != "ACTIVE",
            e.get("category") == "BRANCH",
            a.get("registration", {}).get("status") not in ("ISSUED", "PENDING_TRANSFER", "PENDING_ARCHIVAL"),
            a.get("registration", {}).get("initialRegistrationDate") or "9999",
        )
    rows = [r for r in rows if (r["attributes"]["entity"].get("legalAddress") or {}).get("country") == country]
    return sorted(rows, key=key)[0] if rows else None


def address_text(a):
    parts = list(a.get("addressLines") or []) + [a.get("city"), a.get("region"), a.get("postalCode"), a.get("country")]
    return ", ".join(p for p in parts if p)


def geocode(a):
    """(lon, lat, how) for a GLEIF address, or None."""
    tries = [
        ("street", {"street": (a.get("addressLines") or [""])[0], "city": a.get("city") or "", "postalcode": a.get("postalCode") or "",
                    "countrycodes": (a.get("country") or "").lower()}),
        ("address", {"q": address_text(a)}),
        ("city", {"city": a.get("city") or "", "countrycodes": (a.get("country") or "").lower()}),
    ]
    for how, params in tries:
        if not any(v for k, v in params.items() if k != "countrycodes"):
            continue
        q = urllib.parse.urlencode({**{k: v for k, v in params.items() if v}, "format": "jsonv2", "limit": 1})
        try:
            got = json.loads(get(f"https://nominatim.openstreetmap.org/search?{q}", 60))
        except Exception as e:  # noqa: BLE001
            print(f"    OpenStreetMap: {e}", flush=True)
            got = []
        time.sleep(1.2)
        if got:
            return float(got[0]["lon"]), float(got[0]["lat"]), how, got[0].get("display_name")
    return None


def main():
    stamp = OUT / "banks.build.json"
    if stamp.exists() and not os.environ.get("BOCC_REBUILD"):
        print("bocc: already built; BOCC_REBUILD=1 to build again")
        return
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pdfplumber"], check=True)
    import pdfplumber
    print("bocc: reading the report", flush=True)
    pdf_bytes = get(PDF, 300)
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        pages = [pg.extract_text() or "" for pg in pdf.pages]
    tables = league_tables(pages)
    missing = [b for b in tables["fossil"] if b not in PAIRS] + [b for b in PAIRS if b not in tables["fossil"]]
    if missing:
        sys.exit(f"bocc: names in the report and the pairing list differ: {missing}; not guessed")
    feats, build = [], []
    for bank, (lei, names, country) in PAIRS.items():
        print(f"  {bank}", flush=True)
        rec, note = None, ""
        if lei:
            rec, note = gleif_record(lei), "LEI approved 25 September"
        else:
            cands = []
            for nm in names:
                cands = gleif_by_name(nm, country)
                if cands:
                    break
            rec = choose(cands, country)
            note = (f"exact legal name; {len(cands)} register entr{'y' if len(cands) == 1 else 'ies'} with that name"
                    if rec else f"no register entry named {' / '.join(names)} in {country}")
            build_c = [{"lei": c["id"], "legal_name": c["attributes"]["entity"]["legalName"]["name"],
                        "country": (c["attributes"]["entity"].get("legalAddress") or {}).get("country"),
                        "status": c["attributes"]["entity"].get("status"), "category": c["attributes"]["entity"].get("category")} for c in cands]
        f, e = tables["fossil"][bank], tables["expansion"].get(bank)
        props = {"bank": bank, "fossil_fuel_financing_rank_2025": f["rank"]}
        for y in YEARS:
            props[f"fossil_fuel_financing_{y}"] = f[f"y{y}"]
        props.update({"fossil_fuel_financing_total_2021_2025": f["total_2021_2025"], "fossil_fuel_financing_change_2024_2025": f["change_2024_2025"],
                      "fossil_fuel_financing_change_pct_2024_2025": f["change_pct_2024_2025"]})
        if e:
            props["expansion_financing_rank_2025"] = e["rank"]
            for y in YEARS:
                props[f"expansion_financing_{y}"] = e[f"y{y}"]
            props.update({"expansion_financing_total_2021_2025": e["total_2021_2025"], "expansion_financing_change_2024_2025": e["change_2024_2025"],
                          "expansion_financing_change_pct_2024_2025": e["change_pct_2024_2025"]})
        props["fossil_fuel_financing_2025_usd"] = dollars(f["y2025"])
        row = {"bank": bank, "how_paired": note}
        if not lei:
            row["register_entries_found"] = build_c
        if rec:
            ent = rec["attributes"]["entity"]
            hq = ent.get("headquartersAddress") or ent.get("legalAddress") or {}
            props.update({"legal_entity": ent["legalName"]["name"], "lei": rec["id"], "headquarters_address": address_text(hq),
                          "gleif_record": f"https://search.gleif.org/#/record/{rec['id']}"})
            row.update({"lei": rec["id"], "legal_name": ent["legalName"]["name"], "headquarters": address_text(hq)})
            g = geocode(hq)
            if g:
                lon, lat, how, found = g
                props["position"] = {"street": "The headquarters address in the GLEIF register, found in OpenStreetMap.",
                                     "address": "The headquarters address in the GLEIF register, found in OpenStreetMap as a whole address.",
                                     "city": "The headquarters city in the GLEIF register (the street address was not found in OpenStreetMap)."}[how]
                row.update({"placed": how, "openstreetmap_match": found})
                feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props})
            else:
                row["placed"] = False
        else:
            row["placed"] = False
        props["source"] = "Banking on Climate Chaos 2026 (RAN, BankTrack, Indigenous Environmental Network, Oil Change International, Reclaim Finance, Sierra Club, Urgewald and others), league tables pp. 10-13 and 32-35"
        build.append(row)
    OUT.mkdir(exist_ok=True)
    (OUT / "banks.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    stamp.write_text(json.dumps({"report": PDF, "banks": len(PAIRS), "placed": len(feats), "pairing": build}, ensure_ascii=False, indent=1))
    print(f"bocc: {len(feats)} of {len(PAIRS)} banks placed")


if __name__ == "__main__":
    main()
