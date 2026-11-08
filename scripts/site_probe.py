#!/usr/bin/env python3
"""
What two sites load when they open (round 79, 27 September): They Rule
(theyrule.net), the UN Register of Conventional Arms (unroca.org) and the
Missile Range Simulator (missilerangesimulator.web.app, round 81). Both are
built in the browser and name no data file in their pages, so this opens each
in a headless browser and writes down every request it makes, with the start
of every data answer, so the next round can read their data at the address
they themselves use rather than a guessed one. For They Rule it also reads the
source maps its build publishes and lists the data files bundled into it.

Writes probe/sites/<name>.json. Changes nothing else. Runs only when the
refresh is run by hand, or when a probe is missing.
"""
import json, os, pathlib, re, subprocess, sys, urllib.request

OUT = pathlib.Path("probe/sites")
SITES = {"theyrule": "https://theyrule.net/", "unroca": "https://www.unroca.org/",
         # Round 81: its weapons database ("Educational use only. All data from
         # public sources."), for missile ranges on the conflict layer.
         "missilerange": "https://missilerangesimulator.web.app/", "missilerange_db": "https://missilerangesimulator.web.app/database"}
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas; welcometoyourgalaxy@gmail.com)"}


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()


def theyrule_maps():
    """The data files named in They Rule's source maps, each with its size and start."""
    out = []
    try:
        man = json.loads(get("https://theyrule.net/asset-manifest.json"))
    except Exception as e:  # noqa: BLE001
        return [{"error": f"asset-manifest.json: {e}"}]
    files = man.get("files", man)
    for k, v in files.items():
        if not str(v).endswith(".js.map"):
            continue
        try:
            m = json.loads(get("https://theyrule.net" + v if v.startswith("/") else "https://theyrule.net/" + v))
        except Exception as e:  # noqa: BLE001
            out.append({"map": v, "error": str(e)})
            continue
        for src, content in zip(m.get("sources", []), m.get("sourcesContent") or []):
            if re.search(r"(data|dataset|json)", src, re.I) and "node_modules" not in src:
                out.append({"map": v, "source": src, "bytes": len(content or ""), "start": (content or "")[:600]})
    return out


def main():
    if os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch" and all((OUT / f"{n}.json").exists() for n in SITES):
        print("site_probe: already probed; run the refresh by hand to probe again")
        return
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "playwright"], check=True)
    subprocess.run([sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"], check=True)
    from playwright.sync_api import sync_playwright
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for name, url in SITES.items():
            reqs = []
            page = b.new_page()

            def seen(resp, reqs=reqs):
                try:
                    ct = resp.headers.get("content-type", "")
                    row = {"url": resp.url, "status": resp.status, "type": ct, "method": resp.request.method}
                    if re.search(r"json|text/plain|csv|xml", ct) or re.search(r"\.(json|csv|xml)(\?|$)", resp.url):
                        body = resp.body()
                        row["bytes"] = len(body)
                        row["start"] = body[:800].decode("utf-8", "replace")
                    reqs.append(row)
                except Exception as e:  # noqa: BLE001
                    reqs.append({"url": resp.url, "error": str(e)})
            page.on("response", seen)
            try:
                page.goto(url, wait_until="networkidle", timeout=120000)
                page.wait_for_timeout(8000)
                links = page.evaluate("() => [...document.querySelectorAll('a[href]')].map(a => a.href).slice(0, 400)")
                text = page.evaluate("() => document.body.innerText.slice(0, 3000)")
            except Exception as e:  # noqa: BLE001
                links, text = [], f"did not open: {e}"
            rec = {"site": url, "requests": reqs, "links": links, "text": text}
            if name == "theyrule":
                rec["bundled_data"] = theyrule_maps()
            (OUT / f"{name}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
            print(f"site_probe: {name}: {len(reqs)} requests, {sum(1 for r in reqs if 'start' in r)} with data")
            page.close()
        b.close()


if __name__ == "__main__":
    main()
