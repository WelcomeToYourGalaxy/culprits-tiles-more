#!/usr/bin/env python3
"""
Bankrolling Extinction (Portfolio Earth, 2020): the 50 banks, placed at their
headquarters (round 61, 26 September).

  * Which banks, and their printed figures: Table 2 of the report (p. 47),
    each bank's S&P Global rank, country, region and total assets in 2019
    (million USD), as printed.
  * Their amounts: Figure 1 (pp. 10-11, and Figure-1.pdf) prints no number for
    any bank; it draws bars. The owner chose (26 September) to show amounts
    measured from the bars, marked approximate. Each bar's end is read from
    the figure's own drawing and turned into millions of USD on the figure's
    own axis (0 to 250,000, gridlines every 50,000). The long light bar is the
    bank's total loans and underwriting linked to biodiversity risk; the dark
    bar laid over it is the part linked to direct risk (the report's average
    of the long bars, 52 billion USD, and its largest, "more than 210 billion",
    check this). The left half's bars, the same two as a share of total
    assets, are measured the same way. Each measured figure is rounded to the
    nearest billion, and every box says it was measured. Four banks' bars are
    all drawn at one smallest length and have no dark bar; for those the box
    says so and gives the report's own word on the smallest bank (1.3 billion).
  * Which company each bank is: the same Global Legal Entity Identifier
    register (GLEIF) pairings as Banking on Climate Chaos (scripts/bocc.py)
    where the bank is in both reports; for the others, an exact legal name, and
    no fuzzy matching. A bank not found is listed, not placed.
  * Where: the headquarters address the register gives, found in
    OpenStreetMap (Nominatim); if the street is not found, the city.

Portfolio Earth publishes no data file and states no licence; the report is
© Portfolio Earth (the same footing as Banking on Climate Chaos).

Writes pe/banks.geojson and pe/banks.build.json. Built once; PE_REBUILD=1
builds again.
"""
import json, os, pathlib, re, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bocc  # noqa: E402  (its register and OpenStreetMap helpers, and its approved pairings)

FIG = pathlib.Path("probe/pe/bankrolling_extinction_figure1.pdf")
WORDS = pathlib.Path("probe/pe/bankrolling_extinction_figure1.words.json")
REPORT = pathlib.Path("probe/pe/bankrolling_extinction_report.txt")
OUT = pathlib.Path("pe")
REPORT_URL = "https://portfolio.earth/wp-content/uploads/2020/10/Bankrolling-Extinction-Report.pdf"
PAGE = "https://portfolio.earth/campaigns/bankrolling-extinction/"

# Figure 1's labels -> Table 2's names, where they are written differently.
FIG_NAMES = {
    "JP MORGAN CHASE": "JPMorgan Chase",
    "INDUSTRIAL AND COMMERCIAL BANK": "Industrial and Commercial Bank of China",
    "BANCO BILBAO VIZCAYA ARGENTARIA": "Banco Bilbao Vizcaya Argentaria (BBVA)",
    "OVERSEA-CHINESE BANKING": "Oversea-Chinese Banking Corporation",
    "MALAYSIAN BANKING": "Malayan Banking",
    "SHIN FINANCIAL GROUP": "Shinhan Financial Group",
}
# Table 2's names -> Banking on Climate Chaos's names, where the bank is in both.
BOCC_NAMES = {
    "BPCE Group": "Groupe BPCE",
    "Crédit Mutuel CIC Group": "Crédit Mutuel",
}
# Banks not in Banking on Climate Chaos: exact legal names to look for in the
# register, and the country it should be registered in.
OTHERS = {
    "Norinchukin Bank": (["The Norinchukin Bank"], "JP"),
    "Credit Suisse": (["Credit Suisse Group AG"], "CH"),
    "Sberbank": (["Sberbank of Russia", "PUBLIC JOINT STOCK COMPANY SBERBANK OF RUSSIA"], "RU"),
    "Shinhan Financial Group": (["Shinhan Financial Group Co., Ltd."], "KR"),
    "Oversea-Chinese Banking Corporation": (["Oversea-Chinese Banking Corporation Limited"], "SG"),
    "Banco do Brasil": (["Banco do Brasil S.A.", "BANCO DO BRASIL SA"], "BR"),
    "Bradesco": (["Banco Bradesco S.A.", "BANCO BRADESCO SA"], "BR"),
    "HDFC Bank": (["HDFC Bank Limited"], "IN"),
    "Malayan Banking": (["Malayan Banking Berhad"], "MY"),
    "Standard Bank": (["Standard Bank Group Limited"], "ZA"),
    "CIMB Group": (["CIMB Group Holdings Berhad"], "MY"),
    "FirstRand": (["FirstRand Limited"], "ZA"),
    "Bank Mandiri": (["PT Bank Mandiri (Persero) Tbk", "PT BANK MANDIRI (PERSERO) TBK."], "ID"),
}
COUNTRY = {"China": "CN", "Japan": "JP", "UK": "GB", "USA": "US", "France": "FR", "Spain": "ES", "Germany": "DE", "Canada": "CA",
           "Italy": "IT", "Netherlands": "NL", "Switzerland": "CH", "Singapore": "SG", "Australia": "AU", "India": "IN", "Russia": "RU",
           "South Korea": "KR", "Brazil": "BR", "Malaysia": "MY", "South Africa": "ZA", "Indonesia": "ID"}


def table2():
    t = REPORT.read_text(encoding="utf-8")
    i = t.index("S& P GLOBAL BANK BANK COUNTRY REGION")
    seg = t[i - 3000:i + 8000]
    pat = re.compile(r"(\d{1,3}|na) ([A-Z][A-Za-z&\-\.\(\)' éÉè]+?) (" + "|".join(re.escape(c) for c in sorted(COUNTRY, key=len, reverse=True)) +
                     r") (Asia & Pacific|Europe|North America|South America|Africa) ([\d,]{5,})")
    rows = {}
    for rank, name, country, region, assets in pat.findall(seg):
        rows[name] = {"sp_global_rank": rank, "country": country, "region": region, "total_assets_2019_million_usd": int(assets.replace(",", ""))}
    if len(rows) != 50:
        sys.exit(f"pe_banks: Table 2 read as {len(rows)} banks, not 50; nothing is guessed")
    return rows


def figure1():
    """Each bank's bars, measured from the figure's drawing."""
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pymupdf"], check=True)
    import pymupdf
    page = pymupdf.open(FIG)[0]
    words = json.loads(WORDS.read_text())[0]["words"]
    fills, grid = [], []
    for d in page.get_drawings():
        r = d["rect"]
        if d["type"] == "s" and abs(r.x1 - r.x0) < 0.5:
            grid.append(round(r.x0, 2))
        if d["type"] == "f" and d["fill"] and r.y0 > 100:
            fills.append((r.y0, r.y1, r.x0, r.x1, "light" if d["fill"][0] > 0.45 else "dark"))
    grid = sorted(set(grid))
    right = [g for g in grid if g > 640]      # 0 (the axis line), 50,000 ... 250,000
    left = [g for g in grid if g < 640]       # 12%, 10% ... 2%, 0% (the axis line)
    # Units from the evenly spaced gridlines, 50,000 apart on the right and 2
    # per cent apart on the left; the bars start at the axis line itself.
    per_m = (right[-1] - right[2]) / 150000.0           # points per million USD
    per_pc = (left[4] - left[1]) / 6.0                  # points per percentage point
    names = {}
    for w, x0, y0, x1, y1 in words:
        if 530 < x0 < 660 and y0 > 110:
            names.setdefault(round(y0, 1), []).append((x0, w))
    out = []
    for y, ws in sorted(names.items()):
        label = " ".join(w for _, w in sorted(ws))
        here = [f for f in fills if f[0] - 6 < y < f[1]]
        r_light = [f for f in here if f[4] == "light" and f[2] > 600]
        r_dark = [f for f in here if f[4] == "dark" and f[2] > 600]
        l_light = [f for f in here if f[4] == "light" and f[3] < 600]
        l_dark = [f for f in here if f[4] == "dark" and f[3] < 600]
        m = lambda b: (b[0][3] - b[0][2]) / per_m if b else None
        pc = lambda b: (b[0][3] - b[0][2]) / per_pc if b else None
        out.append({"label": label, "total": m(r_light), "direct": m(r_dark), "total_pc": pc(l_light), "direct_pc": pc(l_dark),
                    "light_end": r_light[0][3] if r_light else None})
    if len(out) != 50:
        sys.exit(f"pe_banks: Figure 1 read as {len(out)} banks, not 50; nothing is guessed")
    return out, {"points_per_million_usd": per_m, "points_per_percent": per_pc}


def billions(m):
    return None if m is None else round(m / 1000.0)


def main():
    stamp = OUT / "banks.build.json"
    if stamp.exists() and not os.environ.get("PE_REBUILD"):
        print("pe_banks: already built; PE_REBUILD=1 to build again")
        return
    t2 = table2()
    fig, scale = figure1()
    smallest = min(f["light_end"] for f in fig)
    at_floor = [f["label"] for f in fig if abs(f["light_end"] - smallest) < 0.01]
    mean = sum(f["total"] for f in fig) / len(fig)
    print(f"  Figure 1: largest {fig[0]['total']:,.0f}, average {mean:,.0f} million USD "
          f"(the report: more than 210 billion, 52 billion); {len(at_floor)} bars at the smallest length", flush=True)
    feats, build = [], []
    for rank_in_figure, f in enumerate(fig, 1):
        name = FIG_NAMES.get(f["label"]) or next((n for n in t2 if n.upper() == f["label"]), None)
        if not name or name not in t2:
            sys.exit(f"pe_banks: Figure 1's {f['label']} is not in Table 2; nothing is guessed")
        row = t2[name]
        props = {"bank": name, "rank_in_figure_1": rank_in_figure, **row}
        floor = f["label"] in at_floor and not f["direct"]
        if floor:
            props["finance_linked_to_biodiversity_risk_2019"] = ("Drawn at the figure's smallest bar length, shared by "
                f"{len(at_floor)} banks, with no direct part drawn: the report says the smallest bank's figure is 1.3 billion USD")
        else:
            props["finance_linked_to_biodiversity_risk_2019_billion_usd_approx"] = billions(f["total"])
            if f["direct"]:
                props["of_which_direct_risk_billion_usd_approx"] = billions(f["direct"])
                props["of_which_indirect_risk_billion_usd_approx"] = billions(f["total"] - f["direct"])
            if f["total_pc"]:
                props["as_share_of_total_assets_percent_approx"] = round(f["total_pc"], 1)
            if f["direct_pc"]:
                props["direct_as_share_of_total_assets_percent_approx"] = round(f["direct_pc"], 1)
        props["how_measured"] = ("Figure 1 prints no numbers. The amounts are measured from the length of the bank's bars in the "
                                 "figure, on its own axis, rounded to the nearest billion (percentages to 0.1); approximate.")
        # Which company: Banking on Climate Chaos's approved pairing, or an exact legal name.
        b_name = BOCC_NAMES.get(name, name)
        cands, rec, note = [], None, ""
        if b_name in bocc.PAIRS:
            lei, names, country = bocc.PAIRS[b_name]
            if lei:
                rec, note = bocc.gleif_record(lei), "LEI as approved for Banking on Climate Chaos, 25 September"
            else:
                for nm in names:
                    cands = bocc.gleif_by_name(nm, country)
                    if cands:
                        break
                rec = bocc.choose(cands, country)
                note = "exact legal name as approved for Banking on Climate Chaos, 25 September" if rec else f"no register entry named {' / '.join(names)}"
        elif name in OTHERS:
            names, country = OTHERS[name]
            for nm in names:
                cands = bocc.gleif_by_name(nm, country)
                if cands:
                    break
            rec = bocc.choose(cands, country)
            note = (f"exact legal name; {len(cands)} register entr{'y' if len(cands) == 1 else 'ies'} with that name"
                    if rec else f"no register entry named {' / '.join(names)} in {country}")
        b = {"bank": name, "figure_1_label": f["label"], "how_paired": note, "measured_million_usd": {k: f[k] for k in ("total", "direct")}}
        if cands:
            b["register_entries_found"] = [{"lei": c["id"], "legal_name": c["attributes"]["entity"]["legalName"]["name"],
                                            "status": c["attributes"]["entity"].get("status")} for c in cands]
        if rec:
            ent = rec["attributes"]["entity"]
            hq = ent.get("headquartersAddress") or ent.get("legalAddress") or {}
            props.update({"legal_entity": ent["legalName"]["name"], "lei": rec["id"], "headquarters_address": bocc.address_text(hq),
                          "gleif_record": f"https://search.gleif.org/#/record/{rec['id']}"})
            g = bocc.geocode(hq)
            if g:
                lon, lat, how, found = g
                props["position"] = {"street": "The headquarters address in the GLEIF register, found in OpenStreetMap.",
                                     "address": "The headquarters address in the GLEIF register, found in OpenStreetMap as a whole address.",
                                     "city": "The headquarters city in the GLEIF register (the street address was not found in OpenStreetMap)."}[how]
                b.update({"placed": how, "openstreetmap_match": found})
                props["source"] = f"Bankrolling Extinction (Portfolio Earth, 2020), Table 2 and Figure 1; {PAGE}"
                feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props})
            else:
                b["placed"] = False
        else:
            b["placed"] = False
        build.append(b)
        print(f"  {name}: {'placed' if b.get('placed') else 'not placed'}", flush=True)
    OUT.mkdir(exist_ok=True)
    (OUT / "banks.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    stamp.write_text(json.dumps({"report": REPORT_URL, "banks": len(fig), "placed": len(feats), "scale": scale,
                                 "checks": {"largest_million_usd": fig[0]["total"], "average_million_usd": mean,
                                            "report_says": "more than 210 billion for the largest; 52 billion on average; 1.3 billion the smallest",
                                            "bars_at_smallest_length": at_floor},
                                 "pairing": build}, ensure_ascii=False, indent=1))
    print(f"pe_banks: {len(feats)} of {len(fig)} banks placed")


if __name__ == "__main__":
    main()
