#!/usr/bin/env python3
"""
The space industry map at industry.openmaps.space, copied daily into
openmaps/space_industry.geojson: every place it lists, with the organisations it
belongs to (name, logo, description, owners and their shares, staff, products,
links), written into each place's box the way the map groups them.
Source: https://industry.openmaps.space/places-en-.json
"""
import html, json, pathlib, sys, urllib.request

SRC = "https://industry.openmaps.space/places-en-.json"
OUT = pathlib.Path("openmaps/space_industry.geojson")
E = html.escape


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def position(p):
    for k in ("coordinates", "coords", "lnglat", "lonlat", "position", "center", "point"):
        v = p.get(k)
        if isinstance(v, (list, tuple)) and len(v) >= 2 and num(v[0]) is not None and num(v[1]) is not None:
            return [num(v[0]), num(v[1])] if k != "latlng" else [num(v[1]), num(v[0])]
        if isinstance(v, dict):
            lat, lng = num(v.get("lat")), num(v.get("lng", v.get("lon")))
            if lat is not None and lng is not None:
                return [lng, lat]
    g = p.get("geometry")
    if isinstance(g, dict) and g.get("type") == "Point":
        return [num(g["coordinates"][0]), num(g["coordinates"][1])]
    v = p.get("latlng")
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        return [num(v[1]), num(v[0])]
    lat, lng = num(p.get("lat", p.get("latitude"))), num(p.get("lng", p.get("lon", p.get("longitude"))))
    if lat is not None and lng is not None:
        return [lng, lat]
    return None


def org_html(o, names):
    parts = [f'<h4 style="margin:8px 0 4px">{E(o.get("name") or "")}</h4>']
    if o.get("logo"):
        parts.append(f'<img src="{E(o["logo"])}" style="max-width:120px;max-height:60px;background:#fff;padding:3px">')
    d = o.get("description") or []
    if d:
        parts.append(f"<p>{E(d[0])}</p>")
    emp = o.get("employees")
    if isinstance(emp, list) and len(emp) >= 2:
        parts.append(f"<div>Staff: {E(str(emp[1]))} ({E(str(emp[0])[1:5])}, {E(str(emp[2]) if len(emp) > 2 else '')})</div>")
    owners = []
    for par in o.get("parents") or []:
        if isinstance(par, list) and par:
            who = names.get(par[0], par[0])
            share = par[1] if len(par) > 1 else None
            owners.append(f"{E(str(who))}" + (f" ({round(float(share) * 100, 2) if float(share) <= 1 else share}%)" if share not in (None, 0) else ""))
    if owners:
        parts.append(f"<div>Owned by: {'; '.join(owners)}</div>")
    prods = [p.get("name") for p in o.get("products") or [] if p.get("name")]
    if prods:
        parts.append(f"<div>Products ({len(prods)}): {E(', '.join(prods[:25]))}{' …' if len(prods) > 25 else ''}</div>")
    links = o.get("links") or {}
    ls = [f'<a href="{E(u)}" target="_blank" rel="noopener">{E(k)}</a>' for k, u in links.items() if u]
    if ls:
        parts.append(f"<div>{' · '.join(ls)}</div>")
    return "".join(parts)


def main():
    req = urllib.request.Request(SRC, headers={"User-Agent": "Mozilla/5.0 (Culprits atlas daily copy)"})
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=120).read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        sys.exit(f"openmaps.space: could not read ({e}); the last good copy stays")
    feats = data.get("features") or {}
    orgs = {k: v for k, v in feats.items() if str(k).startswith("o")}
    places = {k: v for k, v in feats.items() if str(k).startswith("p")}
    names = {k: v.get("name") for k, v in orgs.items()}
    by_place = {}
    for ouid, o in orgs.items():
        for loc in o.get("locations") or []:
            by_place.setdefault(loc.get("uid"), []).append((o, loc.get("direct")))
    out, missing = [], 0
    for puid, p in places.items():
        at = position(p)
        if not at or None in at:
            missing += 1
            continue
        owners = by_place.get(puid, [])
        kind = p.get("type") or p.get("category") or p.get("kind") or ""
        body = (f'<h4 style="margin:0 0 4px">{E(p.get("name") or "")}</h4>' +
                (f"<div>{E(str(kind))}</div>" if kind else "") +
                (f"<div>{E(str(p.get('address')))}</div>" if p.get("address") else "") +
                "".join(org_html(o, names) + ("" if direct else "<div style='font-size:11px'>(indirectly, through a subsidiary)</div>") for o, direct in owners) +
                '<div style="margin-top:6px;font-size:11px">openmaps.space — the space industry map</div>')
        props = {k: v for k, v in p.items() if isinstance(v, (str, int, float, bool)) and k not in ("description",)}
        props.update({"_html": body, "orgs": "; ".join(o.get("name") or "" for o, _ in owners), "group": str(kind)})
        out.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": at}, "properties": props})
    if not out:
        sample = next(iter(places.values()), {})
        sys.exit(f"openmaps.space: no positions found; a place's fields are {sorted(sample.keys())}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": out}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"openmaps.space: {len(out)} places from {len(orgs)} organisations; {missing} without a position")


if __name__ == "__main__":
    main()
