#!/usr/bin/env python3
"""
A look inside Portfolio Earth's reports, so the Culprits map can place their
banks and figures (the site offers no data file, only PDFs). Saves, for each
PDF, its text page by page and every word with its position, under probe/pe/.
Nothing is published to the map from this; it is read in the next round to
write the builder, as bocc_probe.py was for Banking on Climate Chaos.

Run once (by name); it does nothing when its files are already there.
"""
import json, pathlib, subprocess, sys, time, urllib.request

PDFS = {
    "bankrolling_extinction_report": "https://portfolio.earth/wp-content/uploads/2021/01/Bankrolling-Extinction-Report.pdf",
    "bankrolling_extinction_figure1": "https://portfolio.earth/wp-content/uploads/2020/12/Figure-1.pdf",
    "subsidising_extinction_report": "https://portfolio.earth/wp-content/uploads/2021/11/Portfolio-Earth_Subsidising-Extinction.pdf",
}
OUT = pathlib.Path("probe/pe")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; github.com/WelcomeToYourGalaxy)"}


def main():
    try:
        import pdfplumber  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pdfplumber"], check=True)
    import pdfplumber
    OUT.mkdir(parents=True, exist_ok=True)
    for name, url in PDFS.items():
        if (OUT / f"{name}.words.json").exists():
            print(f"  {name}: already read")
            continue
        pdf = OUT / f"{name}.pdf"
        for i in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
                    pdf.write_bytes(r.read())
                break
            except Exception as e:  # noqa: BLE001
                print(f"  {name}: {e}", flush=True)
                time.sleep(20 * (i + 1))
        if not pdf.exists():
            continue
        pages, words = [], []
        with pdfplumber.open(pdf) as doc:
            for n, p in enumerate(doc.pages, 1):
                pages.append(f"===== page {n} =====\n{p.extract_text() or ''}")
                words.append({"page": n, "width": p.width, "height": p.height,
                              "words": [[w["text"], round(w["x0"], 1), round(w["top"], 1), round(w["x1"], 1), round(w["bottom"], 1)]
                                        for w in p.extract_words(keep_blank_chars=False, use_text_flow=False)]})
        (OUT / f"{name}.txt").write_text("\n".join(pages))
        (OUT / f"{name}.words.json").write_text(json.dumps(words))
        print(f"  {name}: {len(pages)} pages read", flush=True)


if __name__ == "__main__":
    main()
