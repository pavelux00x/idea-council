---
name: idea-council
description: Evaluate any idea, plan or project (a business idea, a marketing campaign, a pricing change, a hiring plan, an architecture choice) with a council of several models (OpenRouter/local models + the host's own agents) in a critical, fact-based, non-sycophantic way, then deliver a short verdict with numbers, risks, an improved version and a cheap test. Use when the user types /idea-council, asks to have an idea "evaluated by the council", wants to know whether something is worth it (break-even, unit economics), what competitors do, what the evidence says, or what could go wrong. Input - a context file and a questions file (or one file with both). Built and tested on e-commerce cases; the calc template ships e-commerce economics and is adapted per case.
---

# idea-council

Usage: `/idea-council idea.md` (one file with context and questions, or two files `context.md questions.md`). The skill talks to the user before spending anything: setup on first use, then a quote, then one confirmation.

Domain: any idea complex enough to deserve several opinions; the examples below come from e-commerce marketing because the skill was built and tested there. Goal: critical and constructive thinking grounded in facts. **Never agree by default.** The council must be able to say "this does not work", and must separate what is *measured* from what is merely *claimed*.

Files of this skill (`<skill>` = the folder of this SKILL.md): `openrouter_council.py` (quote, model catalog, runs the OpenRouter/local models, validates every answer), `calc_template.py` (deterministic math), `eval_run.py` (sanity-check a finished run), `config.example.json` (template). The **user config** lives in `~/.config/idea-council/config.json` (override with `$IDEA_COUNCIL_CONFIG`): exact model ids, researchers, devil's advocate, `online_round1`, `runner`, `claude_members`, and `key_path` = the **path** of the file holding the OpenRouter key. Never read, print or copy the key: check the file only with `test -s <path>`.

Working folder for every run: `llm-council/<YYYY-MM-DD>-<slug>/` inside the current directory (`RUN` below). Council outputs follow the language of the questions. Talk to the user in their language.

## Runners (how the agents are spawned)
`runner` in the config, chosen at setup and confirmed each run:
- `herdr` (best, needs `$HC_TERMINAL_ID`): chairman and Claude members are visible Herdr tabs/panes opened with the `herdr-terminals` skill, never the in-process Agent tool.
- `agents` (no Herdr, but the host can spawn subagents): the **current session is the chairman**; the four role members run as parallel subagents with the role prompts of Phase 2 (Claude Code: `general-purpose` agents; Codex, pi or another host: its own subagent mechanism and best model); the OpenRouter script runs in Bash (background) instead of a tab. Wherever this file says "tab" or "pane", read "subagent" or "background Bash".
- `single` (no Herdr, no subagents): the current session is the chairman and the council is the OpenRouter/local models only (`claude_members: false`); the chairman still does the dossier, the checks and the verdict. Say in the report that no Claude members ran.
Auto-detect: `$HC_TERMINAL_ID` set → propose `herdr`; otherwise propose `agents` if the Agent tool exists, else `single`. The user decides.

## Architecture

```
current session ── Phase 0 preflight ──► opens tab "chairman" (Opus 5.5)
chairman ── Phase 1 dossier ─► tab "openrouter" (script: Sonar) + own research
         ── Phase 2/3/4 ─────► tab "openrouter" (script: 6 models, parallel)
                               tab "claude" (4 panes: Sonnet/Opus members with roles)
         ── Phase 5 ─────────► RUN/report.md
```
Council = 6 OpenRouter models of different families (diversity of bias) + 4 Claude members with roles (skeptic, market, creative, numbers). Devil's advocate = the model named in `config.json` (`devil`). Chairman = Opus 5.5.

## Phase 0a - Setup and intake (current session, before anything else)
Ask with the host's **interactive question tool** (Claude Code: `AskUserQuestion`, several questions per call, options + free text; pi or another agent: its equivalent, or numbered options in plain text if none). Write the skill's own text in English, but talk to the user in the user's language. Run the full intake on first use (no `~/.config/idea-council/config.json`) or when the user says "setup"; on later runs show the current setup in one line (runner, N OpenRouter models + N Claude members, web search on/off, researchers, AIsa yes/no) and ask only "keep it or change something?" together with the quote of Phase 0b.
1. **Opening line.** "I will set up the council once, then for every run you get a cost quote before any paid call."
2. **Keys** (plain text, not the question tool, because the answer is a path):
   - "Do you have an OpenRouter key? Put it in a file (for example `~/.config/idea-council/openrouter.key`, just the key, nothing else) and send me the path. I will never read or print it." Check with `test -s <path>`; if missing or empty, ask again. No OpenRouter → `key_path` null, `researcher: []`, local and Claude members only.
   - "Do you have an AIsa API key (paid online search for agents) and may the council use it? yes / no." Yes → `aisa: true` and the AIsa section below applies; the key is read by the `aisa` CLI/MCP itself from `AISA_API_KEY` or `~/.aisa/key`, never by the council.
3. **Environment** (one interactive call, up to 4 questions): Herdr? (auto-detected from `$HC_TERMINAL_ID`, confirm) Can I spawn subagents? Local models (Ollama/LM Studio URL + model names)? Use OpenRouter for the external members? Pick `runner` accordingly (see Runners).
4. **Council size and models** (one interactive call): how many external models (default 6, families diverse) and whether to run the 4 Claude role members (default yes with `herdr`/`agents`); web search in round 1 (default yes, costs 1-3 cents per call); which model is the devil's advocate. To pick ids: `python3 <skill>/openrouter_council.py models <filter>` lists live ids and prices; a local member is `{"slug":"...","model":"<name>","base_url":"http://localhost:11434/v1"}`. Write the config (copy `config.example.json`, drop the local example member if unused).
5. **The idea file.** Read the file(s) given. If there are no explicit questions, derive them from the idea (decisions to take, "is it worth it", what could fail) and show the numbered list to the user in the same confirmation as the quote; adapt them to the user's reply before starting.

## Phase 0b - Preflight (current session)
1. Create `RUN/00-input/`. Save the questions to `questions.md`. Split the context in two files:
   - `context-facts.md`: who we are, past campaigns and results, revenue, goals, product data.
   - `context-opinions.md`: fears, perceived strengths, team convictions (these are claims, not facts).
2. Break every question into sub-decisions (e.g. full AI vs hybrid, is the tool worth it, does the budget suffice, how does the target react). Write them into `questions.md` as numbered questions.
3. Missing data: ask the user **only for budget and margin** if absent. Everything else becomes an explicit assumption (flagged "assumed" in the output).
4. Copy `calc_template.py` to `RUN/01-calc/calc.py`, adapt it to the questions (tool/production costs, specific scenarios) and run: `python3 RUN/01-calc/calc.py RUN budget=.. margin=.. aov=.. ship=.. fixed=.. reso=.. roas=..`. Output: `01-calc/results.md`. **The script does the math, never the models.** If the context has several ROAS values (yearly average and a seasonal figure such as last Christmas), pass them **all** (`roas=2.1,2.8`), and pass the return rate (`reso`) when known: a single ROAS or a forgotten return rate can flip the verdict.
5. **Quote before spending.** Run `python3 <skill>/openrouter_council.py RUN estimate` (no key, no model call): it prints and saves `00-input/quote.md` with the exact model ids, live catalog prices and an indicative range (typically 0.5-0.9 USD per pass with the default council and web search; ±50%; local members cost 0). Show the user the total line, the model list and the numbered questions, and ask one question: "Proceed (about $X-$Y of OpenRouter, plus Claude time and any AIsa searches)? You can drop a member, turn off web search or change a question." Apply the changes (re-run `estimate` if models changed). This is the only confirmation of the run. Stop if they say no.
6. Hand over to the chairman. Runner `herdr`: open the chairman tab as below. Runner `agents`/`single`: you are the chairman, continue with Phases 1-5 yourself (Claude members as subagents in `agents`, none in `single`). (the task must contain everything; a later `hc send` to a booting agent can be dropped):
```sh
herdr-app do tab.new '{"name":"chairman","folder":"<cwd>","argv":["claude","--model","claude-opus-5-5"],"task":"You are the chairman of idea-council. Read ~/.claude/skills/idea-council/SKILL.md and run Phases 1-5 on RUN=<absolute path> (preflight is done: do not repeat it, do not ask the user anything). Log every problem in RUN/test-log.md. When finished run: hc send <session terminal id> \"chairman: report ready in <RUN>\" (or the reason you are blocked)."}'
```
Tell the user the tab and `RUN`, then stop: the chairman does the rest. The chairman's terminal id is its own `$HC_TERMINAL_ID`: it must pass it to the Claude members so they can `hc send` back. (Runner `agents`: members report by returning their answer; runner `single`: skip the Claude member steps.)

## Local skills and tools (chairman and Claude members, optional)
Before researching or analysing, each Claude agent checks cheaply whether a local skill or tool can help:
1. Look at the skills available (Skill tool listing and/or `grep -h '^description:' ~/.claude/skills/*/SKILL.md`). Read **descriptions only**, not whole files.
2. If a description clearly matches a concrete need (competitor analysis, social outlier posts, deep research, CRO of a page, campaign plan, benchmark), load it with the Skill tool and use it. If it is doubtful or only "for completeness", skip it.
3. Never use heavy or out-of-scope skills (video rendering, design, publishing, sending email, edits to stores/ads, anything that acts on the outside world), and never skills that write outside `RUN/`.
4. Skills help find facts and reason; they do not replace the dossier, the calculations or the answer format. Facts found through a skill still need a source.
5. Record which skills were considered, which were used and why (in `RUN/test-log.md`, or a final line `Skills used: ...` in the member's answer file). If none helps, write "none useful".

### Unrestricted online research (chairman, and Claude members if they need extra facts)
Read-only research is allowed freely, without asking: WebSearch, WebFetch, the `agent-reach` skill, and **AIsa**. Never post, comment, log in or send anything.
- **AIsa** (only if `aisa: true` in the config) is a paid, quote-first online search/data tool for agents (including social networks); the user authorised its use at setup. Prefer the **AIsa MCP tools** (`mcp__aisa__*`, configured globally; find them with ToolSearch "aisa") and fall back to the CLI `aisa` (`/opt/homebrew/bin/aisa`, key from `AISA_API_KEY` or `~/.aisa/key`; never print it). Sequence: `search` → `schema` (if `has_full_schema=false`) → `quote` → `call`; reuse the `session_id` returned by search. CLI body uses `calls`: `aisa quote --input '{"calls":[{"call_id":"c1","tool":"<tool>","arguments":{...}}]}' --json`, then `aisa call` with the same body. See `aisa --help` / `aisa quote --help`.
- **Always quote before calling** (the tool requires it), and log the costs in `test-log.md`. There is no spending cap, but `aisa balance` shows the credit.
- In the first test, generic `web.search` queries through AIsa returned off-topic results: use targeted queries and verify sources.
- If AIsa is unavailable or out of credit, fall back to the other tools and say so in the log. Never invent results.
- External queries stay generic (product, format, platform, market): no revenue figures, names of people or private client data in a query.

## Chairman quality control (applies to every phase)
The chairman is the quality gate, not a scribe. Rules:
1. **Mechanical checks are automatic**: the script rejects a round-1/round-2 answer that does not answer every question, lacks a verdict line, is too short, refers back to a previous round, or never uses the break-even ROAS; it retries once with the list of problems, then marks the member `weak` in `RUN/status/`. Never use a `weak`, `truncated` or `error` answer silently.
2. **Semantic checks are yours.** After each round, read every answer (OpenRouter and Claude members) and look for: arithmetic that contradicts `01-calc/`, a claim that cites an F#/N# which does not say that, a changed verdict without a stated reason, generic advice not tied to the questions, invented tools/prices/competitors. Also run `python3 <skill>/eval_run.py RUN` after round 2.
3. **A wrong answer gets re-done, not averaged.** Re-run the member with a precise note: `python3 <skill>/openrouter_council.py RUN round2 --only <slug> --note "<what is wrong and what to fix>"` (for Claude members: `hc send` the same note to their pane). Max 2 re-runs per member per phase; after that discard the answer and say so in the report. Log every re-run and its reason in `test-log.md`.
4. **Judge by evidence, not by vote count.** The chairman may side with one dissenting member if its facts are stronger; a 9-1 split is not an argument.
5. **Models are named exactly.** The report lists every model id actually used (from `status/*.json`), with retries and the ones discarded.

## Phase 1 - Fact dossier (chairman)
- Open tab `openrouter` and run the researchers: `herdr-app do tab.new '{"name":"openrouter","folder":"<cwd>","argv":["python3","<skill>/openrouter_council.py","<RUN>","dossier"],"task":""}'` (verified: a script runs in the tab and its output is visible; the tab stays open as a shell afterwards, so reuse it for later phases with `hc send <terminal> "<command>"`). Without Herdr: run the same command with Bash in the background. No researcher configured: skip, the dossier is yours alone.
- Meanwhile research yourself on the five points: (1) who already does this (Meta Ad Library, TikTok Creative Center, YouTube, competitors), (2) results: **claimed by the brand/vendor** vs **independently measured**, (3) format saturation and open gaps, (4) platform rules (AI-content labels on Meta/TikTok, consumer-protection rules), (5) the user's own data from `context-facts.md`.
- Merge with `02-dossier/sonar*.md` (one file per researcher in `config.json`) into `RUN/02-dossier/dossier.md`: about 15 facts per idea at most, ids `F1..`, each with **source URL, date, confidence, claimed/measured**. No source = "unverified". Check Sonar's sources before trusting them (pages can be unreadable or dates inconsistent: keep only facts confirmed elsewhere).

## Phase 2 - Round 1, blind (facts and calculations only, NO opinions)
- Tab `openrouter`: `python3 <skill>/openrouter_council.py RUN round1`. With `online_round1: true` in `config.json` the OpenRouter members get web search (`:online`, about 1-3 cents per call) and list new facts as `N#` under `## New facts`. Google-grounded answers (Gemini) return redirect URLs, not the real page: resolve them (`curl -sI <url> | grep -i location`) or treat them as unverified.
- Tab `claude`: first member via `tab.new` (name `claude`), the others as split panes with `herdr-app do terminal.open '{"place":"right","argv":["claude","--model","claude-sonnet-5-5","<FULL PROMPT>"]}'`. Verified: `terminal.open` does NOT accept `task` (only argv/folder/place/name): the prompt goes as the last element of `argv`, after the flags. In `zsh`, build the argv carefully (no unquoted word-splitting). Roles:
  - `claude-skeptic` (sonnet 5.5): skeptic, looks for what fails.
  - `claude-market` (sonnet 5.5): competitors, saturation, audience, platform rules.
  - `claude-creative` (opus 5.5): creative/production, hybrid vs full AI, honesty of the format.
  - `claude-numbers` (opus 5.5): economics, scenarios, break-even ROAS, what would have to be true.
  Each member task: read ONLY `RUN/00-input/questions.md`, `context-facts.md`, `01-calc/`, `02-dossier/` (**never** `context-opinions.md`); answer **every** numbered question in the answer format below; write `RUN/03-round1-blind/<role>.md` and `RUN/status/round1-<role>.json` `{"state":"done"}`; then `hc send <chairman terminal> "done <role>"`. No other files. Members apply the "Local skills and tools" section.
- Wait with `hc wait` / `RUN/status/`. A model that failed after its retry, or `truncated`, is reported in the log and the report: never invent its answer. Re-run a phase for one model with `--only <slug>`. Slow "thinking" models can take 4+ minutes: wait for them.

## Phase 3 - Round 2, with full context
First, fold the verified `N#` facts from round 1 (OpenRouter and Claude members) into `dossier.md` as new `F#` entries, marked "found by member <slug>"; discard the ones whose URL does not confirm them. Round 2 has no web search: it judges the given material.
Same as Phase 2 but members also read `context-opinions.md` and their own round 1; output in `04-round2-context/`. Instruction: "rewrite the complete answer to all questions; if you change verdict, say why: a new fact or only the team's opinions?". OpenRouter: `... round2`. Claude members may start round 2 as soon as their own round 1 is done.

## Phase 4 - Anonymous cross-review
`python3 <skill>/openrouter_council.py RUN review` → `05-review-anon/` (+ `mapping.json`, letter → author, only for the chairman). Reviewers rank the answers and name each one's weakest claim.

## Phase 5 - Verdict (chairman)
Read everything. Compare round 1 and round 2: a member who changes verdict only because of the team's opinions is a **sycophancy signal**: write it down. Do not write "great idea" without listing the facts that support it. Mention arithmetic errors or unsupported claims found in the review. Write `RUN/report.md`, **at most one page per question**, easy to read (short tables and lists, verdict first):
```
# <title> - <date>
## Verdict per question: GO / NO-GO / GO WITH CHANGES  (score x/10, confidence)
**In one sentence:** ...
## Numbers  (from 01-calc: break-even ROAS, scenarios, "assumed" inputs, what is NOT modelled)
## Facts that matter  (F#, source, claimed/measured)
## Load-bearing assumptions, ranked  (3-5: claim / fails if... / kill criterion / cheapest test; rank by impact x likelihood x cheapness to test)
## What is well-reasoned  (do not manufacture doubt: say plainly what holds up and why)
## Improved version of the idea  (e.g. mix of original creative + AI)
## Minimal test  (budget, duration, stop threshold, scale threshold)
## Where the council disagrees / changed its mind  (and who the chairman sided with, and why)
## What the council could not assess  (missing data, unverified claims)
## Costs and notes  (costs.json + quote.md vs actual, AIsa costs, exact model ids, re-runs, discarded answers)
```
Then run `python3 <skill>/eval_run.py RUN` and report its result honestly. Finally send the short summary to the user with the path to `report.md`, and offer an Artifact or Notion page built from it.

## Member answer format
Per numbered question: strongest evidence for, strongest evidence against, the load-bearing assumption and a falsifiable "fails if ...", verdict (GO / NO-GO / GO WITH CHANGES + score 1-10), improved version + cheapest test with a kill criterion. Every claim cites an `F#` or is marked `[unverified]`. Max ~300 words per question. Answers must stand alone (no "see round 1").

## Notes
- Costs: about 0.5-1 USD of OpenRouter per full run with web search and two researchers (see `costs.json`); set `online_round1: false` or the cheaper models to spend less; Claude members use the user's Claude Code allowance.
- If `status/*.json` says `truncated`, the answer is cut: re-run with `--only <slug>` or discard it and say so in the report.
- Weak models can be replaced in `config.json` after the first runs; keep families different. Check ids and prices with the `estimate` phase (it warns about ids missing from the catalog).
- Quote vs actual: `estimate` assumes ~450 output tokens per question and 3x for reasoning models; GPT 5.6 Terra and Sonar Reasoning Pro land near the top of the range.
- Never print or copy the OpenRouter or AIsa keys into files, logs or reports.
