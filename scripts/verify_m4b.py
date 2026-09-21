"""Check M4b — the public "about the data" page — against what the plan promised.

    python scripts/verify_m4b.py

The same shape as `verify_m2.py` and `verify_m4c.py`: one line per requirement,
PASS or FAIL, with what was found. Three kinds of check:

  * every promised TOPIC is present — the plan's M4b list, as phrases the page must
    contain (a topic is a thing a reader is told, so the check is for the telling,
    not for a heading);
  * every EXTERNAL LINK resolves — an `href` that 404s is a promise the page breaks
    in front of the reader. The repository link is expected to fail until the
    going-public checklist's step 9 (the settings click), and this is the one check
    that can see the result of that click, so it runs afterwards too;
  * the ACCURACY section carries measured figures, not the "not yet measured"
    placeholder it shipped with.

M4c's figure gate covers "every number is accounted for"; this covers "every
promised topic is there". Neither substitutes for the other.
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sensisat.config import ROOT  # noqa: E402

PAGE = ROOT / "viewer" / "about-the-data.html"
results: list[tuple[str, bool, str]] = []


def report(name: str, ok: bool, what: str) -> None:
    results.append((name, ok, what))
    print(f"  {'PASS' if ok else 'FAIL':4s}  {name:<28} {what}")


#: The plan's M4b list. Each requirement is met when EVERY phrase in its tuple
#: appears in the page text (tags removed, case-insensitive). Phrases are chosen to
#: be the substance of the point, not a heading someone could keep while gutting it.
TOPICS: dict[str, tuple[str, ...]] = {
    "ladder of definitions": ("CORINE", "WSF Evolution", "Imperviousness", "Impervious Built-Up", "GHSL", "cadastre"),
    "extent vs surface": ("extent", "surface", "Fuerteventura", "Gran Canaria"),
    "the 2015/2016 seam": ("2016", "nothing was demolished", "do not add"),
    "the undated class": ("no year", "own colour"),
    "pre-1980 buckets": ("1980", "1900", "round year"),
    "growth-only encoding": ("disappear", "loss"),
    "greenhouses": ("greenhouse", "separately"),
    "per-island quality": ("La Gomera", "El Hierro"),
    "accuracy with interval": ("times in 100", "±"),
    "licences and attribution": ("licence", "CC BY 4.0", "attribution"),
    "how to cite": ("How to cite", "accessed [date]", "Lovagnini"),
    "link to the scripts": ("github.com/LucaLovagnini/sensi-sat",),
}
PLACEHOLDERS = ("not yet measured", "TODO", "TBD", "lorem")


def page_text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def resolves(url: str, timeout: float = 10) -> tuple[bool, str]:
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "sensisat-verify-m4b/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status < 400, str(r.status)
    except urllib.error.HTTPError as e:
        return False, str(e.code)
    except Exception as e:  # DNS, TLS, timeout — all "the reader cannot get there"
        return False, type(e).__name__


def main() -> int:
    print("M4b — the public page: promised topics, working links, real figures\n")
    html = PAGE.read_text()
    text = page_text(html)
    low = text.lower()

    for topic, phrases in TOPICS.items():
        missing = [p for p in phrases if p.lower() not in low]
        report(topic, not missing, "present" if not missing else f"missing: {', '.join(missing)}")

    # whole words, case-sensitive: "Todoque" is a town on La Palma, not a TODO
    found = [p for p in PLACEHOLDERS if re.search(rf"\b{re.escape(p)}\b", text)]
    report("no placeholders", not found, "none" if not found else f"found: {', '.join(found)}")

    links = sorted(set(re.findall(r'href="(https?://[^"]+)"', html)))
    for url in links:
        ok, status = resolves(url)
        note = status
        if not ok and "github.com/LucaLovagnini/sensi-sat" in url:
            note += "  (expected until the repository is public — checklist step 9)"
        report("link " + re.sub(r"^https?://", "", url)[:20], ok, note)

    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    if failed:
        print("  failing: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
