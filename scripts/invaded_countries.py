#!/usr/bin/env python3
"""
How each country is being invaded, beyond settler colonialism (round 73,
asked 27 September). The Culprits map's settler colonialism layer covers the
countries its source map names; the owner asked for every other country too,
with four kinds of invasion, and for the same facts to be added to the settler
layer's own descriptions. Every fact here is read from a published source and
carries its link; nothing is written in by hand except the three short lists
at the top, each of which names the page it comes from.

Writes
  invaded/countries.json          every country's facts, by ISO3 code (the
                                  settler layer's boxes read these too)
  shapes/other_invaded.geojson    the countries the settler layer does not
                                  draw whole, with figures to shade them by

1. Indigenous peoples' situation
   LandMark (landmarkmap.org, through Global Forest Watch's open tiles): the
   share of each country's land held by Indigenous Peoples and communities,
   formally acknowledged or not, and the Indigenous share of its population,
   with the peoples LandMark names. ILO Convention 169: whether the country
   has ratified it (ILO NORMLEX). The UN Declaration on the Rights of
   Indigenous Peoples: how the country voted in 2007 (UN A/61/PV.107).
   IWGIA's Indigenous World: a link to the country's chapter where IWGIA
   has a country page (checked on each run).
2. Colonial rule still in place
   The UN's list of Non-Self-Governing Territories and their administering
   powers; dependent territories and the state that holds them (Wikidata).
3. Economic invasion
   Land deals of 200 ha or more since 2000 (the Land Matrix, as harvested
   weekly by the culprits repo); external debt as a share of national income
   (World Bank, International Debt Statistics), latest year.
4. Past conquest, still standing
   The Correlates of War Territorial Change data (v6, 1816-2018): every
   territory a state took by conquest or annexation, and every one it lost
   that way, with year, the other side and area. Citation required: Tir,
   Schafer, Diehl and Goertz (1998), Conflict Management and Peace Science
   16:89-97. The dataset ends in 2018. A whole territory is followed to its
   next change of hands, if COW records one; a piece of a state's land cannot
   be followed (pieces of one state share its number), so the box says so.

Each part keeps its last copy if its source does not answer.
"""
import csv, gzip, io, json, math, pathlib, re, subprocess, sys, time, urllib.parse, urllib.request, zipfile

UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas daily copy; welcometoyourgalaxy@gmail.com)", "Accept-Encoding": "identity"}
OUT = pathlib.Path("invaded")
SHAPES = pathlib.Path("shapes")
CULPRITS_RAW = "https://raw.githubusercontent.com/WelcomeToYourGalaxy/culprits/main/"
GFW_API = "https://data-api.globalforestwatch.org"

# ILO Convention No. 169 (Indigenous and Tribal Peoples), the 24 ratifying
# states as NORMLEX lists them.
ILO169_URL = "https://normlex.ilo.org/dyn/nrmlx_en/f?p=NORMLEXPUB:11300:0::NO::P11300_INSTRUMENT_ID:312314"
ILO169 = ["ARG", "BOL", "BRA", "CAF", "CHL", "COL", "CRI", "DNK", "DMA", "ECU", "FJI", "DEU", "GTM", "HND", "LUX",
          "MEX", "NPL", "NLD", "NIC", "NOR", "PRY", "PER", "ESP", "VEN"]
# The General Assembly's vote adopting the Declaration, 13 September 2007
# (A/61/PV.107): 143 for, 4 against, 11 abstaining. All four against later
# said they support it (Australia 2009, New Zealand 2010, Canada 2010, the
# United States 2010), as did Colombia and Samoa of those abstaining.
UNDRIP_URL = "https://www.un.org/development/desa/indigenouspeoples/declaration-on-the-rights-of-indigenous-peoples.html"
UNDRIP_AGAINST = {"AUS": 2009, "CAN": 2010, "NZL": 2010, "USA": 2010}
UNDRIP_ABSTAINED = {"AZE": None, "BGD": None, "BTN": None, "BDI": None, "COL": 2009, "GEO": None, "KEN": None,
                    "NGA": None, "RUS": None, "WSM": 2007, "UKR": None}
# The UN's Non-Self-Governing Territories and their administering powers.
NSGT_URL = "https://www.un.org/dppa/decolonization/en/nsgt"
NSGT = {"ESH": None, "AIA": "GBR", "BMU": "GBR", "VGB": "GBR", "CYM": "GBR", "FLK": "GBR", "MSR": "GBR", "SHN": "GBR",
        "TCA": "GBR", "VIR": "USA", "GIB": "GBR", "ASM": "USA", "PYF": "FRA", "GUM": "USA", "NCL": "FRA", "PCN": "GBR",
        "TKL": "NZL"}
# Names for the listed territories the national outlines do not carry.
EXTRA_NAMES = {"GIB": "Gibraltar", "PCN": "Pitcairn", "TKL": "Tokelau", "ESH": "Western Sahara", "SHN": "Saint Helena",
               "BMU": "Bermuda", "CYM": "Cayman Islands", "TCA": "Turks and Caicos Islands", "VGB": "British Virgin Islands",
               "AIA": "Anguilla", "MSR": "Montserrat", "FLK": "Falkland Islands (Malvinas)"}
COW_ZIP = "https://correlatesofwar.org/wp-content/uploads/terr-changes-v6.zip"
COW_MIRROR = "https://raw.githubusercontent.com/jenna-jordan/correlates-of-war/main/data/raw/tc2018.csv"
COW_ENTITIES = "https://raw.githubusercontent.com/jenna-jordan/correlates-of-war/main/data/processed/tc_entities.csv"
COW_STATES = "https://correlatesofwar.org/wp-content/uploads/COW-country-codes.csv"
# Correlates of War state numbers for today's states (COW's state system
# list), to ISO3. A state that no longer exists and has no single successor
# (Hanover, Bavaria, the Papal States, the two Sicilies, the Transvaal, South
# Vietnam and others) is left out rather than given to a modern country;
# Austria-Hungary (300) and Czechoslovakia (315) are given to Austria and the
# Czech Republic, the states COW continues their numbers into.
COW_ISO3 = {2: "USA", 20: "CAN", 31: "BHS", 40: "CUB", 41: "HTI", 42: "DOM", 51: "JAM", 52: "TTO", 53: "BRB", 54: "DMA", 55: "GRD", 56: "LCA", 57: "VCT", 58: "ATG", 60: "KNA", 70: "MEX", 80: "BLZ", 90: "GTM", 91: "HND", 92: "SLV", 93: "NIC", 94: "CRI", 95: "PAN", 100: "COL", 101: "VEN", 110: "GUY", 115: "SUR", 130: "ECU", 135: "PER", 140: "BRA", 145: "BOL", 150: "PRY", 155: "CHL", 160: "ARG", 165: "URY", 200: "GBR", 205: "IRL", 210: "NLD", 211: "BEL", 212: "LUX", 220: "FRA", 221: "MCO", 223: "LIE", 225: "CHE", 230: "ESP", 232: "AND", 235: "PRT", 255: "DEU", 260: "DEU", 290: "POL", 300: "AUT", 305: "AUT", 310: "HUN", 315: "CZE", 316: "CZE", 317: "SVK", 325: "ITA", 331: "SMR", 338: "MLT", 339: "ALB", 341: "MNE", 343: "MKD", 344: "HRV", 345: "SRB", 346: "BIH", 349: "SVN", 350: "GRC", 352: "CYP", 355: "BGR", 359: "MDA", 360: "ROU", 365: "RUS", 366: "EST", 367: "LVA", 368: "LTU", 369: "UKR", 370: "BLR", 371: "ARM", 372: "GEO", 373: "AZE", 375: "FIN", 380: "SWE", 385: "NOR", 390: "DNK", 395: "ISL", 402: "CPV", 403: "STP", 404: "GNB", 411: "GNQ", 420: "GMB", 432: "MLI", 433: "SEN", 434: "BEN", 435: "MRT", 436: "NER", 437: "CIV", 438: "GIN", 439: "BFA", 450: "LBR", 451: "SLE", 452: "GHA", 461: "TGO", 471: "CMR", 475: "NGA", 481: "GAB", 482: "CAF", 483: "TCD", 484: "COG", 490: "COD", 500: "UGA", 501: "KEN", 510: "TZA", 516: "BDI", 517: "RWA", 520: "SOM", 522: "DJI", 530: "ETH", 531: "ERI", 540: "AGO", 541: "MOZ", 551: "ZMB", 552: "ZWE", 553: "MWI", 560: "ZAF", 565: "NAM", 570: "LSO", 571: "BWA", 572: "SWZ", 580: "MDG", 581: "COM", 590: "MUS", 591: "SYC", 600: "MAR", 615: "DZA", 616: "TUN", 620: "LBY", 625: "SDN", 626: "SSD", 630: "IRN", 640: "TUR", 645: "IRQ", 651: "EGY", 652: "SYR", 660: "LBN", 663: "JOR", 666: "ISR", 670: "SAU", 678: "YEM", 679: "YEM", 690: "KWT", 692: "BHR", 694: "QAT", 696: "ARE", 698: "OMN", 700: "AFG", 701: "TKM", 702: "TJK", 703: "KGZ", 704: "UZB", 705: "KAZ", 710: "CHN", 712: "MNG", 713: "TWN", 731: "PRK", 732: "KOR", 740: "JPN", 750: "IND", 760: "BTN", 770: "PAK", 771: "BGD", 775: "MMR", 780: "LKA", 781: "MDV", 790: "NPL", 800: "THA", 811: "KHM", 812: "LAO", 816: "VNM", 820: "MYS", 830: "SGP", 835: "BRN", 840: "PHL", 850: "IDN", 860: "TLS", 900: "AUS", 910: "PNG", 920: "NZL", 935: "VUT", 940: "SLB", 946: "KIR", 947: "TUV", 950: "FJI", 955: "TON", 970: "NRU", 983: "MHL", 986: "PLW", 987: "FSM", 990: "WSM"}
PROCEDURE = {1: "conquest", 2: "annexation", 3: "cession", 4: "secession", 5: "unification", 6: "mandated territory"}


def get(url, tries=3, timeout=120, data=None, headers=None):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=dict(UA, **(headers or {})), data=data)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"  {url}: {e}; again in {10 * (i + 1)}s", flush=True)
            time.sleep(10 * (i + 1))


def jget(url, **kw):
    return json.loads(get(url, **kw).decode("utf-8"))


def pip(*names):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *names], check=False)


def last_copy():
    p = OUT / "countries.json"
    return json.loads(p.read_text()) if p.exists() else {}


def part(name, fn, keep):
    """Run one source; on failure keep what the last run had for it."""
    try:
        got = fn()
        print(f"  ok    {name}: {len(got)} countries", flush=True)
        return got, True
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL  {name}: {e}; its last copy is kept", flush=True)
        return {iso: c[name] for iso, c in keep.items() if name in c}, False


# ------------------------------------------------------------------ LandMark
def landmark():
    pip("mapbox-vector-tile")
    import mapbox_vector_tile  # noqa: E402
    out = {}
    for ds, keep in (("landmark_percent_of_land_indigenous_per_country",
                      ["country", "ctry_land", "ic_t", "ic_t_ha", "ic_t_cat", "ic_t_src", "ic_f", "ic_f_ha", "ic_nf", "ic_nf_ha", "ic_notes", "more_info"]),
                     ("landmark_indigenous_population_per_country",
                      ["country", "pop", "pct", "pctcat", "popcat", "peoples", "sources", "note"])):
        ver = jget(f"{GFW_API}/dataset/{ds}/latest")["data"]["version"]
        assets = jget(f"{GFW_API}/dataset/{ds}/{ver}/assets")["data"]
        tile = next((a["asset_uri"] for a in assets if a.get("asset_type") == "Static vector tile cache"), None)
        if not tile:
            raise RuntimeError(f"{ds} {ver}: no vector tiles listed")
        seen = {}
        for z, x, y in [(0, 0, 0), (1, 0, 0), (1, 1, 0), (1, 0, 1), (1, 1, 1)]:
            try:
                raw = get(tile.replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y)))
            except Exception as e:  # noqa: BLE001
                print(f"    {ds} {z}/{x}/{y}: {e}")
                continue
            # Global Forest Watch's tiles come gzipped (round 80: "Error parsing
            # message with type 'vector_tile.tile'"); an empty square is skipped.
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            if not raw:
                continue
            try:
                layers = mapbox_vector_tile.decode(raw)
            except Exception as e:  # noqa: BLE001
                print(f"    {ds} {z}/{x}/{y}: {e}")
                continue
            for layer in layers.values():
                for f in layer.get("features", []):
                    p = f.get("properties") or {}
                    iso = str(p.get("iso_code") or "").upper()
                    if len(iso) == 3:
                        seen.setdefault(iso, {k: p.get(k) for k in keep if p.get(k) not in (None, "")})
        key = "land" if "land" in ds else "population"
        for iso, v in seen.items():
            out.setdefault(iso, {})[key] = dict(v, dataset=ds, version=ver)
    if not out:
        raise RuntimeError("no country read from the tiles")
    return out


# ---------------------------------------------------------------- IWGIA pages
def iwgia(names):
    out = {}
    for iso, name in names.items():
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        url = f"https://www.iwgia.org/en/{slug}.html"
        try:
            req = urllib.request.Request(url, headers=UA, method="HEAD")
            with urllib.request.urlopen(req, timeout=20) as r:
                if r.status == 200:
                    out[iso] = {"url": url}
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.3)
    if not out:
        raise RuntimeError("no IWGIA country page answered")
    return out


# ------------------------------------------------------------ dependencies
def dependencies():
    q = """SELECT DISTINCT ?t ?tLabel ?iso ?sov ?sovLabel ?sovIso WHERE {
  ?t wdt:P31/wdt:P279* wd:Q161243 .
  ?t wdt:P298 ?iso .
  FILTER NOT EXISTS { ?t wdt:P576 [] }
  OPTIONAL { ?t wdt:P17 ?sov . OPTIONAL { ?sov wdt:P298 ?sovIso } }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}"""
    url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(q)
    rows = jget(url, headers={"Accept": "application/sparql-results+json"})["results"]["bindings"]
    out = {}
    for r in rows:
        iso = r["iso"]["value"].upper()
        sov = r.get("sovIso", {}).get("value", "").upper()
        if not sov or sov == iso:
            continue
        d = out.setdefault(iso, {"held_by": [], "wikidata": r["t"]["value"]})
        if sov not in [h["iso3"] for h in d["held_by"]]:
            d["held_by"].append({"iso3": sov, "name": r.get("sovLabel", {}).get("value", sov)})
    if not out:
        raise RuntimeError("Wikidata returned no dependent territories")
    return out


# ----------------------------------------------------------------- economic
def land_deals():
    d = jget(CULPRITS_RAW + "map/data/land_matrix.countries.json")
    out = {}
    for iso, r in d.items():
        out[iso] = {"hectares": r.get("value"), "deals": r.get("x_deals"), "investor_countries": r.get("x_investor_countries"),
                    "crops": r.get("x_crops"), "url": "https://landmatrix.org/list/deals",
                    "licence": r.get("licence")}
    return out


def debt():
    url = "https://api.worldbank.org/v2/country/all/indicator/DT.DOD.DECT.GN.ZS?format=json&per_page=20000&mrv=1"
    j = jget(url)
    out = {}
    for r in j[1] or []:
        iso = r.get("countryiso3code")
        if iso and r.get("value") is not None and len(iso) == 3:
            out[iso] = {"external_debt_pct_gni": round(r["value"], 1), "year": int(r["date"]),
                        "url": f"https://data.worldbank.org/indicator/DT.DOD.DECT.GN.ZS?locations={iso}"}
    if not out:
        raise RuntimeError("the World Bank returned no values")
    return out


# ------------------------------------------------------------------ conquest
NAMES_BY_ISO = {}


def conquest():
    try:
        z = zipfile.ZipFile(io.BytesIO(get(COW_ZIP)))
        name = next(n for n in z.namelist() if n.lower().endswith("tc2018.csv"))
        text = z.read(name).decode("latin-1")
        src = COW_ZIP
    except Exception as e:  # noqa: BLE001
        print(f"    COW's own file did not answer ({e}); reading the copy in jenna-jordan/correlates-of-war")
        text = get(COW_MIRROR).decode("latin-1")
        src = COW_MIRROR
    rows = list(csv.DictReader(io.StringIO(text)))
    # An entity's name at the time: the entity list gives each number one row
    # per period, and a number can carry different names in different periods.
    spans = {}
    for r in csv.DictReader(io.StringIO(get(COW_ENTITIES).decode("utf-8"))):
        spans.setdefault(r["id"], []).append(r)

    class Names(dict):
        def at(self, code, year=None):
            rs = spans.get(str(code))
            if not rs:
                return None
            if year is not None:
                for r in rs:
                    try:
                        if int(r["start_year"]) <= year <= int(r["end_year"]):
                            return r["name"]
                    except ValueError:
                        pass
                near = min(rs, key=lambda r: min(abs(int(r["start_year"] or 0) - year), abs(int(r["end_year"] or 0) - year)))
                return near["name"]
            return rs[0]["name"]

        def get(self, code, default=None):
            return self.at(code) or default
    ents = Names()

    def iso(code):
        try:
            return COW_ISO3.get(int(code))
        except (TypeError, ValueError):
            return None

    def name_of(code, year=None):
        if str(code) in ("-9", "0", "1", ""):
            return "a people or polity outside the state system (COW codes it -9)" if str(code) == "-9" else f"COW code {code}"
        return ents.at(code, year) or NAMES_BY_ISO.get(iso(code)) or f"COW state {code}"

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    out = {}
    events = []
    for r in rows:
        try:
            proc = int(r["procedur"])
        except (TypeError, ValueError):
            continue
        if proc not in (1, 2):
            continue
        g, l = r["gainer"], r["loser"]
        events.append((int(r["year"]), g, l, r["entity"], r))
    for year, g, l, ent, r in events:
        # Passed on: a later change of the same territory away from the side
        # that took it, to anyone.
        # Only a whole unit can be followed: pieces of one state share its number.
        later = [x for x in rows if r.get("portion") == "1" and str(x.get("year", "")).lstrip("-").isdigit()
                 and int(x["year"]) > year and x["entity"] == ent and x["loser"] == g]
        nxt = min(later, key=lambda x: int(x["year"])) if later else None
        whole = r.get("portion") == "1"
        tname = ents.at(ent, year) or f"COW entity {ent}"
        # COW names a piece of a state's own land by that state's number: a
        # piece taken from the loser is "part of" it; a piece coded with the
        # gainer's number is land joined to the gainer's homeland, unnamed.
        terr = (tname if whole or ent not in (g, l)
                else f"part of {tname}" if ent == l else "land joined to its homeland (COW gives the piece no name)")
        item = {"year": year, "territory": terr, "whole_unit": whole, "procedure": PROCEDURE[int(r["procedur"])],
                "area_km2": num(r.get("area")) if num(r.get("area")) and num(r.get("area")) > 0 else None,
                "armed_conflict": r.get("conflict") == "1",
                "passed_on": {"year": int(nxt["year"]), "to": name_of(nxt["gainer"], int(nxt["year"]))} if nxt else None}
        gi, li = iso(g), iso(l)
        other = name_of
        if gi:
            out.setdefault(gi, {"gained": [], "lost": [], "source": src})["gained"].append(dict(item, other=other(l, year), other_iso3=li))
        if li:
            out.setdefault(li, {"gained": [], "lost": [], "source": src})["lost"].append(dict(item, other=other(g, year), other_iso3=gi))
    for v in out.values():
        v["gained"].sort(key=lambda x: x["year"])
        v["lost"].sort(key=lambda x: x["year"])
    if not out:
        raise RuntimeError("no conquest or annexation read")
    return out


# --------------------------------------------------------------------- main
def main():
    OUT.mkdir(exist_ok=True)
    SHAPES.mkdir(exist_ok=True)
    keep = last_copy()
    bounds = jget(CULPRITS_RAW + "map/data/boundaries.geojson")["features"]
    names = {}
    for f in bounds:
        iso = f["properties"].get("iso3")
        if iso and len(iso) == 3 and iso.isalpha():
            names.setdefault(iso, f["properties"]["name"])
    for k, v in EXTRA_NAMES.items():
        names.setdefault(k, v)
    NAMES_BY_ISO.update(names)
    # Countries the settler layer draws whole.
    whole = set()
    try:
        juris = jget(CULPRITS_RAW + "pipeline/shapes/jurisdictions/site_settler_colonialism.json")["entries"]
        for e in juris.values():
            ps = e["parts"]
            if len(ps) == 1 and "adm0" in ps[0] and not ps[0].get("clip"):
                whole.add(ps[0]["adm0"])
    except Exception as e:  # noqa: BLE001
        print(f"  the settler layer's list did not answer ({e}); every country is drawn")

    lm, _ = part("landmark", landmark, keep)
    iw, _ = part("iwgia", lambda: iwgia(names), keep)
    dep, _ = part("dependencies", dependencies, keep)
    ld, _ = part("land_deals", land_deals, keep)
    db, _ = part("debt", debt, keep)
    cq, _ = part("conquest", conquest, keep)

    holds = {}
    for t, d in dep.items():
        for h in d.get("held_by", []):
            holds.setdefault(h["iso3"], []).append(t)
    for t, admin in NSGT.items():
        if admin:
            holds.setdefault(admin, [])
            if t not in holds[admin]:
                holds[admin].append(t)

    countries = {}
    for iso in sorted(set(names) | set(dep) | set(NSGT)):
        c = {"name": names.get(iso, iso)}
        ind = {}
        if iso in lm:
            ind["landmark"] = lm[iso]
        ind["ilo169"] = {"ratified": iso in ILO169, "url": ILO169_URL}
        if iso in UNDRIP_AGAINST:
            ind["undrip"] = {"vote_2007": "against", "later_supported": UNDRIP_AGAINST[iso], "url": UNDRIP_URL}
        elif iso in UNDRIP_ABSTAINED:
            ind["undrip"] = {"vote_2007": "abstained", "later_supported": UNDRIP_ABSTAINED[iso], "url": UNDRIP_URL}
        if iso in iw:
            ind["iwgia"] = iw[iso]
        c["landmark"] = lm.get(iso)
        c["indigenous"] = ind
        col = {}
        if iso in NSGT:
            col["nsgt"] = {"administering": NSGT[iso], "administering_name": names.get(NSGT[iso]) if NSGT[iso] else None, "url": NSGT_URL}
        if iso in dep:
            col["dependency_of"] = dep[iso]["held_by"]
            col["wikidata"] = dep[iso]["wikidata"]
        if iso in holds:
            col["holds"] = [{"iso3": t, "name": names.get(t, t), "nsgt": t in NSGT} for t in sorted(holds[iso])]
        c["colonial"] = col
        eco = {}
        if iso in ld:
            eco["land_deals"] = ld[iso]
        if iso in db:
            eco["debt"] = db[iso]
        c["economic"] = eco
        if iso in cq:
            c["conquest"] = cq[iso]
        c.pop("landmark", None)
        countries[iso] = c
    (OUT / "countries.json").write_text(json.dumps(countries, ensure_ascii=False, separators=(",", ":")))

    def pct(v):
        try:
            return float(str(v).replace("%", "").strip())
        except (TypeError, ValueError):
            return None

    feats = []
    for f in bounds:
        iso = f["properties"].get("iso3")
        if not iso or len(iso) != 3 or not iso.isalpha() or iso in whole or iso == "ATA":
            continue
        c = countries.get(iso, {})
        ind, col, eco, cq_ = c.get("indigenous", {}), c.get("colonial", {}), c.get("economic", {}), c.get("conquest") or {}
        lmd = ind.get("landmark") or {}
        status = ("A Non-Self-Governing Territory (UN list)" if "nsgt" in col
                  else "A dependency of another state" if "dependency_of" in col
                  else "Holds territories of its own" if "holds" in col else "none recorded")
        p = {"iso3": iso, "name": c.get("name", iso),
             "ind_land_pct": pct((lmd.get("land") or {}).get("ic_t")),
             "ind_pop_pct": pct((lmd.get("population") or {}).get("pct")),
             "ilo169": "ratified" if ind.get("ilo169", {}).get("ratified") else "not ratified",
             "colonial": status,
             "land_deal_ha": (eco.get("land_deals") or {}).get("hectares"),
             "debt_pct_gni": (eco.get("debt") or {}).get("external_debt_pct_gni"),
             "conquests_made": len(cq_.get("gained", [])) or None,
             "conquests_suffered": len(cq_.get("lost", [])) or None}
        feats.append({"type": "Feature", "properties": {k: v for k, v in p.items() if v is not None}, "geometry": f["geometry"]})
    (SHAPES / "other_invaded.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, separators=(",", ":")))
    print(f"invaded: {len(countries)} countries' facts; {len(feats)} countries drawn ({len(whole)} left to the settler layer)")


if __name__ == "__main__":
    main()
