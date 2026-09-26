#!/usr/bin/env python3
"""
Banking on Climate Chaos 2026: a first look, made on GitHub's machines because
the sites cannot be reached from where the map is written. Nothing is mapped
yet. It saves, in bocc/probe/:

  report.pdf, report.txt   the 2026 report (Rainforest Action Network's copy)
                           and its text page by page, with every table
                           pdfplumber finds (report_tables.json)
  site.html, site_urls.txt the report site's front page and every link or
                           script address in it that could hold its per-bank
                           data (json, csv, xlsx, api, wp-json, ajax)
  site_data/               each of those addresses fetched, as they came
  gleif.json               for each bank, the five closest entries in the
                           official Legal Entity Identifier register (GLEIF):
                           LEI, legal name, legal and headquarters address

From these the owner approves which GLEIF entry stands for each bank, and the
map layer is built from the report's own figures. Run by hand: refresh, with
bocc_probe in the box.
"""
import json, pathlib, re, subprocess, sys, time, urllib.parse, urllib.request

OUT = pathlib.Path("bocc/probe")
SITE = "https://www.bankingonclimatechaos.org/"
PDF = "https://www.ran.org/wp-content/uploads/2026/06/BOCC_2026_vFINAL-1.pdf"
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas; github.com/WelcomeToYourGalaxy)"}

# The report's short names, as a search for the parent company in GLEIF.
BANKS = [
    "JPMorgan Chase & Co.", "Bank of America Corporation", "Mitsubishi UFJ Financial Group", "Mizuho Financial Group",
    "Citigroup Inc.", "Wells Fargo & Company", "Royal Bank of Canada", "Barclays PLC", "Sumitomo Mitsui Financial Group",
    "Morgan Stanley", "The Goldman Sachs Group", "The Toronto-Dominion Bank", "The Bank of Nova Scotia", "Truist Financial Corporation",
    "Canadian Imperial Bank of Commerce", "CITIC Group", "China CITIC Bank", "Bank of China Limited", "The PNC Financial Services Group",
    "U.S. Bancorp", "Deutsche Bank AG", "Banco Santander", "HSBC Holdings plc", "Bank of Montreal",
    "Industrial and Commercial Bank of China", "Standard Chartered PLC", "China Merchants Bank", "China Construction Bank",
    "ING Groep", "Societe Generale", "Credit Agricole", "Banco Bilbao Vizcaya Argentaria", "Industrial Bank Co., Ltd.",
    "BNP Paribas", "Agricultural Bank of China", "Shanghai Pudong Development Bank", "BPCE", "China Everbright Group",
    "China Everbright Bank", "Capital One Financial Corporation", "State Bank of India", "Intesa Sanpaolo", "Bank of Beijing",
    "UniCredit", "China Minsheng Banking Corp", "DBS Group Holdings", "Ping An Insurance (Group) Company of China", "UBS Group AG",
    "Bank of Jiangsu", "Cooperatieve Rabobank", "NatWest Group plc", "Commerzbank AG", "Australia and New Zealand Banking Group",
    "Bank of Communications", "KB Financial Group", "Lloyds Banking Group plc", "DZ BANK AG", "Postal Savings Bank of China",
    "Danske Bank", "CaixaBank", "Fundacion Bancaria La Caixa", "National Australia Bank", "Hua Xia Bank", "Westpac Banking Corporation",
    "Nordea Bank Abp", "Commonwealth Bank of Australia", "Confederation Nationale du Credit Mutuel", "La Banque Postale",
]


def get(url, timeout=120):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    log = []
    try:
        (OUT / "report.pdf").write_bytes(get(PDF, 300))
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pdfplumber"], check=True)
        import pdfplumber
        pages, tables = [], []
        with pdfplumber.open(OUT / "report.pdf") as pdf:
            for n, pg in enumerate(pdf.pages, 1):
                pages.append(f"===== page {n} =====\n" + (pg.extract_text() or ""))
                for t in pg.extract_tables():
                    tables.append({"page": n, "rows": t})
        (OUT / "report.txt").write_text("\n".join(pages), encoding="utf-8")
        (OUT / "report_tables.json").write_text(json.dumps(tables, ensure_ascii=False, indent=0), encoding="utf-8")
        log.append(f"report: {len(pages)} pages, {len(tables)} tables")
    except Exception as e:  # noqa: BLE001
        log.append(f"report: not read ({e})")
    try:
        html = get(SITE).decode("utf-8", "replace")
        (OUT / "site.html").write_text(html, encoding="utf-8")
        urls = sorted(set(re.findall(r"""(?:src|href|data-[a-z-]+)=["']([^"']+)["']""", html)) |
                      set(re.findall(r"""https?://[^\s"'<>()]+""", html)))
        want = [u for u in urls if re.search(r"\.(json|csv|xlsx?|js)(\?|$)|wp-json|api|ajax|data", u, re.I)]
        (OUT / "site_urls.txt").write_text("\n".join(urls), encoding="utf-8")
        d = OUT / "site_data"
        d.mkdir(exist_ok=True)
        for i, u in enumerate(want[:80]):
            full = urllib.parse.urljoin(SITE, u)
            try:
                body = get(full, 60)
                if len(body) > 20_000_000:
                    continue
                name = f"{i:02d}_" + re.sub(r"[^A-Za-z0-9._-]+", "_", urllib.parse.urlparse(full).path)[-80:]
                (d / name).write_bytes(body)
                log.append(f"site data: {full} -> {name} ({len(body):,} bytes)")
            except Exception as e:  # noqa: BLE001
                log.append(f"site data: {full} not read ({e})")
    except Exception as e:  # noqa: BLE001
        log.append(f"site: not read ({e})")
    gleif = {}
    for b in BANKS:
        q = urllib.parse.urlencode({"filter[fulltext]": b, "page[size]": 5})
        try:
            j = json.loads(get(f"https://api.gleif.org/api/v1/lei-records?{q}", 60))
            gleif[b] = [{"lei": r["id"], "legal_name": r["attributes"]["entity"]["legalName"]["name"],
                         "status": r["attributes"]["entity"].get("status"),
                         "legal_address": r["attributes"]["entity"].get("legalAddress"),
                         "headquarters_address": r["attributes"]["entity"].get("headquartersAddress")} for r in j.get("data", [])]
        except Exception as e:  # noqa: BLE001
            gleif[b] = f"not read ({e})"
        time.sleep(1)
    (OUT / "gleif.json").write_text(json.dumps(gleif, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "log.txt").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
