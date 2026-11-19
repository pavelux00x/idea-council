#!/usr/bin/env python3
"""idea-council: OpenRouter runner.

Usage: openrouter_council.py <run_dir> <estimate|dossier|round1|round2|review> [--only slug,slug] [--note "chairman's correction"]
       openrouter_council.py models [filter]      list OpenRouter catalog ids with prices (to pick members)
Config: ~/.config/idea-council/config.json (per user; see config.example.json next to this script).
A member with "base_url" (e.g. Ollama http://localhost:11434/v1, LM Studio http://localhost:1234/v1) is called there
with the OpenAI chat format and no OpenRouter key; it costs 0 and never gets ":online".
estimate: cost quote (no model calls, no key needed) -> <run_dir>/00-input/quote.md
--note: appended to the prompt when the chairman re-runs one model (e.g. "Q2 contradicts the calc: break-even is 2.34").
Reads/writes files inside <run_dir>. The API key stays in the file named in config.json (never printed).
Every round-1/round-2 answer is checked (all questions, verdicts, length, calc numbers, no back-references);
a failing answer is retried once with the list of problems, then marked 'weak' in status/.
"""
import json, os, pathlib, random, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date

HERE = pathlib.Path(__file__).parent
CFG_PATH = pathlib.Path(os.environ.get("IDEA_COUNCIL_CONFIG", "~/.config/idea-council/config.json")).expanduser()
if not CFG_PATH.exists():
    sys.exit(f"no config at {CFG_PATH}: run the intake in SKILL.md (copy config.example.json there and set key_path/members)")
CFG = json.loads(CFG_PATH.read_text())
URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"  # public catalog with prices
WEB_SEARCH_USD = (0.02, 0.05)  # per :online call (OpenRouter web plugin: $4/1000 results, 5 results default; Gemini grounding ~0.03 observed)
MODEL_NAMES = r"\b(DeepSeek|Gemini|GPT[-\w.]*|ChatGPT|Qwen|Kimi|Grok|Claude|Sonar)\b"  # stripped before anonymous review

SYSTEM = """You are a member of a council that evaluates marketing ideas for an e-commerce business.
Your job is NOT to agree: it is to find what holds up and what does not.
Rules:
1) Rely only on the facts in the dossier (ids F1, F2...) and the provided calculations. Cite the id next to every claim; if there is no source write [unverified].
2) Never change the numbers in the calculations. Assumptions marked 'assumed' are uncertain.
3) A fact 'claimed' by a brand or vendor deserves skepticism (survivorship bias: you see the winners, not the losers).
4) Account for deadlines and seasonality (today is {today}).
5) Answer EVERY numbered question, one by one, using the format below. Your answer must stand alone: never refer to a previous round.
6) Concise: max ~300 words per question. No generic praise. Write in the language of the questions.
{online}Format per question:
### <question>
- Strongest evidence FOR:
- Strongest evidence AGAINST:
- Load-bearing assumption (if false, the idea dies) and "Fails if ...": (concrete, falsifiable)
- Verdict: GO / NO-GO / GO WITH CHANGES - score 1-10
- Improved version + cheapest test with a kill criterion (the threshold at which you stop):"""

ONLINE = """7) You have web search: use it to check the dossier and to find facts it lacks (competitors, prices, platform rules, measured results). A new fact gets an id N1, N2... cited in the text, and is listed at the end under '## New facts' as: N# | fact | source URL | date | claimed/measured. No URL = [unverified].
"""

DEVIL = "\nYour role: devil's advocate. Attack the idea with the strongest factual objections even if it looks good. Your verdict stays honest, but never write praise without facts."

SONAR = """Find verifiable facts, with URL and date, for these e-commerce marketing questions (Italy/target market where relevant):
1) who already does this (brands/competitors, concrete examples); 2) results: distinguish 'claimed by the brand/vendor' from 'independently measured'; 3) format saturation and open gaps; 4) platform rules (e.g. AI-content labels on Meta/TikTok); 5) real costs of tools/production.
Prefer sources from the last 12 months and say the date; include news, official platform pages and at least one practitioner/community source (Reddit, forums, case studies) when one exists.
List facts as F1, F2... with: fact | source URL | date | confidence (high/medium/low). No fact without a source. Write in the language of the questions."""


def rd(p):
    p = pathlib.Path(p)
    return p.read_text() if p.exists() else ""


def n_questions(q):
    return max(1, len(re.findall(r"^\s*\d+[.)]", q, re.M)))


def calc_numbers(calcs):
    m = re.search(r"(?:Break-even ROAS \(ads only\)|ROAS di pareggio \(solo ads\)):\s*\**([\d.]+)", calcs)  # English template or older Italian one
    return {m.group(1), m.group(1).replace(".", ",")} if m else set()


def check(text, phase, nq, nums, prev=""):
    """Deterministic completeness check of a member answer. Returns a list of problems (empty = ok)."""
    import difflib
    p = []
    if phase == "round2" and prev and difflib.SequenceMatcher(None, prev, text).ratio() > 0.9:
        p.append("round 2 is a copy of round 1: rewrite it taking the team's opinions into account and state whether your verdicts change")
    heads = len(re.findall(r"^###\s", text, re.M))
    if heads < nq:
        p.append(f"only {heads} of {nq} numbered questions have their own '### <question>' block")
    if len(re.findall(r"erdict|erdetto", text)) < nq:
        p.append("a 'Verdict: ... - score x/10' line is missing for some questions")
    if len(text.split()) < 120 * nq:
        p.append("too short: every question needs the complete format")
    if phase == "round2" and re.search(r"(see|vedi|cfr\.?|as (stated|explained|noted) in|come (detto|spiegato|indicato) (nel|al))\s+(my\s+)?(round|giro|previous|precedente)", text, re.I):
        p.append("refers back to a previous round: the answer must stand alone")
    if nums and not any(n in text for n in nums):
        p.append("the break-even ROAS from the calculations is never used")
    return p


def key():
    t = pathlib.Path(os.path.expanduser(CFG["key_path"])).read_text().strip()
    return t.split("=")[-1].strip().strip("\"'")


def call(model, system, user, k, base_url=None):
    body = json.dumps({"model": model, "max_tokens": 24000, "usage": {"include": True},  # "thinking" models (kimi, deepseek) burn 10-15k tokens reasoning before answering
                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode()
    url = (base_url.rstrip("/") + "/chat/completions") if base_url else URL  # local OpenAI-compatible server or OpenRouter
    last = None
    for attempt in range(2):  # one retry only
        try:
            req = urllib.request.Request(url, body, {"Authorization": "Bearer " + (k or "local"), "Content-Type": "application/json", "X-Title": "idea-council"})
            d = json.load(urllib.request.urlopen(req, timeout=300))
            c = d["choices"][0]["message"].get("content")
            if isinstance(c, list):
                c = "".join(x.get("text", "") for x in c)
            if not c:
                raise ValueError("empty response")
            u = d.get("usage", {})
            return c, {"tokens": u.get("total_tokens"), "cost_usd": u.get("cost"), "finish": d["choices"][0].get("finish_reason")}
        except Exception as e:  # never include request details in the message
            last = f"{type(e).__name__}: {str(e)[:200]}"
            time.sleep(3)
    raise RuntimeError(last)


def estimate(run, members, rs, online, nq, base, opinions, research_input):
    """Indicative quote before spending: catalog prices x estimated tokens. Range = low (plain answer) .. high (reasoning models, web search)."""
    cat = {m["id"]: m["pricing"] for m in json.load(urllib.request.urlopen(MODELS_URL, timeout=60))["data"]}
    tok = lambda t: len(t) // 4
    out_q, dossier_tok = 450 * nq, 4000  # ~450 output tokens per question; dossier not written yet at preflight
    rows = []  # phase, slug, model, in, out, low, high

    def add(phase, slug, model, tin, tout, web=False, local=False):
        if local:
            rows.append((phase, slug, model + " (local)", tin, tout, 0.0, 0.0)); return
        p = cat.get(model.split(":")[0])
        if not p:
            rows.append((phase, slug, model, tin, tout, None, None)); return
        pi, po = float(p["prompt"]), float(p["completion"])
        low = tin * pi + tout * po
        high = tin * pi + 3 * tout * po  # thinking models bill reasoning as output
        if web:
            low, high = low + WEB_SEARCH_USD[0], high + WEB_SEARCH_USD[1]
        rows.append((phase, slug, model, tin, tout, low, high))

    for i, r in enumerate(rs):
        add("dossier", f"sonar{'' if i == 0 else f'-{i + 1}'}", r, tok(SONAR + research_input), 2500)
    for m in members:
        loc = bool(m.get("base_url"))
        mid = m["model"] + (":online" if online and ":" not in m["model"] and not loc else "")
        add("round1", m["slug"], mid, tok(base) + dossier_tok, out_q, web=online and not loc, local=loc)
        add("round2", m["slug"], m["model"], tok(base) + dossier_tok + tok(opinions) + out_q, out_q, local=loc)
        add("review", m["slug"], m["model"], tok(base) + dossier_tok + (len(members) + 4) * out_q, 400, local=loc)
    unknown = [r for r in rows if r[5] is None]
    if not rows:
        sys.exit("config has no members")
    lo, hi = sum(r[5] for r in rows if r[5]), sum(r[6] for r in rows if r[6])
    lines = ["# OpenRouter quote (indicative, before any paid call)", "",
             f"Questions: {nq}. Members: {len(members)} ({'web search in round 1' if online else 'no web search'}). Researchers: {len(rs)}.", "",
             "| phase | member | exact model id | in tok | out tok | est. USD |", "|---|---|---|---|---|---|"]
    lines += [f"| {r[0]} | {r[1]} | `{r[2]}` | {r[3]} | {r[4]} | " + (f"{r[5]:.3f} - {r[6]:.3f}" if r[5] is not None else "unknown model id") + " |" for r in rows]
    lines += ["", f"**Total OpenRouter: about ${lo:.2f} - ${hi:.2f}** (one pass; each chairman re-run of a member adds ~1/{len(members) * 3:.0f} of this).",
              "Not included: Claude members and chairman (Claude Code plan), AIsa searches (quoted separately), re-runs.",
              "Prices from the live OpenRouter catalog at " + date.today().isoformat() + "; tokens estimated from the input files (chars/4) and ~450 output tokens per question."]
    if unknown:
        lines.append(f"\nWARNING - not in the catalog: {', '.join(sorted({r[2] for r in unknown}))}. Fix config.json before running.")
    out = run / "00-input" / "quote.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def list_models(flt=""):
    cat = json.load(urllib.request.urlopen(MODELS_URL, timeout=60))["data"]
    for m in sorted(cat, key=lambda m: m["id"]):
        if flt.lower() in m["id"].lower() and ":" not in m["id"].split("/")[-1]:
            p = m["pricing"]
            print(f"{m['id']:50} in ${float(p['prompt']) * 1e6:6.2f}/M  out ${float(p['completion']) * 1e6:6.2f}/M  ctx {m.get('context_length')}")


def main():
    if sys.argv[1] == "models":
        return list_models(sys.argv[2] if len(sys.argv) > 2 else "")
    run, phase = pathlib.Path(sys.argv[1]), sys.argv[2]
    only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else None
    note = sys.argv[sys.argv.index("--note") + 1] if "--note" in sys.argv else ""
    inp, today = run / "00-input", date.today().isoformat()
    questions = rd(inp / "questions.md")
    facts, opinions = rd(inp / "context-facts.md"), rd(inp / "context-opinions.md")
    dossier, calcs = rd(run / "02-dossier/dossier.md"), rd(run / "01-calc/results.md")
    base = f"# Questions\n{questions}\n\n# Context (facts only)\n{facts}\n\n# Fact dossier\n{dossier}\n\n# Calculations (do not modify)\n{calcs}\n"
    if note:
        base += f"\n# Note from the chairman (fix this in your answer)\n{note}\n"
    nq, nums = n_questions(questions), calc_numbers(calcs)

    jobs = []  # (slug, model, system, user, outfile)
    members = [m for m in CFG["members"] if not only or m["slug"] in only]
    online = CFG.get("online_round1", False)  # web search only in the fact round; round 2/review judge the given material
    rs = CFG.get("researcher") or []
    rs = rs if isinstance(rs, list) else [rs]  # several researchers = more facts, different biases
    sysmsg = lambda m: SYSTEM.format(today=today, online=ONLINE if online and phase == "round1" else "") + (DEVIL if m["slug"] == CFG["devil"] else "")
    model_of = lambda m: m["model"] + (":online" if online and phase == "round1" and ":" not in m["model"] and not m.get("base_url") else "")

    if phase == "estimate":
        return estimate(run, members, rs, online, nq, base, opinions, questions + facts)
    k = key() if CFG.get("key_path") else None  # no key = local members only
    if not rs and phase == "dossier":
        sys.exit("no researcher configured (no OpenRouter): the chairman writes the dossier alone")

    if phase == "dossier":
        (run / "02-dossier").mkdir(parents=True, exist_ok=True)
        jobs = [(f"sonar{'' if i == 0 else f'-{i + 1}'}", r, "You are a rigorous researcher.", SONAR + f"\n\n# Questions\n{questions}\n\n# Context\n{facts}", run / f"02-dossier/sonar{'' if i == 0 else f'-{i + 1}'}.md", None) for i, r in enumerate(rs)]
    elif phase in ("round1", "round2"):
        out = run / ("03-round1-blind" if phase == "round1" else "04-round2-context")
        out.mkdir(parents=True, exist_ok=True)
        for m in members:
            u = base
            if phase == "round2":
                u += ("\n# Team opinions and priorities (claims to verify, NOT facts)\n" + opinions +
                      "\n\n# Your round 1 answer\n" + rd(run / f"03-round1-blind/{m['slug']}.md") +
                      "\nRevise your evaluation. Rewrite the COMPLETE answer to ALL questions (do not refer back to round 1). "
                      "If your verdict changes versus round 1, say explicitly why (a new fact, or only the team's opinions?).")
            jobs.append((m["slug"], model_of(m), sysmsg(m), u, out / f"{m['slug']}.md", m.get("base_url")))
    elif phase == "review":
        out = run / "05-review-anon"
        out.mkdir(parents=True, exist_ok=True)
        files = sorted((run / "04-round2-context").glob("*.md"))
        random.Random(7).shuffle(files)
        labels = {chr(65 + i): f.stem for i, f in enumerate(files)}
        (out / "mapping.json").write_text(json.dumps(labels, indent=1))
        anon = "\n\n".join(f"## Answer {chr(65 + i)}\n{re.sub(MODEL_NAMES, '[model]', f.read_text())}" for i, f in enumerate(files))  # no vendor names: judge on merit
        task = (base + "\n# Anonymous council answers\n" + anon +
                "\n\nRank the answers from most to least solid (letters only). For each: its weakest or unsupported claim. "
                "Then: where does the council agree too easily? Max 250 words. Write in the language of the questions.")
        jobs = [(m["slug"], m["model"], sysmsg(m), task, out / f"{m['slug']}.md", m.get("base_url")) for m in members]
    else:
        sys.exit("unknown phase")

    (run / "status").mkdir(exist_ok=True)

    def work(j):
        slug, model, system, user, f, base_url = j
        st = run / "status" / f"{phase}-{slug}.json"
        st.write_text(json.dumps({"state": "running", "model": model}))
        print(f"[{slug}] started ({model})", flush=True)
        try:
            text, usage = call(model, system, user, k, base_url)
            prev = rd(run / f"03-round1-blind/{slug}.md") if phase == "round2" else ""
            problems = check(text, phase, nq, nums, prev) if phase in ("round1", "round2") else []
            if problems:  # one corrective retry with the explicit list of problems
                print(f"[{slug}] incomplete, retrying: {problems}", flush=True)
                fix = user + "\n\n# Correction required\nYour previous answer was rejected for these reasons:\n- " + "\n- ".join(problems) + "\nRewrite the COMPLETE answer, fixing every point.\n"
                text2, usage2 = call(model, system, fix, k, base_url)
                usage = {**usage2, "cost_usd": (usage.get("cost_usd") or 0) + (usage2.get("cost_usd") or 0), "tokens": (usage.get("tokens") or 0) + (usage2.get("tokens") or 0), "retried": True}
                problems = check(text2, phase, nq, nums, prev)
                if len(problems) <= len(check(text, phase, nq, nums, prev)):
                    text = text2
            f.write_text(text)
            state = "truncated" if usage.get("finish") == "length" else "weak" if problems else "done"  # cut/weak answer: chairman must re-run or discard
            usage = {"model": model, **usage, **({"problems": problems} if problems else {})}
            st.write_text(json.dumps({"state": state, **usage}))
            print(f"[{slug}] {state.upper() if state != 'done' else 'done'} {usage}", flush=True)
            return slug, usage
        except Exception as e:
            st.write_text(json.dumps({"state": "error", "model": model, "error": str(e)}))
            print(f"[{slug}] ERROR {e}", flush=True)
            return slug, {"error": str(e)}

    with ThreadPoolExecutor(len(jobs)) as ex:
        res = dict(ex.map(work, jobs))
    cf = run / "costs.json"
    costs = json.loads(cf.read_text()) if cf.exists() else {}
    costs[phase] = {**costs.get(phase, {}), **res}  # a --only re-run merges into the phase, never wipes the other members
    cf.write_text(json.dumps(costs, indent=1))
    tot = sum((v.get("cost_usd") or 0) for v in res.values())
    print(f"phase {phase} complete. cost ~${tot:.4f}. Output in {run}")


main()
