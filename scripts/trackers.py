#!/usr/bin/env python3
"""
Two trackers drawn on the map in place of CFR's (round 63, 26 September).
CFR's Terms of Use do not allow its tracker data to be reproduced for a public
purpose; the same kinds of figures come from their primary sources, whose
terms do:

  Central bank policy rates: the Bank for International Settlements,
  WS_CBPOL (monthly), from its bulk file on data.bis.org. BIS terms
  (bis.org/terms_statistics.htm): the statistics may be reproduced if the BIS
  is cited as the source. Saved to trackers/policy_rates.json: every monthly
  value of every central bank, as published. The euro area's rate (XM) is
  also given to each member for the months it had the euro (the dates it
  joined are listed below), marked as the euro area's.

  Current account balances: the International Monetary Fund's DataMapper
  (World Economic Outlook): BCA_NGDPD (% of GDP) and BCA (billions of US
  dollars), every year it gives, its own projections included. IMF terms
  (imf.org/external/terms.htm): free to reproduce and publish, with
  "Source: International Monetary Fund". Saved to trackers/imbalances.json.

Runs daily; each part keeps its last good copy if its source does not answer.
"""
import csv, io, json, pathlib, re, sys, time, urllib.request, zipfile

UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas daily copy; welcometoyourgalaxy@gmail.com)", "Accept-Encoding": "identity"}
OUT = pathlib.Path("trackers")
BIS = ["https://data.bis.org/static/bulk/WS_CBPOL_csv_flat.zip", "https://data.bis.org/static/bulk/WS_CBPOL_csv_col.zip"]
IMF = "https://www.imf.org/external/datamapper/api/v1/"
ISO2TO3 = json.loads('{"AD":"AND","AE":"ARE","AF":"AFG","AG":"ATG","AI":"AIA","AL":"ALB","AM":"ARM","AO":"AGO","AQ":"ATA","AR":"ARG","AS":"ASM","AT":"AUT","AU":"AUS","AW":"ABW","AX":"ALA","AZ":"AZE","BA":"BIH","BB":"BRB","BD":"BGD","BE":"BEL","BF":"BFA","BG":"BGR","BH":"BHR","BI":"BDI","BJ":"BEN","BL":"BLM","BM":"BMU","BN":"BRN","BO":"BOL","BQ":"BES","BR":"BRA","BS":"BHS","BT":"BTN","BV":"BVT","BW":"BWA","BY":"BLR","BZ":"BLZ","CA":"CAN","CC":"CCK","CD":"COD","CF":"CAF","CG":"COG","CH":"CHE","CI":"CIV","CK":"COK","CL":"CHL","CM":"CMR","CN":"CHN","CO":"COL","CR":"CRI","CU":"CUB","CV":"CPV","CW":"CUW","CX":"CXR","CY":"CYP","CZ":"CZE","DE":"DEU","DJ":"DJI","DK":"DNK","DM":"DMA","DO":"DOM","DZ":"DZA","EC":"ECU","EE":"EST","EG":"EGY","EH":"ESH","ER":"ERI","ES":"ESP","ET":"ETH","FI":"FIN","FJ":"FJI","FK":"FLK","FM":"FSM","FO":"FRO","FR":"FRA","GA":"GAB","GB":"GBR","GD":"GRD","GE":"GEO","GF":"GUF","GG":"GGY","GH":"GHA","GI":"GIB","GL":"GRL","GM":"GMB","GN":"GIN","GP":"GLP","GQ":"GNQ","GR":"GRC","GS":"SGS","GT":"GTM","GU":"GUM","GW":"GNB","GY":"GUY","HK":"HKG","HM":"HMD","HN":"HND","HR":"HRV","HT":"HTI","HU":"HUN","ID":"IDN","IE":"IRL","IL":"ISR","IM":"IMN","IN":"IND","IO":"IOT","IQ":"IRQ","IR":"IRN","IS":"ISL","IT":"ITA","JE":"JEY","JM":"JAM","JO":"JOR","JP":"JPN","KE":"KEN","KG":"KGZ","KH":"KHM","KI":"KIR","KM":"COM","KN":"KNA","KP":"PRK","KR":"KOR","KW":"KWT","KY":"CYM","KZ":"KAZ","LA":"LAO","LB":"LBN","LC":"LCA","LI":"LIE","LK":"LKA","LR":"LBR","LS":"LSO","LT":"LTU","LU":"LUX","LV":"LVA","LY":"LBY","MA":"MAR","MC":"MCO","MD":"MDA","ME":"MNE","MF":"MAF","MG":"MDG","MH":"MHL","MK":"MKD","ML":"MLI","MM":"MMR","MN":"MNG","MO":"MAC","MP":"MNP","MQ":"MTQ","MR":"MRT","MS":"MSR","MT":"MLT","MU":"MUS","MV":"MDV","MW":"MWI","MX":"MEX","MY":"MYS","MZ":"MOZ","NA":"NAM","NC":"NCL","NE":"NER","NF":"NFK","NG":"NGA","NI":"NIC","NL":"NLD","NO":"NOR","NP":"NPL","NR":"NRU","NU":"NIU","NZ":"NZL","OM":"OMN","PA":"PAN","PE":"PER","PF":"PYF","PG":"PNG","PH":"PHL","PK":"PAK","PL":"POL","PM":"SPM","PN":"PCN","PR":"PRI","PS":"PSE","PT":"PRT","PW":"PLW","PY":"PRY","QA":"QAT","RE":"REU","RO":"ROU","RS":"SRB","RU":"RUS","RW":"RWA","SA":"SAU","SB":"SLB","SC":"SYC","SD":"SDN","SE":"SWE","SG":"SGP","SH":"SHN","SI":"SVN","SJ":"SJM","SK":"SVK","SL":"SLE","SM":"SMR","SN":"SEN","SO":"SOM","SR":"SUR","SS":"SSD","ST":"STP","SV":"SLV","SX":"SXM","SY":"SYR","SZ":"SWZ","TC":"TCA","TD":"TCD","TF":"ATF","TG":"TGO","TH":"THA","TJ":"TJK","TK":"TKL","TL":"TLS","TM":"TKM","TN":"TUN","TO":"TON","TR":"TUR","TT":"TTO","TV":"TUV","TW":"TWN","TZ":"TZA","UA":"UKR","UG":"UGA","UM":"UMI","US":"USA","UY":"URY","UZ":"UZB","VA":"VAT","VC":"VCT","VE":"VEN","VG":"VGB","VI":"VIR","VN":"VNM","VU":"VUT","WF":"WLF","WS":"WSM","YE":"YEM","YT":"MYT","ZA":"ZAF","ZM":"ZMB","ZW":"ZWE"}')
# The euro area's members and the month each took the euro.
EURO = {"AT": "1999-01", "BE": "1999-01", "DE": "1999-01", "ES": "1999-01", "FI": "1999-01", "FR": "1999-01", "IE": "1999-01",
        "IT": "1999-01", "LU": "1999-01", "NL": "1999-01", "PT": "1999-01", "GR": "2001-01", "SI": "2007-01", "CY": "2008-01",
        "MT": "2008-01", "SK": "2009-01", "EE": "2011-01", "LV": "2014-01", "LT": "2015-01", "HR": "2023-01", "BG": "2026-01"}
csv.field_size_limit(1 << 30)


def get(url, tries=4, timeout=180):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"  {url}: {e}; again in {20 * (i + 1)}s", flush=True)
            time.sleep(20 * (i + 1))


def col(header, key):
    """The column whose code (before any ':') is key."""
    for i, h in enumerate(header):
        if h.split(":")[0].strip().upper() == key:
            return i
    return None


def bis_rows(raw):
    """(freq, area code, area name, period, value) from either bulk layout."""
    z = zipfile.ZipFile(io.BytesIO(raw))
    name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
    rows = list(csv.reader(io.TextIOWrapper(z.open(name), encoding="utf-8-sig", errors="replace")))
    header = rows[0]
    f, a, t, v = col(header, "FREQ"), col(header, "REF_AREA"), col(header, "TIME_PERIOD"), col(header, "OBS_VALUE")
    out = []
    if t is not None and v is not None:
        for r in rows[1:]:
            if len(r) <= max(a, t, v):
                continue
            code = r[a].split(":")[0].strip()
            nm = r[a].split(":", 1)[1].strip() if ":" in r[a] else code
            out.append((r[f].split(":")[0].strip() if f is not None else "", code, nm, r[t].strip(), r[v].strip()))
    else:
        dates = [(i, h.strip()) for i, h in enumerate(header) if re.match(r"^\d{4}(-\d{2}){0,2}$", h.strip())]
        for r in rows[1:]:
            if a is None or len(r) <= a:
                continue
            code = r[a].split(":")[0].strip()
            nm = r[a].split(":", 1)[1].strip() if ":" in r[a] else code
            fr = r[f].split(":")[0].strip() if f is not None and len(r) > f else ""
            for i, d in dates:
                if i < len(r) and r[i].strip():
                    out.append((fr, code, nm, d, r[i].strip()))
    return out


def policy_rates():
    raw = None
    for url in BIS:
        try:
            raw = get(url)
            src = url
            break
        except Exception as e:  # noqa: BLE001
            print(f"  BIS {url}: {e}", flush=True)
    if raw is None:
        print("policy_rates: BIS did not answer; the last good copy stays")
        return
    rows = bis_rows(raw)
    banks, months = {}, set()
    for fr, code, nm, period, val in rows:
        if fr not in ("M", "") or not re.match(r"^\d{4}-\d{2}$", period):
            continue
        try:
            x = float(val)
        except ValueError:
            continue
        b = banks.setdefault(code, {"name": nm, "iso3": ISO2TO3.get(code), "rates": {}})
        b["rates"][period] = x
        months.add(period)
    if not banks:
        sys.exit(f"policy_rates: no monthly values read from {src} (its layout may have changed)")
    shade = {}
    for code, b in banks.items():
        if b["iso3"]:
            shade[b["iso3"]] = {"bank": code, "rates": b["rates"]}
    if "XM" in banks:
        for c2, since in EURO.items():
            i3 = ISO2TO3[c2]
            own = shade.get(i3, {"bank": c2, "rates": {}})
            rates = dict(own["rates"])
            for m, x in banks["XM"]["rates"].items():
                if m >= since:
                    rates[m] = x
            shade[i3] = {"bank": own["bank"], "rates": rates, "euro_from": since}
    OUT.mkdir(exist_ok=True)
    (OUT / "policy_rates.json").write_text(json.dumps({
        "read": time.strftime("%Y-%m-%d", time.gmtime()), "source": src,
        "credit": "Source: Bank for International Settlements, central bank policy rates (WS_CBPOL)",
        "months": sorted(months), "banks": banks, "countries": shade}, ensure_ascii=False, separators=(",", ":")))
    print(f"policy_rates: {len(banks)} central banks, {len(months)} months, {len(shade)} countries shaded")


def imbalances():
    try:
        names = json.loads(get(IMF + "countries")).get("countries", {})
        meta = json.loads(get(IMF + "indicators")).get("indicators", {})
        vals = {ind: json.loads(get(IMF + ind)).get("values", {}).get(ind, {}) for ind in ("BCA_NGDPD", "BCA")}
    except Exception as e:  # noqa: BLE001
        print(f"imbalances: the IMF did not answer ({e}); the last good copy stays")
        return
    if not any(vals.values()):
        sys.exit("imbalances: the IMF gave no values (its layout may have changed)")
    countries, groups, years = {}, {}, set()
    for ind, by in vals.items():
        for code, series in by.items():
            clean = {str(y): v for y, v in series.items() if isinstance(v, (int, float))}
            years.update(clean)
            where = countries if code in names else groups
            where.setdefault(code, {"name": (names.get(code) or {}).get("label", code)})[ind] = clean
    OUT.mkdir(exist_ok=True)
    (OUT / "imbalances.json").write_text(json.dumps({
        "read": time.strftime("%Y-%m-%d", time.gmtime()), "source": IMF,
        "credit": "Source: International Monetary Fund, World Economic Outlook (DataMapper)",
        "measures": {k: {"label": (meta.get(k) or {}).get("label", k), "unit": (meta.get(k) or {}).get("unit", ""),
                         "about": (meta.get(k) or {}).get("description", "")} for k in vals},
        "years": sorted(years), "countries": countries, "groups": groups}, ensure_ascii=False, separators=(",", ":")))
    print(f"imbalances: {len(countries)} countries, {len(groups)} groups, years {min(years)} to {max(years)}")


if __name__ == "__main__":
    policy_rates()
    imbalances()
