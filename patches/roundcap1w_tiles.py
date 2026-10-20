#!/usr/bin/env python3
"""Round cap1w tiles (19 October 2026): the Planted, bought or captured layer
keeps only cases of capture.

An audit (19 October) found most of the layer's points were not cases of
capture at all:
  - every foreign principal registered under the US Foreign Agents
    Registration Act (17,769 points: a legal, public tie, such as XinMin
    International registering for the Xinmin Evening News);
  - the whole UK government sanctions list (6,954 points), which came in with
    the development banks' debarment lists because its publisher's name
    ("Foreign, Commonwealth & Development Office") has "Development" in it,
    and was labelled as "fraud or corruption in projects financed by" the
    Foreign Office;
  - the development banks' debarments (3,980 firms barred from bank-financed
    projects: the banks' own findings, about contracts, not capture);
  - most of Poland's IPN entries (2,907 of 3,358): the old reading took any
    "TW", "KO", "agent" or "informator" anywhere in the record as the person's
    own registration, though most records say the person was watched, vetted,
    interned, questioned, a candidate for recruitment, or the subject of an
    informer's reports.

Nothing is deleted. scripts/capture.py now sorts each week's build: what is
not a case moves to four files of its own, each record saying how it was
sorted and, for IPN, the sentence of the record the reading rests on:
  capture/fara.geojson, capture/uk_sanctions.geojson,
  capture/debarments.geojson, capture/ipn_watched.geojson.
capture/cases.geojson keeps the rest, and capture/by_country.json (the
country shading and the lawmakers per 100 seats) is counted from the kept
cases only. This patch also sorts the files already in the repo once, so the
Culprits map is right before the next Monday build.

Upload to WelcomeToYourGalaxy/culprits-tiles-more, folder patches/. It does
not depend on any other round, and running it twice changes nothing.
"""
import json, pathlib, sys

here = pathlib.Path(__file__).resolve().parent
ROOT = here.parent if here.name == "patches" else (here.parent.parent if here.name == "failed" else pathlib.Path.cwd())
P = ROOT / "scripts" / "capture.py"
src = P.read_text()

if "round cap1w" in src:
    print("round cap1w tiles: capture.py already sorts the layer")
else:
    def once(old, new):
        global src
        n = src.count(old)
        if n != 1:
            sys.exit(f"round cap1w tiles: expected one {old[:70]!r} in scripts/capture.py, found {n}")
        src = src.replace(old, new)

    SORT = r'''# ---- round cap1w: records that are not cases of capture get rows of their own
# (audit of 19 October 2026). Nothing is deleted: each moves to its own file,
# saying how it was sorted.
MOVED = {"fara": "fara.geojson", "uk_sanctions": "uk_sanctions.geojson", "debarments": "debarments.geojson", "ipn_watched": "ipn_watched.geojson"}
MOVED_GROUP = {
    "fara": "Registered under the US Foreign Agents Registration Act (a legal, public tie, not a crime)",
    "uk_sanctions": "On the UK government's sanctions list (a government's decision, not a court ruling)",
    "debarments": "Barred by a development bank for fraud or corruption in projects it financed (the bank's own finding)",
    "ipn_watched": "In IPN's catalogue, but the records do not show them registered as a collaborator",
}
# Poland's IPN catalogue: what each record says about the person, read in
# Polish, checked by hand on samples. Their own registration, recruitment or
# agreement, or a collaborator's file in their name, counts; being watched,
# vetted, interned, questioned, a candidate, or named in someone else's
# reports does not.
_Q = r"[\"„“”']?\s*"
_ROLE = (r"(tajn\w+\s+współpracownik|\btw\b|kontakt\w*\s+(operacyjn|służbow|obywatelsk)|\bko\b|\bks\b|\bkt\b|informator|agent|rezydent|konsultant|"
         r"osob\w+\s+zaufania|lokal\w*\s+kontaktow|\blk\b|\bmk\b|\bkos\b|osobowe\s+źródł|\bozi\b)")
IPN_COLLAB = [
    r"zarejestrowan\w*[^;\n]{0,220}?\b(jako|w\s+charakterze|w\s+kategorii|do\s+kategorii|kategoria)\s+" + _Q + r"(dysponent\w*\s+)?" + _ROLE,
    r"(podpisał\w*|zawart\w*|zawarł\w*)[^.\n]{0,40}\b(umow\w*|zobowiązani\w*|deklaracj\w*)\s+(o|do)\s+współprac",
    r"(?<!próba )(?<!próby )(?<!próbę )\bpozyskan[yao]\b\s+(go\s+|ją\s+)?(do\s+współpracy|jako|w\s+charakterze)",
    r"\bzwerbowan[ya]\b|\bzwerb\.",
    r"(rozwiązan|zaprzestan|zakończon)\w*\s+współprac",
    r"wyeliminowan\w*\s+z\s+(czynnej\s+)?sieci",
]
# a sentence that says the recruitment did not happen, was only tried or
# planned, or was of someone else, does not count
IPN_NOT = (r"\bnie\s+(został\w*\s+|zostało\s+|był\w*\s+)?(pozyska|zwerb|zarejestr|zgodził|wyraził|podpisał|podjął|doszło)|\bnie\s+dał\w*\s+(pozytywn|rezultat)|"
           r"odmówił|odmow|zrezygnowan|zaniechan|\bpróbę\b|\bpróby\b|\bpróba\b|usiłowan|próbowan|próbował|zamierzan|planowan|\bmiał\w*\s+być\b|podejrzen|kandydat|innego\s+kandydata|"
           r"bezskuteczn|nieudan|niepowodzen")
IPN_OFFICER = [r"akta\s+osobowe\s+funkcjonariusza", r"pełnił\w*\s+służb\w*\s+w\s+(sb|ub|organach\s+bezpieczeństwa|wsw|zarządzie\s+ii|mbp|msw)"]
IPN_CAND = [r"kandydat\w*\s+na\s+(tajnego\s+)?(współpracownik|tw|ko|kontakt|informator|agent)", r"\bktw\b"]
IPN_WATCHED = [r"internowan", r"aresztowan", r"skazan", r"zatrzyman", r"rozpracow", r"objęt\w*\s+kontrol", r"kontrolowan\w*", r"inwigil", r"represjon", r"podsłuch",
               r"obserwacj", r"odmówił\w*\s+współprac", r"nie\s+wyraził\w*\s+zgody", r"zrezygnowano\s+z\s+pozyskania", r"rozmow\w*\s+profilaktyczn", r"figurant",
               r"zastrzeżeni", r"opiniowan", r"sprawdzeni", r"kartotek\w*\s+(opiniodawcz|ogólnoinformacyjn)", r"kwestionariusz\w*\s+ewidencyjn", r"\[ke\]", r"\bsor\b",
               r"\bsos\b", r"spraw\w*\s+obiektow", r"\bso\b"]
IPN_OWNFILE = (r"teczk\w*\s+(personaln|pracy)\w*\s+(i\s+teczk\w*\s+pracy\s+)?[\"„]?(tw\b|ko\b|informatora|agenta|rezydenta|tajnego\s+współpracownika|kontaktu)")
IPN_ABOUT = r"doniesie|donos|dotycz|na\s+temat|występuje|w\s+których|zawiera\w*\s+(informacj|doniesie)|o\s+osobie|na\s+(niego|nią|w/w|ww)"
IPN_LUSTR = r"niezgodn\w*\s+z\s+prawdą"
IPN_HOW = {
    "court": "Kept: a lustration court ruled the person's declaration of no collaboration untrue.",
    "collab": "Kept: the records say the person was registered, recruited or signed on as a secret collaborator, contact or the like.",
    "ownfile": "Kept: the records list a collaborator's personal or work file in the person's own name.",
    "officer": "Moved: the records are the person's own file as an officer of the security services, not as a collaborator.",
    "candidate": "Moved: the records show the person registered only as a candidate for recruitment, which IPN does not count as collaboration.",
    "watched": "Moved: the records show the person watched, vetted, interned, questioned, prosecuted or named in others' reports, not registered as a collaborator.",
    "unsorted": "Moved: the records do not say how the security services saw the person.",
}
IPN_NOTE = {
    "court": "A lustration court ruled this person's declaration of no collaboration untrue, as IPN's catalogue records.",
    "collab": "Registered by the security services as a collaborator or contact, as IPN's catalogue records. A registration is the services' record, not a court finding; the rulings box says whether a lustration court has ruled.",
    "ownfile": "IPN's catalogue lists a collaborator's file in this person's name. A registration is the services' record, not a court finding; the rulings box says whether a lustration court has ruled.",
}


def ipn_reading(records, rulings):
    """What an IPN record says about the person: (kind, the words it rests on)."""
    low, rul = (records or "").lower(), (rulings or "").lower()

    def hit(pats, s):
        return next((m for p in pats for m in [re.search(p, s)] if m), None)

    def sentence(text, m, cap=280):
        # the whole sentence holding the words (a full stop after an
        # abbreviation such as "r.", "nr.", "pseud." or "krypt.", or after an
        # initial, does not end one)
        if not m:
            return ""
        ends = [x.end() for x in re.finditer(r"(?<!\br)(?<!\bnr)(?<!\bps)(?<!\bpseud)(?<!\bkrypt)(?<!\bur)(?<!\bpor)(?<!\bkpt)(?<!\bpłk)(?<!\bgen)(?<!\bewid)"
                                             r"(?<!\bpkt)(?<!\bww)(?<!\bin)(?<!\binf)(?<!\bim)(?<!\btzw)(?<!\b[A-ZŁŚŻ])[.;]\s+(?=[A-ZŁŚŻŹĆÓ\d\"„])|[.;,]?\s+[-–]\s+|\n", text)]
        a = max([x for x in ends if x <= m.start()] or [0])
        e = min([x for x in ends if x >= m.end()] or [len(text)])
        q = re.sub(r"\s+", " ", text[a:e]).strip()
        return q if not cap or len(q) <= cap else q[:cap - 3].rsplit(" ", 1)[0] + "…"
    if re.search(IPN_LUSTR, rul) and re.search(r"orzek|orzecz|wyrok|sąd", rul):
        return "court", sentence(rulings or "", re.search(IPN_LUSTR, rul))
    for p in IPN_COLLAB:
        rx, pos = re.compile(p), 0
        while True:   # every match, overlapping ones too, until one is not negated
            m = rx.search(low, pos)
            if not m:
                break
            if not re.search(IPN_NOT, sentence(records or "", m, None).lower()):
                return "collab", sentence(records or "", m)
            pos = m.start() + 1
    t = re.search(IPN_OWNFILE, low)
    if t and not re.search(IPN_ABOUT, low):
        return "ownfile", sentence(records or "", t)
    for k, pats in (("officer", IPN_OFFICER), ("candidate", IPN_CAND), ("watched", IPN_WATCHED)):
        m = hit(pats, low)
        if m:
            return k, sentence(records or "", m)
    return "unsorted", ""


def sort_cases(feats, found):
    """Splits a build into the cases kept on the layer and the records moved to rows of their own."""
    kept, moved = [], {k: [] for k in MOVED}
    for f in feats:
        p = f["properties"]
        part = p.get("part") or ""
        if part == "fara":
            p["group"] = MOVED_GROUP["fara"]
            p["how it was sorted"] = ("Moved off the Planted, bought or captured layer: a registration under the Foreign Agents Registration Act is legal and public. "
                                      "It records that someone in the US is paid to act for a foreign government, party or company, not that anyone was captured, planted or bought.")
            moved["fara"].append(f)
        elif part == "mdb_debarments" and not re.search(r"bank", f"{p.get('list', '')} {p.get('published by', '')}", re.I):
            # A government's sanctions list that came in with the banks' lists
            # (the Foreign, Commonwealth & Development Office's name has "Development" in it).
            p["group"] = MOVED_GROUP["uk_sanctions"]
            p.pop("working for or tied to", None)
            p["sanctioned by"] = p.get("published by") or p.get("list", "")
            p["note"] = ("On the UK government's sanctions list: assets frozen, travel barred or trade restricted under one of the UK's sanctions regimes "
                         "(Russia, Belarus, Iran, North Korea, terrorism and others), for the reason the list gives. A government's decision, not a court ruling.")
            p["how it was sorted"] = ("Moved off the Planted, bought or captured layer: this is the UK government's sanctions list, not a development bank's debarment list. "
                                      "It came in with the banks' lists only because the Foreign, Commonwealth & Development Office has \"Development\" in its name.")
            moved["uk_sanctions"].append(f)
        elif part == "mdb_debarments":
            p["group"] = MOVED_GROUP["debarments"]
            p["how it was sorted"] = ("Moved off the Planted, bought or captured layer: a development bank barring a firm from the projects it finances, "
                                      "after its own sanctions process, is about fraud or corruption in contracts, not about officials or companies captured, planted or bought.")
            moved["debarments"].append(f)
        elif part == "ipn":
            kind, words = ipn_reading(p.get("what the records say (IPN)", ""), p.get("rulings and prosecutors' decisions (IPN)", ""))
            p["how it was sorted"] = IPN_HOW[kind]
            p["the words it rests on (IPN)"] = words
            if kind in IPN_NOTE:
                p["group"] = TIERS["court"] if kind == "court" else TIERS["archive"]
                p["note"] = IPN_NOTE[kind]
                kept.append(f)
            else:
                p["group"] = MOVED_GROUP["ipn_watched"]
                p.pop("working for or tied to", None)
                p["note"] = IPN_HOW[kind].split(": ", 1)[1][0].upper() + IPN_HOW[kind].split(": ", 1)[1][1:]
                moved["ipn_watched"].append(f)
        else:
            kept.append(f)
    found["moved to rows of their own (round cap1w)"] = {k: len(v2) for k, v2 in moved.items()}
    return kept, moved


def write_sorted(kept, moved):
    (OUT / "cases.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": kept}, ensure_ascii=False))
    for k, name in MOVED.items():
        (OUT / name).write_text(json.dumps({"type": "FeatureCollection", "features": moved[k]}, ensure_ascii=False))


'''
    once("# ---- by country: cases found, and lawmakers found per 100 seats today -----\n", SORT + "# ---- by country: cases found, and lawmakers found per 100 seats today -----\n")
    # the box's paragraph for the UK sanctions list says what it is
    once('''    if part == "mdb_debarments":
        return (f"{name} was barred by''', '''    if part == "mdb_debarments" and p.get("sanctioned by"):
        why = _short(re.sub(r'^"|"$', "", str(p.get("list: sanctions", ""))), 600)
        return (f"{name} is on the UK government's sanctions list ({p['sanctioned by']}), which freezes assets, bars travel or restricts trade. "
                f"{'The reason the list gives: ' + why if why else 'The list gives no reason.'} A government's decision, not a court ruling.")
    if part == "mdb_debarments":
        return (f"{name} was barred by''')
    # an IPN box with no office given does not say "who held ."
    once("""return (f"{name}, who held {_short(p.get('offices held (IPN)'), 250)}. Poland's""",
         """return (f"{name}{', who held ' + _short(p.get('offices held (IPN)'), 250) if p.get('offices held (IPN)') else ''}. Poland's""")
    # last week's copies of a part are looked for in the moved files too
    once('''    before = json.loads(old.read_text())["features"] if old.exists() else []
''', '''    before = json.loads(old.read_text())["features"] if old.exists() else []
    before += [f for name in MOVED.values() if (OUT / name).exists() for f in json.loads((OUT / name).read_text())["features"]]
''')
    # sort before the boxes' paragraphs are written; count and shade from the kept cases only
    once('''    add_summaries(feats)
    old.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
''', '''    feats, moved = sort_cases(feats, found)   # round cap1w
    add_summaries(feats)
    for v2 in moved.values():
        add_summaries(v2)
    write_sorted(feats, moved)
''')
    once('''  capture/cases.geojson   group = what proves it (TIERS); branch; captor
''', '''  capture/cases.geojson   group = what proves it (TIERS); branch; captor
  capture/fara.geojson, uk_sanctions.geojson, debarments.geojson,
  ipn_watched.geojson     records that are not cases of capture, moved off the
                          layer (round cap1w), each saying how it was sorted
''')
    compile(src, str(P), "exec")
    P.write_text(src)
    print("round cap1w tiles: scripts/capture.py now sorts the layer")

# ---- sort the files already built, once, so the map is right before Monday
out = ROOT / "capture"
cases = out / "cases.geojson"
if not cases.exists():
    print("round cap1w tiles: no capture/cases.geojson yet; the next build sorts it")
    sys.exit(0)
sys.path.insert(0, str(ROOT / "scripts"))
import os
os.chdir(ROOT)
import capture  # noqa: E402

feats = json.loads(cases.read_text())["features"]
for name in capture.MOVED.values():
    if (out / name).exists():
        feats += json.loads((out / name).read_text())["features"]
found, errors = {}, []
kept, moved = capture.sort_cases(feats, found)
for v2 in moved.values():
    capture.add_summaries(v2)
capture.add_summaries([f for f in kept if f["properties"].get("part") == "ipn"])
capture.write_sorted(kept, moved)
print("round cap1w tiles: kept", len(kept), "cases; moved", found["moved to rows of their own (round cap1w)"])
bc = capture.by_country(kept, found, errors)
if bc:
    (out / "by_country.json").write_text(json.dumps(bc, ensure_ascii=False, indent=0))
    print(f"round cap1w tiles: by_country.json counted from the kept cases ({len(bc)} countries)")
else:
    print("round cap1w tiles: could not count by country now (" + "; ".join(errors) + "); the next Monday build will")
stamp = out / "build.json"
if stamp.exists():
    b = json.loads(stamp.read_text())
    b["features"] = len(kept)
    b["by_tier_and_branch"] = {}
    for f in kept:
        k = f"{f['properties']['group']} | {f['properties']['branch']}"
        b["by_tier_and_branch"][k] = b["by_tier_and_branch"].get(k, 0) + 1
    b["by_tier_and_branch"] = dict(sorted(b["by_tier_and_branch"].items()))
    b.setdefault("found", {}).update(found)
    stamp.write_text(json.dumps(b, indent=1, ensure_ascii=False))
