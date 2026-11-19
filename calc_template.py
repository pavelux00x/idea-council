#!/usr/bin/env python3
"""Calculation template: copy to <run>/01-calc/calc.py, adapt to the questions, run.
Usage: calc.py <run_dir> budget=3000 aov=45 margin=0.55 ship=6 fixed=300 reso=0.09 roas=2.1,2.8
roas: one or more reference ROAS values (yearly average AND seasonal figure, e.g. last Christmas): if the context has two, pass both.
reso: return rate (0.09 = 9%), reduces the margin: do not omit it if the context reports it.
Parameters not passed => assumptions flagged '(assumed)' in the output. NEVER assume budget or margin.
ponytail: simple linear model (no saturation/seasonality effects), enough for a go/no-go.
"""
import pathlib, sys

run = pathlib.Path(sys.argv[1])
given = dict(a.split("=") for a in sys.argv[2:])
defaults = {"aov": 40.0, "ship": 6.0, "fixed": 0.0, "reso": 0.0}
for need in ("budget", "margin"):
    if need not in given:
        sys.exit(f"missing {need}: ask the user")
p = {k: float(given.get(k, v)) for k, v in defaults.items()}
roases = [float(x) for x in given.get("roas", "1.8").split(",")]
p["budget"], p["margin"] = float(given["budget"]), float(given["margin"])
tag = lambda k: "" if k in given else " (assumed)"

contrib = (p["aov"] * p["margin"] - p["ship"]) / p["aov"] * (1 - p["reso"])  # contribution margin per euro of revenue, net of returns
if contrib <= 0:
    sys.exit("margin after shipping/returns <= 0: the idea can never pay back, report it")
be_roas = 1 / contrib
lines = ["# Calculations (deterministic script)", "",
         f"- ad budget: {p['budget']:.0f}{tag('budget')}",
         f"- average order value: {p['aov']:.2f}{tag('aov')}; gross margin: {p['margin']:.0%}; shipping: {p['ship']:.2f}{tag('ship')}",
         f"- return rate: {p['reso']:.0%}{tag('reso')}",
         f"- extra fixed costs (tools+production): {p['fixed']:.0f}{tag('fixed')}",
         f"- reference ROAS: {', '.join(map(str, roases))}{tag('roas')}",
         f"- contribution margin per euro of revenue: {contrib:.1%}",
         f"- **Break-even ROAS (ads only): {be_roas:.2f}**",
         f"- Break-even ROAS incl. fixed costs: {(1 / contrib) * (1 + p['fixed'] / p['budget']):.2f}",
         f"- Max sustainable CPA: {p['aov'] * contrib:.2f}", "",
         "| ref. ROAS | scenario | ROAS | revenue | net profit | orders |", "|---|---|---|---|---|---|"]
for base in roases:
    for name, f in (("pessimistic", 0.6), ("base", 1.0), ("optimistic", 1.4)):
        r = base * f
        rev = p["budget"] * r
        lines.append(f"| {base} | {name} | {r:.2f} | {rev:.0f} | {rev * contrib - p['budget'] - p['fixed']:.0f} | {rev / p['aov']:.0f} |")
out = run / "01-calc"
out.mkdir(exist_ok=True)
(out / "results.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
