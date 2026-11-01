#!/usr/bin/env python3
"""
What two wildlife and timber crime sources offer, read before either is mapped
(round 101b, by hand):

  Forest Trends' ILAT Risk Data Tool (www.forest-trends.org/idat/): relative
  risk of illegal logging and associated trade, country by country. The page
  says its data and charts can be downloaded and asks to be cited as "Forest
  Trends' IDAT Risk website, as downloaded [date]". Saved: the tool's page and
  every link on it to a data file or an embedded chart, and each data file
  found (first 200 KB).

  TRAFFIC's Wildlife Trade Portal (www.wildlifetradeportal.org): seizures and
  incidents of wildlife trade. Saved: its about and terms pages as text, and
  the addresses its page script calls, so the terms can be read before any of
  it is copied.

  probe/crime/ilat.json, probe/crime/traffic.json
"""
import html, json, os, pathlib, re, urllib.parse, urllib.request

OUT = pathlib.Path("probe/crime")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}


def get(url, limit=None, timeout=120):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read(limit) if limit else r.read(), r.headers.get("Content-Type", ""), r.geturl()


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", s, flags=re.S | re.I))).strip()


def links(page, base):
    out = set()
    for h in re.findall(r'(?:href|src|data-src)=["\']([^"\']+)["\']', page, re.I):
        out.add(urllib.parse.urljoin(base, html.unescape(h)))
    return sorted(out)


def ilat():
    rec = {"pages": {}}
    for url in ["https://www.forest-trends.org/idat/ilat-risk-data-tool/", "https://www.forest-trends.org/idat/"]:
        try:
            raw, ct, final = get(url)
            page = raw.decode("utf-8", "replace")
            ls = links(page, final)
            data = [l for l in ls if re.search(r"\.(xlsx?|csv|json|zip)(\?|$)|tableau|datawrapper|flourish|powerbi|google\.com/spreadsheets|/wp-json/|ajax", l, re.I)]
            rec["pages"][url] = {"text": text(page)[:8000], "data_links": data, "all_links": ls[:400]}
            for l in data[:30]:
                try:
                    body, ct2, _ = get(l, 200_000)
                    rec.setdefault("files", {})[l] = {"type": ct2, "start": body.decode("utf-8", "replace")[:20000]}
                except Exception as e:  # noqa: BLE001
                    rec.setdefault("files", {})[l] = {"error": str(e)}
        except Exception as e:  # noqa: BLE001
            rec["pages"][url] = {"error": str(e)}
    return rec


def traffic():
    rec = {"pages": {}}
    for url in ["https://www.wildlifetradeportal.org/about", "https://www.wildlifetradeportal.org/terms",
                "https://www.wildlifetradeportal.org/terms-of-use", "https://www.wildlifetradeportal.org/"]:
        try:
            raw, ct, final = get(url)
            page = raw.decode("utf-8", "replace")
            scripts = [l for l in links(page, final) if l.endswith(".js") or "/static/js/" in l]
            calls = set()
            for s in scripts[:10]:
                try:
                    js = get(s, 3_000_000)[0].decode("utf-8", "replace")
                    calls.update(re.findall(r'https?://[a-z0-9.-]*(?:api|wildlifetradeportal)[a-z0-9./_-]*', js, re.I))
                    for m in re.finditer(r"(terms[^\"'`]{0,40}|licen[cs]e[^\"'`]{0,300}|copyright[^\"'`]{0,300})", js, re.I):
                        rec.setdefault("script_words", []).append(m.group(0)[:300])
                except Exception as e:  # noqa: BLE001
                    rec.setdefault("script_errors", []).append(f"{s}: {e}")
            rec["pages"][url] = {"final": final, "text": text(page)[:8000], "scripts": scripts, "calls": sorted(calls)[:200]}
        except Exception as e:  # noqa: BLE001
            rec["pages"][url] = {"error": str(e)}
    if "script_words" in rec:
        rec["script_words"] = sorted(set(rec["script_words"]))[:200]
    return rec


def main():
    if os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch") != "workflow_dispatch":
        print("crime_probe: by hand only")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    for name, job in (("ilat", ilat), ("traffic", traffic)):
        r = job()
        (OUT / f"{name}.json").write_text(json.dumps(r, indent=1, ensure_ascii=False))
        print(f"crime_probe: {name}: {len(r.get('pages', {}))} pages, {len(r.get('files', {}))} files", flush=True)


if __name__ == "__main__":
    main()
