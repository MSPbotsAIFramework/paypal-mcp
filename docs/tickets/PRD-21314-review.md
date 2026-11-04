# PRD-21314 · Code review

## Round 1 · 2026-11-04 · reviewed b890d23 (base cf7b17e)

Verdict: changes requested

### Scope

`git diff cf7b17e...b890d23` on `MSPbotsAIFramework/paypal-mcp` (the only repo on this ticket, `Track: vendor-mcp`, `Release order: any`). 28 files changed, all new except `README.md`. Read: `docs/tickets/PRD-21314.md` (product design, tech design, self-test, handoff), `docs/tickets/PRD-21314.ac.json` (17 test cases), all of `app/`, `tests/`, `Dockerfile`, `pyproject.toml`, `README.md`.

Independently re-run (not just trusted from the self-test section):
- `uv run pytest -v` on `b890d23` → 17/17 passed, matching the self-test table.
- `grep -rnP '[\x{4e00}-\x{9fff}]' --exclude-dir=.git --exclude-dir=.venv .` on `b890d23` → **one hit**, contradicting the self-test table's "No output (clean)" (see Finding 1).
- README's "MSPbots Connector" section vs. `vendor-mcp-development/reference/readme-connector-section.md` → byte-identical (71/71 lines), positioned correctly.
- Tool catalog via `fastmcp.Client(build_mcp()).list_tools()` → exactly 10 tools; all descriptions ≤ 500 chars (max 452) and first lines ≤ 100 chars (max 89), matching the self-test table.
- `.ac.json`: 17/17 entries present, 13 `pass` with a test reference, 4 `untested` with a real-PayPal-account reason recorded — no case marked `pass` without evidence, none silently green.

### Findings

1. **[must-fix]** `docs/tickets/PRD-21314.md:643` — the repo contains Chinese text, which the vendor-mcp-development SOP (S0.4) and this track's review checklist (`references/mcp-track.md` §4.3: "README 的 Connector 段落...; 仓库里没有中文") both require to be absent, no exception carved out for doc-only occurrences. The line is a literal Chinese quote of this pipeline's own `legs/dev.md` S4 rule ("dev 可自行改[技术设计]，只要不动用户可见行为"), embedded in the "Changes from the technical design during implementation" section. The Self-test section's own claim two sections earlier — "No-Chinese scan ... No output (clean)" — is stale: it was true when that scan was run, but the doc was edited afterward (this sentence was added later in the same file) and the scan was not re-run before the doc was frozen at `Status: frozen @ 5600026`. Confirmed independently on `b890d23`: `grep -rnP '[\x{4e00}-\x{9fff}]' --exclude-dir=.git --exclude-dir=.venv .` reports exactly this one line and nothing else. Fix: rewrite the sentence in English (e.g. "the technical design's own latitude (`legs/dev.md` S4: dev may freely change the technical design as long as it does not change user-visible behavior)"), re-run the no-Chinese scan, confirm clean, and re-freeze the doc.

### Suggestions

1. **[suggestion]** `app/settings.py:24-25` — `paypal_sandbox_base_url` / `paypal_live_base_url` are declared on `Settings` but never read anywhere; `app/paypal_client.py:22-23` hardcodes its own `_SANDBOX_HOST` / `_LIVE_HOST` module constants instead. Not a must-fix (dead config surface, not a behavior bug — `X-Paypal-Environment` still correctly selects sandbox vs. live via the hardcoded constants), but the two unused settings fields should either be wired up or removed the next time this file is touched, so there is only one place that names the PayPal hosts.

### Fixes (round 1)

1. **Must-fix 1** (`docs/tickets/PRD-21314.md:643`, Chinese text / stale no-Chinese scan claim) —
   rewrote the sentence in English, matching the wording the review suggested. Added a "Review round 1
   fix" note under Self-test documenting the re-run. Commit: `649bb30` (`fix(docs): translate stray
   Chinese text in PRD-21314.md, update stale no-Chinese scan claim (PRD-21314)`). Doc re-frozen at
   `Status: frozen @ 649bb30`.
   Re-run results: `uv run pytest -v` 17/17 passed (unchanged, doc-only fix); no-Chinese scan on all
   dev-owned paths (`app/`, `tests/`, `docs/tickets/PRD-21314.md`, `docs/tickets/PRD-21314.ac.json`,
   `README.md`) is clean. The whole-repo scan still reports one hit at `docs/tickets/PRD-21314-review.md:20`
   (this file, this finding, quoting the original text verbatim) — that is this review record itself,
   frozen before this round and owned by the review leg, not dev; it is not re-litigated as a new
   must-fix.

### Not re-litigated (tech-design latitude, not a review concern)

The "Changes from the technical design during implementation" section documents several additions not named in the original file list (`app/serialize.py`, `app/tool_support.py`, `app/logging_utils.py`, the `http_app(stateless_http=True)` placement, `/health` via `@mcp.custom_route`). These are internal reuse/extraction that do not change any tool's name, parameters, or externally observable behavior, which `legs/dev.md` S4 and this ticket's own tech design explicitly leave to dev's discretion. No finding raised against them.

## Round 2 · 2026-11-04 · reviewed 9061db6 (base cf7b17e)

Verdict: approved

Status: frozen @ 9061db6

### Scope

Rework delta only, per process: `git diff b890d23...9061db6` (the round-1 fix). Two files changed, both docs: `docs/tickets/PRD-21314.md` (+23/-3) and this review record (dev-appended "Fixes (round 1)" section, +42). No code, test, dependency, or README file touched; `main` is still at `cf7b17e` (unchanged since round 1), so the baseline did not move either.

### Round-1 must-fix verification

1. **Fixed.** `docs/tickets/PRD-21314.md:643`'s Chinese sentence is rewritten in English (commit `649bb30`, carried into the re-freeze at `9061db6`). Independently re-run on `9061db6`: `grep -rnP '[\x{4e00}-\x{9fff}]' --exclude-dir=.git --exclude-dir=.venv app tests docs/tickets/PRD-21314.md docs/tickets/PRD-21314.ac.json README.md` -> no output (clean), matching the updated self-test table. The lone whole-repo hit left by the same scan without the path filter (`docs/tickets/PRD-21314-review.md:20`) is this review record's own round-1 finding text, quoting the original violation verbatim for the audit trail — it predates this round, is not dev-owned, and is not a fresh instance of the SOP violation (SOP intent is user/vendor-facing content, not a review record's documentary quote of a defect it is tracking). Not re-litigated as a must-fix.
2. `uv run pytest -v` independently re-run on `9061db6` -> 17/17 passed (0.69s), matching the self-test table and unchanged from round 1 (doc-only fix, no code touched).

### Findings

None. The round-2 diff is doc-only and limited to the must-fix fix itself; no new issue found.

### Suggestions

Carried over from round 1, still open and non-blocking (not touched this round): `app/settings.py:24-25` — `paypal_sandbox_base_url` / `paypal_live_base_url` are declared but never read; `app/paypal_client.py:22-23` hardcodes its own `_SANDBOX_HOST` / `_LIVE_HOST` constants instead. Wire up or remove the next time this file is touched.
