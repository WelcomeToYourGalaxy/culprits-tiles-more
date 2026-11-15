#!/usr/bin/env python3
"""
The Genetic engineering map's own country write-ups, "What you can do" lists,
open consultations, international bodies and how-to guides, copied for the
Culprits map (round 76, 27 September).

These are not files in the Genetic engineering map's repository: they are
built in the reader's browser from its data (harvest/resources.json,
harvest/consultations.json, overlays/*.geojson, projects.json) by the map's own
code. Rewriting that code in the Culprits map would make two versions that
drift apart. So the map itself is opened here, in a headless browser, and asked
for what it would show: _regimeBox(iso) for each country's write-up,
pjCountryResources(name) for its "What you can do" list, the consultations box
as it builds it, and internationalBodies as it declares it. Nothing is edited
except that <script> tags are taken out.

Writes, under gmo/:
  countries/<ISO3>.json {name, law, act} - HTML as the map builds it;
                       countries.json lists them
  panel.json           {consultations, guides:[{title,url}], made}
  bodies.places.geojson + bodies.boxes.json - the international bodies as a
                       site map (each body at its seat, its trackers in the box)
Daily; the consultations expire, and the map says so itself.
"""
import http.server, json, os, pathlib, re, socketserver, subprocess, sys, tempfile, threading, time

OUT = pathlib.Path("gmo")
REPO = "https://github.com/WelcomeToYourGalaxy/GMO-map.git"
PAGES = "https://welcometoyourgalaxy.github.io/GMO-map/"


def sh(cmd, **kw):
    print("  $", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def clean(html):
    return re.sub(r"<script\b[\s\S]*?</script>", "", str(html or ""), flags=re.I)


def serve(root):
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(root), **k)

        def log_message(self, *a):
            pass
    srv = socketserver.TCPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def main():
    work = pathlib.Path(tempfile.mkdtemp())
    src = work / "gmo"
    if os.environ.get("GMO_SRC"):          # a local checkout, for testing
        src = pathlib.Path(os.environ["GMO_SRC"])
    else:
        sh(["git", "clone", "-q", "--depth", "1", REPO, str(src)])
    if not os.environ.get("GMO_NO_INSTALL"):
        sh([sys.executable, "-m", "pip", "install", "-q", "playwright"])
        sh([sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"])
    from playwright.sync_api import sync_playwright

    treaties = json.loads((src / "overlays" / "treaties.geojson").read_text())
    names = {}
    for f in treaties.get("features", []):
        p = f.get("properties") or {}
        if p.get("iso"):
            names[p["iso"]] = p.get("name") or p["iso"]
    # Countries named on the other overlays too, so none with a write-up is missed.
    for k in ("regime", "gmofree", "cultivation", "incidents"):
        try:
            for f in json.loads((src / "overlays" / f"{k}.geojson").read_text()).get("features", []):
                p = f.get("properties") or {}
                iso = p.get("iso") or (p.get("name") if k == "regime" else None)
                if iso and re.fullmatch(r"[A-Z]{3}", str(iso)):
                    names.setdefault(iso, iso)
        except Exception as e:  # noqa: BLE001
            print(f"  overlay {k}: {e}", file=sys.stderr)
    srv, port = serve(src)
    errors = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(**({"executable_path": os.environ["GMO_CHROMIUM"]} if os.environ.get("GMO_CHROMIUM") else {}))
        page = b.new_page()
        cdn = os.environ.get("GMO_CDN_DIR")    # local copies of the map's libraries, for testing offline
        if cdn:
            def route(r):
                u = r.request.url
                for key, f in (("leaflet.min.js", "leaflet-1.9.4/dist/leaflet.js"), ("leaflet.min.css", "leaflet-1.9.4/dist/leaflet.css"),
                               ("topojson.min.js", "topojson-3.0.2/dist/topojson.min.js")):
                    if key in u:
                        return r.fulfill(path=os.path.join(cdn, f))
                return r.continue_() if u.startswith("http://127.0.0.1") else r.abort()
            page.route("**/*", route)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="domcontentloaded", timeout=120000)
        # The map reads its files as it opens; wait until the resources and the
        # consultations have both arrived (the consultations box stops saying it
        # is checking), or two minutes.
        ready = False
        for _ in range(120):
            ready = page.evaluate("""() => !!(window.PJ_RES && typeof window.pjCountryResources === 'function'
                && typeof _regimeBox === 'function' && window._ovData && window._ovData.regime
                && document.getElementById('consBody') && !/Checking for open comment windows/.test(document.getElementById('consBody').innerHTML))""")
            if ready:
                break
            time.sleep(1)
        print(f"gmo_boxes: map ready={ready}; {len(errors)} page errors" + (f" (first: {errors[0]})" if errors else ""), flush=True)
        boxes = page.evaluate("""(names) => {
            const out = {};
            for (const [iso, name] of Object.entries(names)) {
              let law = '', act = '';
              try { law = _regimeBox(iso); } catch (e) { law = ''; }
              try { act = String(window.pjCountryResources(name) || ''); } catch (e) { act = ''; }
              out[iso] = { name, law, act };
            }
            return out;
        }""", names)
        page.evaluate("() => { try { window.pjBuildConsPanel && window.pjBuildConsPanel(); } catch (e) {} }")
        cons = page.evaluate("() => (document.getElementById('consBody') || {}).innerHTML || ''")
        guides = page.evaluate("""() => [...document.querySelectorAll('#guidesBody a.guide-btn')].map((a) => {
            const m = (a.getAttribute('onclick') || '').match(/openGuide\\('([^']+)'\\s*,\\s*'([^']+)'/);
            return m ? { url: m[1], title: m[2] } : null; }).filter(Boolean)""")
        bodies = page.evaluate("() => (typeof internationalBodies !== 'undefined' ? internationalBodies : [])")
        b.close()
    srv.shutdown()

    OUT.mkdir(exist_ok=True)
    for v in boxes.values():
        v["law"], v["act"] = clean(v["law"]), clean(v["act"])
    # One file per country, read when that country is clicked: all of them
    # together are over 14 MB (a country's filed decisions are listed whole).
    cdir = OUT / "countries"
    cdir.mkdir(exist_ok=True)
    for iso, v in boxes.items():
        (cdir / f"{iso}.json").write_text(json.dumps(v, ensure_ascii=False))
    (OUT / "countries.json").write_text(json.dumps({iso: v["name"] for iso, v in boxes.items()}, ensure_ascii=False))
    (OUT / "panel.json").write_text(json.dumps({
        "made": int(time.time()), "consultations": clean(cons),
        "guides": [{"title": g["title"], "url": PAGES + g["url"]} for g in guides],
    }, ensure_ascii=False))

    esc = lambda s: (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))
    feats, bx = [], {}
    for i, body in enumerate(bodies):
        if body.get("lat") is None or body.get("lng") is None:
            continue
        k = f"b{i}"
        items = "".join(
            f'<div class="gmo-tr"><a href="{esc(t.get("url"))}" target="_blank" rel="noopener"><b>{esc(t.get("name"))}</b></a>'
            + (f'<div>{esc(t.get("desc"))}</div>' if t.get("desc") else "")
            + (f'<div class="meta">{esc(", ".join(t.get("tags") or []))}</div>' if t.get("tags") else "")
            + "</div>" for t in body.get("trackers") or [])
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [body["lng"], body["lat"]]},
                      "properties": {"k": k, "p": 1, "t": 1, "n": body.get("name", ""), "c": "", "f": ""}})
        bx[k] = {"t": f"<b>{esc(body.get('name'))}</b>",
                 "h": f'<div class="meta">{len(body.get("trackers") or [])} resources{(" · " + esc(body.get("guide"))) if body.get("guide") else ""}</div>{items}',
                 "o": {"maxWidth": 360, "maxHeight": 460}}
    (OUT / "bodies.places.geojson").write_text(json.dumps({"type": "FeatureCollection", "filters": [], "features": feats}, ensure_ascii=False))
    (OUT / "bodies.boxes.json").write_text(json.dumps({"name": "International bodies (Genetic engineering map)", "css": "",
                                                       "stylesheets": [], "chain": [], "boxes": bx}, ensure_ascii=False))
    n_law = sum(1 for v in boxes.values() if v["law"])
    n_act = sum(1 for v in boxes.values() if v["act"])
    print(f"gmo_boxes: {len(boxes)} countries ({n_law} write-ups, {n_act} action lists); "
          f"{len(guides)} guides; {len(feats)} international bodies with "
          f"{sum(len(b.get('trackers') or []) for b in bodies)} resources", flush=True)


if __name__ == "__main__":
    main()
