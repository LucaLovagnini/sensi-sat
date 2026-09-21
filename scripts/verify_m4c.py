"""Check M4c — figure provenance — against its acceptance criteria, as written in the plan.

    python scripts/verify_m4c.py

The same shape as `verify_m2.py`: each criterion is a line, PASS or FAIL, with the
measured value beside it, so a reader can see what was checked rather than that
"everything passed". Criteria a person must perform are printed as RECORDED with
what is on file, never as PASS — a recorded attestation is not a verified one.

Numbering follows the plan's M4c "Verification" section (criteria 1–22).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sync_docs import DOCUMENTS, PRELUDE, render_facts_js  # noqa: E402

from sensisat import figures as g  # noqa: E402
from sensisat.config import ROOT  # noqa: E402
from sensisat.provenance import HISTORICAL  # noqa: E402

PAGE = ROOT / "viewer" / "about-the-data.html"
GATE = ROOT / "tests" / "test_documented_numbers.py"
results: list[tuple[str, str, str]] = []


def report(n: str, ok: bool | None, what: str) -> None:
    verdict = "RECORDED" if ok is None else ("PASS" if ok else "FAIL")
    results.append((n, verdict, what))
    print(f"  {verdict:8s} {n:>4}  {what}")


def run(*cmd: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          env={**os.environ, **(env or {})})


def main() -> int:
    print("M4c — figure provenance: acceptance criteria\n")
    page = PAGE.read_text()

    # A. Nothing unaccounted for --------------------------------------------------
    gate = run(sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(GATE))
    summary = gate.stdout.strip().splitlines()[-1] if gate.stdout.strip() else gate.stderr[-200:]
    report("1", gate.returncode == 0, f"the whole gate: {summary}")

    doctored = g.figures_in(page.replace("</p>", " Another 42.7 km² here.</p>", 1), html=True) - set(HISTORICAL)
    clean = g.figures_in(page, html=True) - set(HISTORICAL)
    report("2", doctored == {"42.7 km²"} and not clean,
           f"adding '42.7 km²' to the page is named ({sorted(doctored)}); the page as it is has {len(clean)} unaccounted")

    present = set().union(*g.token_level_figures().values())
    some_key = next(k for k in HISTORICAL if k in present)
    without = present - (set(HISTORICAL) - {some_key})
    dead = {"999 km²"} - present
    report("3", without == {some_key} and dead == {"999 km²"},
           f"deleting the registry entry {some_key!r} leaves it unaccounted; an entry for '999 km²' would be dead")

    # B. Exceptions stay narrow ---------------------------------------------------
    swallowed = []
    for rel in g.PROSE_SURFACES:
        text = (ROOT / rel).read_text()
        for m in g.TOKEN.finditer(g._prose(text, html=rel.endswith(".html"))):
            tok = m.group().strip()
            if re.search(r"(km²|km2|m²|MiB|%|×)$", tok) and g.YEAR.match(tok):
                swallowed.append((rel, tok))
    report("4", not swallowed, f"no exception matches a token carrying a unit, over every prose surface ({len(g.PROSE_SURFACES)} files)")

    fixtures = [("1. There is", True), ("## 3. The result", True), ("   2. nested", True),
                ("reached 12.", False), ("fell to 7.", False), ("was 1.234", False)]
    ok5 = all((next(g.TOKEN.finditer(t)).start() in {m.start(1) for m in g.LIST_MARKER_AT_LINE_START.finditer(t)}) is e
              for t, e in fixtures)
    report("5", ok5, "list-marker fixtures: '1.', '## 3.', '   2.' exempt; 'reached 12.', 'fell to 7.', '1.234' classified")

    baseline = json.loads(g.EXEMPTIONS_BASELINE.read_text())
    now = g.current_exemptions()
    report("6", baseline == now, f"exemption counts equal tests/fixtures/figure_exemptions.json ({sum(sum(v.values()) for v in now.values())} exemptions pinned)")

    # C. One definition, many consumers -------------------------------------------
    stats_path = ROOT / "data" / "processed" / "statistics" / "layers.json"
    if stats_path.exists():
        stats = json.loads(stats_path.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            perturbed = Path(tmp) / "layers.json"
            for isl in stats["settlement-era-a"].values():
                isl["properties"]["pre-2016, undated"] *= 1.5          # one fact moves…
            perturbed.write_text(json.dumps(stats))
            env = {"SENSISAT_STATS": str(perturbed)}
            js_moved = run(sys.executable, "-c", "from sync_docs import render_facts_js; print(render_facts_js())",
                           env={**env, "PYTHONPATH": f"{ROOT}/scripts:{ROOT}"}).stdout != render_facts_js()
            page_moved = run(sys.executable, "-m", "cogapp", "-p", PRELUDE, "--check", str(PAGE), env=env).returncode != 0
            stac_moved = run(sys.executable, "-c",
                             "import json,sys; from sensisat import catalog, layers, facts; "
                             "spec=layers.LAYERS['settlement-era-a']; "
                             "st=facts.stats(); isl=st['settlement-era-a']['Gran Canaria']; "
                             "print(catalog._description_values(spec, isl['properties'], st)['undated_pct'])",
                             env={**env, "PYTHONPATH": str(ROOT)}).stdout.strip()
            real = run(sys.executable, "-c",
                       "import json,sys; from sensisat import catalog, layers, facts; "
                       "spec=layers.LAYERS['settlement-era-a']; "
                       "st=facts.stats(); isl=st['settlement-era-a']['Gran Canaria']; "
                       "print(catalog._description_values(spec, isl['properties'], st)['undated_pct'])",
                       env={"PYTHONPATH": str(ROOT)}).stdout.strip()
        report("7", js_moved and page_moved and stac_moved != real and stac_moved != "",
               f"one perturbed statistics file moves the page (cog --check stale: {page_moved}), the viewer module "
               f"({js_moved}) and the STAC template (Gran Canaria {real} % -> {stac_moved} %) together")
    else:
        report("7", False, "no statistics on disk — run scripts/build.py --all")

    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "page.html"
        copy.write_text(re.sub(r"(<!--\[\[\[cog cog\.out\(f\"\{f\.dated_share\(\):\.1f\} %\"\) \]\]\]-->\s*)([\d.]+ %)",
                               lambda m: m.group(1) + "12.3 %", page, count=1))
        rc = run(sys.executable, "-m", "cogapp", "-p", PRELUDE, "--check", "--diff", str(copy)).returncode
    report("8", rc == 5, f"a doctored generated figure fails `cogapp --check` (exit {rc}, 5 = stale)")

    markers = [p.name for p in (ROOT / "viewer" / "app.js", ROOT / "sensisat" / "layers.py") if "[[[cog" in p.read_text()]
    report("9", not markers, "no cog marker inside app.js or layers.py (a marker in a string renders; cog cannot parse ']]]')")

    items = sorted((ROOT / "data/processed/settlement-era-a").glob("*/settlement-era-a-*.json"))
    per_island = []
    for it in items:
        d = json.loads(it.read_text())
        st = d["properties"]["sensisat:statistics"]
        stated = int(re.search(r"The (\d+) % that cannot inherit", d["properties"]["description"]).group(1))
        per_island.append(stated == round(100 * st["pre-2016, undated"] / st["footprint_km2"]))
    report("10", bool(items) and all(per_island), f"{len(items)} STAC items each state their own island's undated share from the same run")

    report("11", None, "in a browser the viewer shows the generated notes — verified in Chrome on 2026-09-21 (37 %, 2.1×, 5 main islands, 5 %)")

    # D. Collision check ----------------------------------------------------------
    allowed = {(e["file"], e["figure"]) for e in json.loads(g.COLLISIONS_ALLOWED.read_text())}
    hits = set(g.hand_typed_live_figures()) if stats_path.exists() else set()
    report("12", hits <= allowed and allowed <= hits,
           f"live values typed by hand: {len(hits)} found, all allow-listed with a reason; {len(allowed)} allow-listed, all present")

    # E. Prose rules --------------------------------------------------------------
    lint = g.quantity_words_without_digits
    ok13 = (lint("about a quarter empty", html=False) and not lint("three in ten (31 %)", html=False)
            and not lint("a third party", html=False))
    report("13", bool(ok13), "the lint fails 'about a quarter empty', passes 'three in ten (31 %)' and 'a third party'")

    problems = [p for rel in g.SECTION_SURFACES for p in g.declaration_problems((ROOT / rel).read_text())]
    fx = (g.declaration_problems("## A\n\n12 km²\n") and g.declaration_problems("## A\n<!-- figures: nope.py @ 2026-01-01 -->\n12 km²\n")
          and g.declaration_problems("# T\n\n12 km²\n\n## A\nx\n") and not g.declaration_problems("# T\n<!-- figures: scripts/build.py @ 2026-01-01 -->\n12 km²\n"))
    n_decl = sum(len(g.DECLARATION.findall((ROOT / rel).read_text())) for rel in g.SECTION_SURFACES)
    report("14", not problems and bool(fx), f"every section stating a figure declares an existing source ({n_decl} declarations, {len(g.SECTION_SURFACES)} files); undeclared, missing-file and preamble fixtures behave")

    css = (ROOT / "viewer" / "about.css").read_text()
    report("15", not re.search(r"<h2>\s*\d", page) and "counter(section)" in css,
           "page source holds no typed heading number; about.css numbers them with a counter (rendered check: Chrome, 2026-09-21)")

    # F. Evidence and enforcement -------------------------------------------------
    manifest = {e["file"] for e in json.loads(g.MANIFEST.read_text())}
    orphans = [p.name for p in g.DATA_DIR.iterdir() if p.suffix in (".csv", ".json") and p.name != g.MANIFEST.name
               and not g.code_referring_to(p.name) and p.name not in manifest]
    report("16", not orphans, f"every file in docs/figures/data is named by code or in the manifest ({len(manifest)} manifest entries)")

    build_src, pub_src = (ROOT / "scripts/build.py").read_text(), (ROOT / "scripts/publish.py").read_text()
    wired = "figure_gate()" in build_src and "return 4" in build_src and "figure_gate()" in pub_src and "review_figures.py" in pub_src
    report("17", wired, "build.py runs the gate and exits 4 on failure; publish.py runs the gate and the review check and returns 3 "
                        "(structural; the exit-3 refusal with an untouched dist/ was demonstrated by hand on 2026-09-21)")

    base = g.fingerprint()
    reworded = g.fingerprint({"viewer/about-the-data.html": page.replace("Every number on the map", "Each figure on the map", 1)})
    figured = g.fingerprint({"viewer/about-the-data.html": page.replace("</p>", " Another 42.7 km² here.</p>", 1)})
    md = (ROOT / "docs/pipeline.md").read_text()
    declared = g.fingerprint({"docs/pipeline.md": md.replace("@ 2026-09-19 -->", "@ 2026-09-20 -->", 1)})
    report("18", reworded == base and figured != base and declared != base,
           "attestation hash: unchanged by rewording, changed by one figure, changed by one declaration")

    hook = ROOT / ".githooks" / "pre-push"
    ok_now = subprocess.run([str(hook)], cwd=ROOT, capture_output=True).returncode
    backup = page
    try:
        PAGE.write_text(page.replace("</p>", " Another 42.7 km² here.</p>", 1))
        blocked = subprocess.run([str(hook)], cwd=ROOT, capture_output=True).returncode
    finally:
        PAGE.write_text(backup)
    report("19", ok_now == 0 and blocked != 0,
           f"the pre-push hook passes the current tree (exit {ok_now}) and blocks it with one added figure (exit {blocked}); "
           "against a throwaway remote it was shown to transmit nothing (2026-09-21)")

    design = ROOT / "docs" / "design" / "figure-provenance.md"
    report("20", design.exists() and str(design.relative_to(ROOT)) in g.SECTION_SURFACES and "docs/design/figure-provenance.md" in DOCUMENTS,
           "docs/design/figure-provenance.md exists, is a section-level surface of the gate, and is synced by cog")

    # G. Human steps, recorded not omitted ---------------------------------------
    review = ROOT / "docs" / "figures-review.json"
    if review.exists():
        rec = json.loads(review.read_text())
        current = rec.get("fingerprint") == base
        report("21", None, f"/verify-figures attested {rec['reviewed']} by {rec['reviewer'][:60]}… — "
                           f"{'current' if current else 'STALE'}; three judgements on file")
    else:
        report("21", None, "no /verify-figures attestation on file")
    hooks_path = subprocess.run(["git", "config", "core.hooksPath"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    report("22", None, f"core.hooksPath = {hooks_path or '(unset)'} in this clone; the going-public checklist is in CLAUDE.md")

    failed = [n for n, v, _ in results if v == "FAIL"]
    recorded = [n for n, v, _ in results if v == "RECORDED"]
    print(f"\n{len(results) - len(failed) - len(recorded)} passed, {len(failed)} failed, {len(recorded)} recorded (human)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
