#!/usr/bin/env python3
"""
Who sits on the boards of the largest companies, and the companies one person
ties together (round 119b, asked 30 September 2026: They Rule's data on the
map itself, not its page in a panel).

They Rule (theyrule.net) packs its data inside its page's own program and
states no licence for it; its 2021 boards say they come from Wikidata. So
this reads the same kind of data from Wikidata itself (CC0), for the world's
500 largest companies by revenue that companies/largest.geojson places (built
by scripts/largest_companies.py from Wikidata):

  - every person Wikidata records as a board member (P3320), chair (P488) or
    chief executive (P169) of each company, with the start and end dates
    Wikidata gives, so present and past members are told apart;
  - one line between two companies for every person recorded at both, with
    who it is.

  boards/interlocks.geojson   the companies (at their head office, as
                              largest.geojson places them) and the lines
  boards/build.json           counts, and companies Wikidata records no one for

Wikidata's records of boards are uneven: many large companies have none, and
the lines show only what is recorded. The box of each company says so.

Weekly (Mondays) or by hand.
"""
import datetime, json, os, pathlib, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import wdtools as W  # noqa: E402

SRC = pathlib.Path("companies/largest.geojson")
OUT = pathlib.Path("boards")
ROLES = {"P3320": "board member", "P488": "chair", "P169": "chief executive"}


def main():
    stamp = OUT / "build.json"
    if stamp.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("boards: weekly; not Monday")
        return
    if not SRC.exists():
        raise SystemExit("boards: companies/largest.geojson not built yet (scripts/largest_companies.py)")
    comps = [f for f in json.loads(SRC.read_text(encoding="utf-8"))["features"] if f.get("geometry")]
    by_q = {}
    for f in comps:
        q = W.qid(str(f["properties"].get("wikidata") or ""))
        if q.startswith("Q"):
            by_q[q] = f
    people = {}          # person qid -> {name, roles: [(company qid, role, start, end)]}
    qs = sorted(by_q)
    for i in range(0, len(qs), 60):
        values = " ".join(f"wd:{q}" for q in qs[i:i + 60])
        rows = W.sparql(f"""
SELECT ?c ?prop ?p ?pLabel ?start ?end WHERE {{
  VALUES ?c {{ {values} }}
  VALUES ?prop {{ p:P3320 p:P488 p:P169 }}
  ?c ?prop ?st . ?st ?ps ?p . ?psp wikibase:claim ?prop ; wikibase:statementProperty ?ps .
  ?st wikibase:rank ?rank . FILTER(?rank != wikibase:DeprecatedRank)
  OPTIONAL {{ ?st pq:P580 ?start }} OPTIONAL {{ ?st pq:P582 ?end }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,fr,de,es,ja,zh". }}
}}""")
        for b in rows:
            p = W.qid(W.v(b, "p"))
            if not p.startswith("Q"):
                continue
            role = ROLES.get(W.v(b, "prop").rsplit("/", 1)[-1], "board member")
            e = people.setdefault(p, {"name": W.v(b, "pLabel"), "roles": []})
            e["roles"].append((W.qid(W.v(b, "c")), role, W.v(b, "start")[:10], W.v(b, "end")[:10]))
        time.sleep(1)
        print(f"boards: {min(i + 60, len(qs))} of {len(qs)} companies asked", flush=True)

    on = {q: [] for q in by_q}
    for pq, e in people.items():
        for cq, role, start, end in e["roles"]:
            on[cq].append((pq, e["name"], role, start, end))
    feats, lines, none = [], [], []
    for q, f in by_q.items():
        rows = on[q]
        p = dict(f["properties"])
        say = lambda r: f"{r[1]} ({r[2]}{', from ' + r[3][:4] if r[3] else ''}{', until ' + r[4][:4] if r[4] else ''})"
        now = [r for r in rows if not r[4]]
        past = [r for r in rows if r[4]]
        ties = {other for pq, *_ in rows for (other, *_r) in people[pq]["roles"] if other != q}
        p.update({"group": "Board recorded in Wikidata" if rows else "No board members recorded in Wikidata",
                  "people recorded": len({r[0] for r in rows}),
                  "on the board or running it now (as Wikidata records)": "; ".join(sorted(say(r) for r in now)),
                  "in the past (as Wikidata records)": "; ".join(sorted(say(r) for r in past)),
                  "companies tied to it through a person": len(ties),
                  "about these records": "From Wikidata (board member, chair, chief executive). Wikidata's records of boards are uneven; "
                                         "a company with few or none recorded may have a full board."})
        feats.append({"type": "Feature", "geometry": f["geometry"], "properties": p})
        if not rows:
            none.append(p.get("name"))
    pairs = {}
    for pq, e in people.items():
        cs = sorted({r[0] for r in e["roles"]})
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                pairs.setdefault((cs[i], cs[j]), []).append(pq)
    for (a, b), who in pairs.items():
        fa, fb = by_q[a], by_q[b]
        names = []
        for pq in who:
            r = people[pq]["roles"]
            at = lambda cq: ", ".join(sorted({f"{role}{' until ' + end[:4] if end else ''}" for c, role, _s, end in r if c == cq}))
            names.append(f"{people[pq]['name']}: {fa['properties'].get('name')} ({at(a)}); {fb['properties'].get('name')} ({at(b)})")
        current = any(all(not end for c, _r, _s, end in people[pq]["roles"] if c in (a, b)) for pq in who)
        lines.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [fa["geometry"]["coordinates"], fb["geometry"]["coordinates"]]},
                      "properties": {"name": f"{fa['properties'].get('name')} and {fb['properties'].get('name')}",
                                     "people on both": len(who), "who": "; ".join(sorted(names)),
                                     "group": "Tie now: a person on both" if current else "Tie in the past",
                                     "source": "Wikidata (CC0)"}})
    OUT.mkdir(exist_ok=True)
    (OUT / "interlocks.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats + lines}, ensure_ascii=False, separators=(",", ":")))
    stamp.write_text(json.dumps({"built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "companies": len(feats), "people": len(people),
                                 "ties": len(lines), "companies with no one recorded": none}, indent=1, ensure_ascii=False))
    print(f"boards: {len(feats)} companies, {len(people)} people, {len(lines)} ties", flush=True)


if __name__ == "__main__":
    main()
