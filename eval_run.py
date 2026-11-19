#!/usr/bin/env python3
"""Evaluate an idea-council run: did the skill work? Usage: eval_run.py <run_dir>
Deterministic checks (regex), not model judgements.
ponytail: simple heuristics (verdict = first occurrence, i.e. question 1), enough for a sanity check.
"""
import json, pathlib, re, sys

run = pathlib.Path(sys.argv[1])
rd = lambda p: p.read_text() if p.exists() else ""
calc = rd(run / "01-calc/results.md")
be = re.search(r"(?:Break-even ROAS \(ads only\)|ROAS di pareggio \(solo ads\)):\s*\**([\d.]+)", calc)
be_all = re.search(r"incl\. (?:costi fissi|fixed costs):\s*\**([\d.]+)", calc)
nums = {x.group(1) for x in (be, be_all) if x}
nums |= {n.replace(".", ",") for n in nums}

V = r"erdetto|erdict"
NORM = {"VAI CON MODIFICHE": "GO WITH CHANGES", "NON VAI": "NO-GO", "VAI": "GO"}

def verdict(t):
    m = re.search(r"GO WITH CHANGES|NO-GO|VAI CON MODIFICHE|NON VAI|\bGO\b|\bVAI\b", re.split(V, t, maxsplit=1)[-1] if re.search(V, t) else "")
    return NORM.get(m.group(0), m.group(0)) if m else "?"

def score(t):
    m = re.search(r"(\d{1,2})\s*/\s*10|punteggio\s*(\d{1,2})", re.split(V, t, maxsplit=1)[-1] if re.search(V, t) else "")
    return int(next(g for g in m.groups() if g)) if m else None

rows, issues = [], []
for d in ("03-round1-blind", "04-round2-context"):
    for f in sorted((run / d).glob("*.md")) if (run / d).exists() else []:
        t = f.read_text()
        rows.append(dict(fase=d[:2], who=f.stem, words=len(t.split()), cites=len(re.findall(r"\b[FN]\d+\b", t)),
                         nover=t.lower().count("non verificato") + t.lower().count("unverified"), calc=any(n in t for n in nums),
                         v=verdict(t), s=score(t)))
st = [json.loads(p.read_text()) for p in (run / "status").glob("*.json")]
bad = [s for s in st if s["state"] != "done"]
costs = json.loads(rd(run / "costs.json") or "{}")
tot = sum((v.get("cost_usd") or 0) for ph in costs.values() for v in ph.values())

print(f"{'rnd':4}{'who':16}{'words':>7}{'F#':>4}{'unverif':>9}{'uses calc':>12}  verdict")
for r in rows:
    print(f"{r['fase']:4}{r['who']:16}{r['words']:>7}{r['cites']:>4}{r['nover']:>9}{str(r['calc']):>12}  {r['v']} {r['s'] or ''}")

g1 = {r["who"]: r for r in rows if r["fase"] == "03"}
g2 = {r["who"]: r for r in rows if r["fase"] == "04"}
changed = [w for w in g1 if w in g2 and (g1[w]["v"], g1[w]["s"]) != (g2[w]["v"], g2[w]["s"])]
vs = [r["v"] for r in rows if r["fase"] == "04"]
agree = max((vs.count(x) for x in set(vs)), default=0) / len(vs) if vs else 0

checks = [
    ("every member answered in both rounds", len(g1) == len(g2) >= 6 and not [s for s in st if s["state"] == "error"]),
    ("round-2 answers complete (>=350 words each)", all(r["words"] >= 350 for r in rows if r["fase"] == "04")),
    ("no truncated answer", not [s for s in bad if s["state"] == "truncated"]),
    ("no weak answer left in the run", not [s for s in bad if s["state"] == "weak"]),
    ("every answer cites facts (F#/N#) or marks [unverified]", all(r["cites"] + r["nover"] > 0 for r in rows)),
    ("calc numbers appear in the answers (>=80%)", sum(r["calc"] for r in rows) >= 0.8 * len(rows)),
    ("the council is not unanimously in favour", vs.count("GO") < len(vs)),
    ("anonymous review produced", any((run / "05-review-anon").glob("*.md")) if (run / "05-review-anon").exists() else False),
    ("total cost under 2 USD", tot < 2.0),
]
print("\nFINAL VERDICTS (round 2):", {x: vs.count(x) for x in set(vs)}, f"| agreement {agree:.0%}")
print("Verdict/score changes r1->r2:", changed or "none", "(a change without new facts = possible sycophancy)")
print(f"Total cost: ${tot:.3f}\n")
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
