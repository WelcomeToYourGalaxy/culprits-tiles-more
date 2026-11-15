#!/usr/bin/env python3
"""
Who Owns the Food Industry, whole (round 135b, asked 2 October: "Not all of
the data that came with the Who owns the food industry layer was transferred
to this map; only base info like company name").

Reads the page's own data (maps repo site/site_food_system.html): the 48
companies (sector, revenue, share of the system, ownership, headquarters,
description, brands, regional sites), the 8 asset managers and financiers
(what they manage, which companies they hold), the 5 lobby groups (members)
and the 12 bodies in the industry's orbit (whom they are tied to). Writes:

  food/system.places.geojson  every entry at its headquarters, every regional
                              site, and a line for every tie the page draws
                              (holdings, lobby membership, orbit ties)
  food/system.boxes.json      each one's box, with everything the page gives
  food/system.build.json      counts, and any tie whose company was not found

Nothing is left out or added: the figures are the page's own. Weekly, or by
hand; the arrays are read with node, which the runners have.
"""
import hashlib, html, json, pathlib, re, subprocess, sys, tempfile, urllib.request

PAGE = "https://raw.githubusercontent.com/WelcomeToYourGalaxy/maps/main/site/site_food_system.html"
OUT = pathlib.Path("food")
GLOBAL = 12000  # the page's own size of the whole system, US$ billion (const GLOBAL=12000)
EXTRA = {"Capital": ("#34495e", "Asset managers and financiers"), "Influence": ("#c2185b", "Lobby groups"),
         "Orbit": ("#3949ab", "Bodies in the industry's orbit")}


def arr(s, name):
    i = s.index(f"const {name}=") + len(f"const {name}=")
    opener = s[i]
    closer = "]" if opener == "[" else "}"
    d = 0
    for j in range(i, len(s)):
        if s[j] == opener:
            d += 1
        elif s[j] == closer:
            d -= 1
            if d == 0:
                return s[i:j + 1]
    raise SystemExit(f"food_system: {name} not closed on the page")


def key(*parts):
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:16]


def esc(x):
    return html.escape(str(x), quote=True)


def main():
    s = urllib.request.urlopen(urllib.request.Request(PAGE, headers={"User-Agent": "Culprits atlas build"}), timeout=120).read().decode("utf-8")
    js = "\n".join(f"const {n}={arr(s, n)};" for n in ("COMP", "FIN", "LOB", "ORB", "SECMETA")) + \
        "\nprocess.stdout.write(JSON.stringify({COMP,FIN,LOB,ORB,SECMETA}));"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(js)
    d = json.loads(subprocess.run(["node", f.name], capture_output=True, text=True, check=True).stdout)
    meta = d["SECMETA"]
    for k, (col, label) in EXTRA.items():
        meta.setdefault(k, {"col": col, "label": label})
    comp = {c["n"]: c for c in d["COMP"]}
    holders, lobbies, orbits = {}, {}, {}
    ties, missing = [], []
    for fi in d["FIN"]:
        # The page's holdings: names, or [name, how strongly it draws the line]
        # (a drawing weight, not a share of the company).
        held = [c["n"] for c in d["COMP"] if c.get("bt")] if fi.get("holdsBt") else [h[0] if isinstance(h, list) else h for h in fi.get("holds") or []]
        for n in held:
            (ties.append((fi, n, "Ties: shareholdings: holds shares in")) if n in comp else missing.append([fi["n"], n]))
            holders.setdefault(n, []).append(fi["n"])
        fi["_held"] = held
    for lb in d["LOB"]:
        for n in lb.get("members") or []:
            (ties.append((lb, n, "Ties: lobby membership: member")) if n in comp else missing.append([lb["n"], n]))
            lobbies.setdefault(n, []).append(lb["n"])
    for ob in d["ORB"]:
        for n in ob.get("ties") or []:
            (ties.append((ob, n, "Ties: the orbit: tied to")) if n in comp else missing.append([ob["n"], n]))
            orbits.setdefault(n, []).append(ob["n"])
    feats, boxes, kinds = [], {}, {}

    def put(geom, props, kind, h):
        k = props["k"]
        props["f"] = f"|{kind}|"
        kinds[kind] = kinds.get(kind, 0) + 1
        feats.append({"type": "Feature", "geometry": geom, "properties": props})
        boxes[k] = {"h": h}

    def row(label, value):
        return f'<div class="pop-meta"><b>{esc(label)}:</b> {esc(value)}</div>' if value not in (None, "", []) else ""

    for c in d["COMP"]:
        m = meta.get(c["sec"], {})
        share = c["rev"] / GLOBAL * 100 if c.get("rev") is not None else None
        k = key("comp", c["n"])
        h = (f'<div class="pop-n">{esc(c["n"])}</div><div>{esc(c.get("desc", ""))}</div>' +
             row("Part of the system", m.get("label", c["sec"])) +
             row("Revenue", f'about ${c["rev"]} billion a year' if c.get("rev") is not None else None) +
             row("Share of the whole food system", f'about {share:.2f}%' if share is not None and share < 1 else (f'about {share:.1f}%' if share is not None else None)) +
             row("Ownership", c.get("own")) + row("Headquarters", c.get("city")) +
             row("Brands", ", ".join(c.get("b") or [])) +
             row("Regional sites", "; ".join(r[2] for r in c.get("reg") or [])) +
             row("Held by (asset managers and financiers)", ", ".join(holders.get(c["n"], []))) +
             row("Member of (lobby groups)", ", ".join(lobbies.get(c["n"], []))) +
             row("Tied to (bodies in the industry's orbit)", ", ".join(orbits.get(c["n"], []))) +
             '<div class="pop-meta">Source: Who Owns the Food Industry (Welcome to Your Galaxy), figures as the page gives them; share = revenue over the page\'s $12 trillion system.</div>')
        put({"type": "Point", "coordinates": [c["hq"][1], c["hq"][0]]},
            {"k": k, "c": m.get("col", "#6E6A55"), "r": max(6.0, min(16.0, 5 + (c.get("rev") or 0) ** 0.5)), "s": "#FFFFFF", "w": 2, "o": 0.95, "n": c["n"], "p": 1},
            m.get("label", c["sec"]), h)
        for lat, lng, what in c.get("reg") or []:
            put({"type": "Point", "coordinates": [lng, lat]},
                {"k": key("reg", c["n"], what), "c": m.get("col", "#6E6A55"), "r": 4.0, "s": "#FFFFFF", "w": 1, "o": 0.8, "n": f'{c["n"]}: {what}', "p": 1},
                "Regional sites", f'<div class="pop-n">{esc(c["n"])}</div><div class="pop-meta">{esc(what)}</div>' +
                '<div class="pop-meta">A regional site the page gives for this company (positions marked approx. there are approximate).</div>')
    for group, sec in ((d["FIN"], "Capital"), (d["LOB"], "Influence"), (d["ORB"], "Orbit")):
        for o in group:
            m = meta.get(o.get("sec") or sec, {})
            linked = o.get("_held") or o.get("members") or o.get("ties") or []
            word = {"Capital": "Holds shares in", "Influence": "Members", "Orbit": "Tied to"}[sec]
            h = (f'<div class="pop-n">{esc(o["n"])}</div><div>{esc(o.get("desc", ""))}</div>' + row("Kind", EXTRA[sec][1]) +
                 row("Size", o.get("aum")) + row("Headquarters", o.get("city")) + row(word, ", ".join(linked)) +
                 ('<div class="pop-meta">The page has it hold every widely held public company it maps (its "Big Three" note).</div>' if o.get("holdsBt") else "") +
                 '<div class="pop-meta">Source: Who Owns the Food Industry (Welcome to Your Galaxy).</div>')
            put({"type": "Point", "coordinates": [o["hq"][1], o["hq"][0]]},
                {"k": key(sec, o["n"]), "c": o.get("tcol") or m.get("col"), "r": 9.0, "s": "#FFFFFF", "w": 2, "o": 0.95, "n": o["n"], "p": 1},
                EXTRA[sec][1], h)
    for o, n, kind in ties:
        c = comp[n]
        put({"type": "LineString", "coordinates": [[o["hq"][1], o["hq"][0]], [c["hq"][1], c["hq"][0]]]},
            {"k": key("tie", o["n"], n, kind), "c": o.get("tcol") or "#5E6A78", "w": 1, "o": 0.5, "n": f'{o["n"]} \u2013 {n}', "p": 1},
            kind.rsplit(":", 1)[0], f'<div class="pop-n">{esc(o["n"])} \u2013 {esc(n)}</div><div class="pop-meta">{esc(kind.rsplit(": ", 1)[1].capitalize())} (as the page draws it)</div>')
    OUT.mkdir(exist_ok=True)
    places = {"type": "FeatureCollection", "name": "Who Owns the Food Industry", "overlays": [],
              "filters": [{"label": "Type", "from": "the page's own sections", "rows": True,
                           "values": [{"k": k, "label": k, "n": n} for k, n in kinds.items()]}],
              "features": feats}
    (OUT / "system.places.geojson").write_text(json.dumps(places, ensure_ascii=False))
    old = pathlib.Path("sitemaps/site_food_system.boxes.json")
    shell = json.loads(old.read_text()) if old.exists() else {}
    shell = {k: v for k, v in shell.items() if k != "boxes"}
    shell.update({"name": "Who Owns the Food Industry", "page": PAGE, "boxes": boxes})
    (OUT / "system.boxes.json").write_text(json.dumps(shell, ensure_ascii=False))
    stamp = {"companies": len(d["COMP"]), "financiers": len(d["FIN"]), "lobby_groups": len(d["LOB"]), "orbit": len(d["ORB"]),
             "regional_sites": sum(len(c.get("reg") or []) for c in d["COMP"]), "ties": len(ties), "kinds": kinds,
             "ties_naming_no_company_on_the_page": missing}
    (OUT / "system.build.json").write_text(json.dumps(stamp, indent=1, ensure_ascii=False))
    print("food_system:", json.dumps(stamp, ensure_ascii=False)[:600])


if __name__ == "__main__":
    main()
