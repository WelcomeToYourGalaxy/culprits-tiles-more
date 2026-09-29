#!/usr/bin/env python3
"""
Poland's IPN catalogue of people holding public office (round 110c, asked 29
September, for the Planted, bought or captured layer).

The Institute of National Remembrance publishes, for every person in an office
the lustration law covers (president, ministers, members of the Sejm and
Senate, MEPs, judges, prosecutors, mayors, heads of towns and districts...),
what the communist security services' records say about them:
https://katalog.bip.ipn.gov.pl/informacje/<number>. This reads every entry, a
slice each day (the catalogue has hundreds of thousands of numbers), and keeps
the entries whose records say more than passports:

  archive tier  registered as a secret collaborator (TW), operational contact
                (KO), agent, informer, resident, consultant or the like
  court tier    the lustration court ruled the person's declaration untrue
  alleged tier  registered only as a candidate for secret collaborator (the
                SB's term for someone it meant to recruit, not an agent)

Entries showing only passport files, "not listed", or registration for
protection or checking (not collaboration, as IPN explains) are counted in
capture/ipn_build.json but not drawn. Every field IPN prints is kept for the
entries drawn. Each is placed at the town IPN names for the office
(OpenStreetMap Nominatim), or Warsaw for national offices.

  capture/ipn.geojson      capture/ipn_state.json      capture/ipn_build.json

Daily, until every number has been read; then again from the start after 30
days. By hand: capture_ipn.
"""
import concurrent.futures as cf, datetime, html, json, os, pathlib, re, sys, time, urllib.parse, urllib.request

OUT = pathlib.Path("capture")
BASE = "https://katalog.bip.ipn.gov.pl/informacje/"
UA = {"User-Agent": "Culprits atlas build (https://github.com/WelcomeToYourGalaxy/culprits-tiles-more; welcometoyourgalaxy@gmail.com)"}
BUDGET_S = 125 * 60
WORKERS = 4
GIVE_UP_AFTER = 30000          # numbers in a row with nothing, past the highest found
WARSAW = (21.0122, 52.2297)
TIERS = {"archive": "Named in opened secret-police or spy-service files", "court": "Convicted, or found by a court",
         "alleged": "Charged or alleged, not proven"}
NATIONAL = r"sejm|senat|parlament europejski|minist|rada ministrów|prezes rady|prezydent rzeczypospolitej|prezydent rp|trybunał|sąd najwyższy|naczelny sąd|prokurator krajowy|prokuratura krajowa|najwyższa izba|narodowy bank|instytut pamięci|rzecznik praw"


def fetch(n):
    url = BASE + str(n)
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return n, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return n, None
            time.sleep(5 * (i + 1))
        except Exception:  # noqa: BLE001
            time.sleep(5 * (i + 1))
    return n, ""


def text_of(page):
    page = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", page)
    page = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", page)
    page = re.sub(r"(?i)</t[dh]>", " | ", page)
    t = html.unescape(re.sub(r"<[^>]+>", " ", page))
    return "\n".join(x for x in (re.sub(r"[ \t\xa0]+", " ", l).strip(" |") for l in t.split("\n")) if x)


def field(t, label):
    m = re.search(label + r"\s*:\s*(.+)", t)
    return m.group(1).strip() if m else ""


def between(t, a, b):
    i = t.find(a)
    if i < 0:
        return ""
    j = t.find(b, i + len(a)) if b else -1
    return t[i + len(a): j if j > 0 else None].strip()


def classify(records, rulings):
    low = records.lower()
    cand = re.search(r"kandydat\w*\s+na\s+(tajnego\s+)?współpracownik", low)
    rest = re.sub(r"kandydat\w*\s+na\s+(tajnego\s+)?współpracownik\w*", " ", low)
    agent = re.search(r"\btw\b|tajn\w*\s+współpracownik|kontakt\w*\s+operacyjn|\bko\b|\bagent\w*|informator|rezydent|konsultant\w*|osob\w*\s+zaufani|\boz\b|\bpomoc\w*\s+obywatelsk", rest)
    rul = rulings.lower()
    if re.search(r"niezgodn\w*\s+z\s+prawdą", rul) and re.search(r"orzek|orzecz|wyrok|sąd", rul):
        return "court"
    if agent:
        return "archive"
    if cand:
        return "alleged"
    return None


def branch(functions):
    f = functions.lower()
    if re.search(r"sędzi|sąd|trybunał|prokurator", f):
        return "courts"
    if re.search(r"poseł|posł|senator|sejm|senat|radn|parlament", f):
        return "lawmaking"
    if re.search(r"spółk|zarząd spółki|prezes zarządu", f):
        return "company"
    return "ruling and running"


def parse(n, page):
    t = text_of(page)
    if "Nazwisko" not in t:
        return None
    name = " ".join(x for x in (field(t, "Imiona"), field(t, "Nazwisko")) if x)
    functions = between(t, "Data objęcia funkcji", "Treść zapisów ewidencyjnych")
    records = between(t, "Treść zapisów ewidencyjnych", "Zarządzenia/Orzeczenia") or between(t, "Treść zapisów ewidencyjnych", "")
    records = re.sub(r"^Opis materiałów\s*\|?\s*Stan zachowania\s*\|?\s*Uwagi", "", records).strip()
    rulings = re.sub(r"^Treść", "", between(t, "Zarządzenia/Orzeczenia", "")).strip()
    rulings = re.split(r"\n(Biuletyn Informacji Publicznej|Redakcja|Metryka|Drukuj)", rulings)[0]
    return {"n": n, "name": name, "maiden name": field(t, "Nazwisko rodowe"), "place of birth": field(t, "Miejsce urodzenia"),
            "date of birth": field(t, "Data urodzenia"), "father's name": field(t, "Imię ojca"), "mother's name": field(t, "Imię matki"),
            "more": field(t, "Dodatkowe informacje"), "functions": functions, "records": records, "rulings": rulings,
            "tier": classify(records, rulings)}


def town(functions):
    m = re.search(r"([A-ZĄĆĘŁŃÓŚŹŻ][\w\-ąćęłńóśźż]+(?:[ \-][A-ZĄĆĘŁŃÓŚŹŻ][\w\-ąćęłńóśźż]+)*)\s*\(powiat", functions)
    if m:
        return m.group(1)
    m = re.search(r"\|\s*([A-ZĄĆĘŁŃÓŚŹŻ][\wąćęłńóśźż\-]+(?: [A-ZĄĆĘŁŃÓŚŹŻ][\wąćęłńóśźż\-]+)*)\s*\|\s*\d\d-\d\d-\d{4}", functions)
    return m.group(1) if m else ""


def geocode(name, cache):
    if name in cache:
        return cache[name]
    ll = None
    try:
        q = urllib.parse.urlencode({"q": name, "countrycodes": "pl", "format": "json", "limit": 1})
        j = json.loads(urllib.request.urlopen(urllib.request.Request("https://nominatim.openstreetmap.org/search?" + q, headers=UA), timeout=60).read())
        if j:
            ll = (round(float(j[0]["lon"]), 5), round(float(j[0]["lat"]), 5))
        time.sleep(1.1)
    except Exception:  # noqa: BLE001
        return None
    cache[name] = ll
    return ll


def main():
    OUT.mkdir(exist_ok=True)
    sp = OUT / "ipn_state.json"
    st = json.loads(sp.read_text()) if sp.exists() else {"next": 1, "highest": 0, "entries": {}, "counts": {}, "geo": {}}
    if st.get("finished"):
        if (datetime.date.today() - datetime.date.fromisoformat(st["finished"])).days < 30 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
            print("capture_ipn: every number read; next pass after 30 days")
            return
        st.update({"next": 1, "finished": None})
    started, n = time.time(), st["next"]
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        while time.time() - started < BUDGET_S:
            batch = list(range(n, n + 200))
            for num, page in ex.map(fetch, batch):
                if page is None:
                    st["counts"]["missing"] = st["counts"].get("missing", 0) + 1
                    continue
                if page == "":
                    st["counts"]["no answer"] = st["counts"].get("no answer", 0) + 1
                    st.setdefault("retry", []).append(num)
                    continue
                e = parse(num, page)
                if not e:
                    st["counts"]["not a public-office entry"] = st["counts"].get("not a public-office entry", 0) + 1
                    continue
                st["highest"] = max(st["highest"], num)
                k = e["tier"] or "records show no collaboration"
                st["counts"][k] = st["counts"].get(k, 0) + 1
                if e["tier"]:
                    st["entries"][str(num)] = e
            n += 200
            st["next"] = n
            sp.write_text(json.dumps(st, ensure_ascii=False))
            if n - st["highest"] > GIVE_UP_AFTER and st["highest"]:
                st["finished"] = datetime.date.today().isoformat()
                print(f"capture_ipn: reached {n}, {GIVE_UP_AFTER} past the highest entry ({st['highest']}); pass complete", flush=True)
                break
    st["retry"] = sorted(set(st.get("retry", [])))[-5000:]
    feats = []
    for k, e in sorted(st["entries"].items(), key=lambda kv: int(kv[0])):
        tw = town(e["functions"])
        national = re.search(NATIONAL, e["functions"].lower())
        ll = WARSAW if national or not tw else (geocode(tw, st["geo"]) or WARSAW)
        props = {"name": e["name"], "group": TIERS[e["tier"]], "branch": branch(e["functions"]),
                 "working for or tied to": "Poland's communist-era security services (SB, military counter-intelligence and others), as IPN's catalogue records",
                 "offices held (IPN)": e["functions"], "what the records say (IPN)": e["records"], "rulings and prosecutors' decisions (IPN)": e["rulings"],
                 "maiden name": e["maiden name"], "place of birth": e["place of birth"], "date of birth": e["date of birth"],
                 "father's name": e["father's name"], "mother's name": e["mother's name"], "more": e["more"],
                 "IPN entry": BASE + k, "part": "ipn",
                 "note": {"archive": "Registered by the security services as a collaborator or contact, as IPN's catalogue records. A registration is the services' record, not a court finding; the rulings box says whether a lustration court has ruled.",
                          "court": "A lustration court ruled this person's declaration of no collaboration untrue, as IPN's catalogue records.",
                          "alleged": "Registered only as a candidate for secret collaborator: someone the services meant to recruit. IPN does not count this as collaboration."}[e["tier"]],
                 "source": "Institute of National Remembrance (IPN), catalogue of people holding public office, read " + datetime.date.today().isoformat(),
                 "placed at": "Warsaw (a national office)" if national else (f"{tw}, the town IPN names for the office" if tw and ll != WARSAW else "Warsaw (no town found for the office)")}
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": list(ll)}, "properties": props})
        sp.write_text(json.dumps(st, ensure_ascii=False))
    (OUT / "ipn.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    (OUT / "ipn_build.json").write_text(json.dumps({"read": datetime.date.today().isoformat(), "next number": st["next"], "highest entry": st["highest"],
                                                     "finished": st.get("finished"), "counts": st["counts"], "drawn": len(feats)}, indent=1, ensure_ascii=False))
    print(f"capture_ipn: read to {st['next']}; {len(feats)} entries drawn; counts {st['counts']}", flush=True)


if __name__ == "__main__":
    main()
