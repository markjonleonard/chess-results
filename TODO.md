# TODO

Open work on chess-results, roughly in the order it is worth doing.

## Before this goes anywhere

- [x] **CI.** Done 2026-08-09 as `.github/workflows/ci.yml`, green as of `593c298`. Two jobs
      on push to `main`, every pull request and `workflow_dispatch`: `lint` runs
      `ruff check`, `ruff format --check` and `mypy --strict` on 3.13 only; `test` runs
      `pytest` across 3.10–3.13 with `fail-fast: false`. No secrets and no network
      allowance — the suite is fixtures only.

      `mypy` was left out of the first cut because it still failed; it was added in the same
      sitting once the item below was fixed.

      **The first run failed, and the cause is worth keeping.** All four test legs passed,
      3.10 included. `lint` fell over on `ruff format --check` — which also meant `mypy`
      never ran, being the step after it. Local ruff was 0.15.12, where formatting Python
      blocks inside Markdown is experimental and gated behind preview mode; CI resolved
      `ruff>=0.5` to 0.16.2, where it happens by default, and it wanted to reflow the
      aligned trailing comments in the README and DESIGN examples. Fixed by excluding
      `*.md` in `[tool.ruff.format]`, so the result no longer depends on which ruff a
      developer happens to have.

      **The dev extra is unpinned on purpose, so expect this again.** `ruff>=0.5` and
      `mypy>=1.8` mean CI always resolves to the newest release and a new rule or a changed
      default can red the badge without a line of our code changing. That is the trade for
      not having to chase pins; when it happens, check the version CI installed against the
      local one before suspecting the commit. Reproduce it by downloading the exact version
      CI used and running it against the tree — guessing costs a push per attempt.

      Also worth knowing: **3.10 is in the matrix because `requires-python = ">=3.10"` and
      the classifiers advertise it**, not because anything needs it. Every module carries
      `from __future__ import annotations` and there is no 3.11+ stdlib use, so raising the
      floor would drop a support claim without simplifying any code. 3.10 has upstream
      security support until October 2026. If the claim is ever dropped, change
      `requires-python`, the classifiers and the matrix together.
- [ ] **Publish to PyPI as `chess-results`.** Still free as at 2026-08-10, on both
      normalisations. Rehearsing on TestPyPI first, via
      `.github/workflows/publish.yml` — TestPyPI only by design, so there is no path to
      the real index until an upload has been watched working.

      **Trusted Publishing, not an API token.** GitHub mints a short-lived OIDC token
      the index exchanges for upload rights: nothing in repository secrets, nothing on
      a laptop, and the upload acts as the repository rather than as a user — which
      also sidesteps this machine defaulting to the wrong GitHub account.

      **The TestPyPI rehearsal succeeded on 2026-08-10**, run 31385337061, uploading
      `0.1.0.dev1`. Both install paths were then verified from the index in clean
      venvs — the wheel, and the sdist via `--no-binary`, which is the one that
      exercises building from source. The console script lands on `PATH`, the import
      works, `py.typed` ships, and the three runtime dependencies resolve while the
      `dev` extras correctly do not.

      Beware verifying this in the global pyenv: the editable install satisfies
      `chess-results` already, so pip reports "already satisfied" and never contacts
      the index at all. It looks like a pass and tests nothing. Use a throwaway venv:

          pip install --index-url https://test.pypi.org/simple/ \
                      --extra-index-url https://pypi.org/simple/ chess-results

      The fallback index is required — requests, beautifulsoup4 and requests-cache are
      not mirrored on TestPyPI.

      **What is left is the real index**, and it is blocked on one thing needing a
      login: registering a **pending** publisher on pypi.org. The project does not
      exist there, so there is nothing to attach an ordinary publisher to; the first
      upload converts it. Project `chess-results`, owner `markjonleonard`, repo
      `chess-results`, workflow `release.yml`, environment `pypi`. All five must match
      or the exchange is refused — and note two differ from the TestPyPI publisher
      already registered, which is the easy mistake.

      Releasing is then `git tag v0.1.0 && git push origin v0.1.0`.
      `.github/workflows/release.yml` fires on `v*` rather than a button, so a release
      is tied to one commit rather than to whatever `main` happens to be. It runs the
      suite first — a tag push matches neither of CI's triggers, so without that a
      release could ship code nothing had run against — then refuses to upload unless
      the tag matches the built version, compared after PEP 440 normalisation.

      The metadata is clean: `twine check --strict` passes on both artifacts, and the
      licence is the SPDX `License-Expression: MIT` of PEP 639 rather than the
      deprecated classifiers. Both workflows run that same `--strict` check before
      uploading, so a fault fails the build instead of burning a version number.
- [x] **Compare the round 8 prediction against the published pairings.** Done 2026-08-07 with
      `examples/validate_prediction.py`. Rounds 7 and 8 both reproduce **51 of 51 exactly,
      colours and bye included**, once withdrawals are supplied; 37/51 and 44/51 respectively
      without them. Withdrawals are the entire error term. Round 9 re-confirmed this on
      2026-08-09: **50 of 50** with withdrawals, 42/50 blind, and all 8 blind misses trace to
      the 8 absent players. Three rounds, same result — see the withdrawal-inference item below.

## Correctness and coverage

- [x] **`parse_tournament_name` returned the server-load banner.** Fixed 2026-08-08. It took
      the first heading of any level; chess-results prints an `h3` banner above the name once
      a tournament is more than five days old, so every Frome section came back as "Note: To
      reduce the server load...". The name is the first `h2`, with the page title (minus the
      site's prefix) as a fallback. The existing Frome fixtures already reproduced it.

- [x] **Forfeits are untested against real pages.** Fixed 2026-08-09. Stubbs (starting
      number 62) defaulted twice in the 2026 British — round 8 board 45 against Gunatilake
      (`- -`) and round 9 board 48 against Cooke (`+ -`) — which gives both directions on
      both views. Added `british2026_champ_r8.html`, `_r9.html` and
      `_crosstable_final.html`, and `tests/test_forfeit.py` covering the pairing pages, the
      previously-uncovered `_crosstable_cell` branch (`100w-` and its matching win on the
      opponent's row), and the `+`/`-` TRF encoding read back out of a real file. The
      parsers were correct as written; nothing needed changing.
- [x] **`mypy --strict` fails.** Fixed 2026-08-09; it now passes clean on all 8 source
      files and runs in the CI `lint` job. With the stubs installed the count was 28, not
      the 22 recorded here, and they came down to six causes:

      - `cache.cached_session` had no return type and typed `**kwargs: object`. Now returns
        `CachedSession` (imported under `TYPE_CHECKING`, since requests-cache is optional at
        runtime) and forwards `**kwargs: Any` — a pass-through to a constructor with a couple
        of dozen unrelated setting types cannot be more precise than that.
      - `client.fetch` typed `**params: object`; they are query values, so `str | int`.
      - `client.fetch`'s `options` dict carries `expire_after`, which is requests-cache's
        extension and absent from `requests.Session.get`. Typed `Any` with a comment; the
        alternative is to type the session as `CachedSession`, which it often is not.
      - `client._is_cached` took a bare `dict` and read `self.session.cache`, which
        `requests.Session` does not have. Now `dict[str, str | int]`, and the store is
        reached with `getattr(self.session, "cache", None)`. Behaviour is unchanged — the
        old `self.caching` guard was the same `hasattr` test.
      - `Player.colours` returned `list[Colour | None]`: `counts_for_colour` guarantees the
        colour is set but mypy will not narrow through a property, so the check is spelled
        out in the comprehension.
      - `cli.main` returned `Any` from `args.func(args)`, argparse being untyped.

      No behaviour changed and no test needed amending; 165 still pass.
- [x] **Widen the ruff ruleset.** Done 2026-08-09. `select` is now `E, F, I, UP, B, SIM,
      RET, C4, PTH, RUF`; `ANN`, `D` and `S` stay off. The whole tree — src, tests and
      examples — produced exactly two findings, both fixed rather than suppressed, so no
      per-file ignores were needed:

      - `PTH123` in `cli.py`: `open(args.output, "w")` is now
        `Path(args.output).write_text(text, encoding="utf-8")`, which drops the `with`
        block entirely.
      - `SIM114` in `tournament.likely_withdrawn`: two `if` arms both adding to the same
        set. Combined behind two named conditions, `trailing_unpaired` and `never_played`,
        which is what the docstring already called the two signals.

      The two threshold warnings noted here as worth suppressing — `parse_pairings`
      complexity 11 and `trf.py`'s 7 returns — come from `C901` and `PLR`, neither of which
      is in the selection, so they never fire.
- [x] **Raise CLI coverage.** Done 2026-08-09, and the figure recorded here was long out of
      date: `cli.py` was at **86%**, not 45%, and the project at 91%, not 86% — the
      `pairings`/`--limit` work had brought its own tests. Covering `dump` (both the stdout
      and the `-o` file paths) and `unfinished` (empty, populated and truncated) takes
      `cli.py` to **97%** and the project to **94%**, 182 tests. What is left uncovered is
      `_fetch`, which needs a live client, and three process-level lines: `_silence_stdout`,
      the `BrokenPipeError` arm and `__main__`. Not worth testing.
- [x] **No retry or backoff.** Done 2026-08-09. `client.retrying_adapter` mounts a urllib3
      `Retry` on 429 and the 5xx family — 3 attempts, `backoff_factor` 0.5, so roughly 0.5s,
      1s, 2s — for GET and HEAD only, honouring `Retry-After`. 404 is deliberately not in
      the list: it is chess-results answering that no such tournament exists.

      Only sessions `ChessResults` builds itself are mounted on. A session passed in as
      `session` keeps its own transport policy, which would otherwise be silently
      overwritten — the adapter is exported so such a caller can mount it themselves.
      `retries=0` opts out. Covered by `tests/test_client.py` without touching the network.
- [x] **Cross-check the crosstable instead of only filling gaps.** Done 2026-08-09. Where
      both views have a round, `add_crosstable` now compares `kind`, `colour`, `opponent`,
      `score` and `forfeit`, recording any contradiction in `Tournament.disagreements` as a
      `Disagreement`. The pairing page still wins — a disagreement is reported, never
      silently resolved — and the CLI prints them to stderr, so piped output stays clean.

      **It finds nothing.** Zero disagreements across every fixture (British mid-event,
      British played out through round 9 including both forfeits, Frome) and zero against the
      live event. That is the expected result — the two views come from the same upload — so
      this is a tripwire, not a fix. The tests corrupt a parsed crosstable deliberately to
      prove it can still fire.

      The one design point worth keeping: **a value one view holds and the other lacks is
      not a contradiction.** The mid-event crosstable fixture has 114 results the round 6
      and 7 pages had not caught, purely because it was saved later, and a round page carries
      no result at all until the game finishes. Comparing those would have produced 114 false
      alarms on a healthy tournament.
- [ ] **Recovered rounds have no float direction beyond byes.** A `Play` restored from the
      crosstable has no `points_before`, so `_floats` cannot run on it. Only the
      bye-is-a-downfloat rule applies. The pre-round score could be reconstructed by summing
      earlier rounds if float history for those players ever matters.
- [x] **`fixed_board_number` takes the modal board.** Fixed 2026-08-09 — and the modal board
      was not merely inexact, it was **wrong on the one real example we have, at the moment
      it mattered**. Hebden's pin starts at round 4 (boards 23, 18, 1, then 14 for the rest),
      and after round 4 every board has been played exactly once, so `Counter.most_common`
      returns the first inserted: **23**. It only came right at round 5. Round 4 is precisely
      when you would ask — predicting round 5 from a live round 4.

      Now the longest unbroken run of one board number, most recent run winning a tie, which
      identifies a pin from the round it begins. A bye is skipped rather than treated as
      breaking the run. Rounds 1-3 still answer 1, the last board played, because nothing in
      them can know 14 is coming.

      It stays a heuristic and the docstring now says why: two rounds on one board by
      coincidence look like a pin, and a pin the arbiter could not honour one round looks
      like two shorter ones. chess-results only ever flags *that* a player is pinned. The
      tests fail against the old implementation, which is the point of them.

## Open questions from the round 7 validation

- [x] **Explain the differing pairings.** Answered 2026-08-07, and the old hypothesis was
      wrong. It was not the rule version: given the correct field, bbpPairings reproduces
      rounds 7 and 8 exactly, all 51 boards with colours and the bye. Every difference was a
      withdrawn player the scraper could not see. The earlier "47 of 52" figure does not
      reproduce and has been dropped from the README. Running JaVaFo is no longer needed to
      separate "our data is wrong" from "the engines disagree" — it was the data.
- [x] **Infer withdrawals rather than requiring `--withdrawn`.** Done 2026-08-09 as
      `Tournament.likely_withdrawn`: a player is flagged when their last `consecutive`
      rounds are all `UNPAIRED`, or when they never occupied a round at all. A *requested*
      bye is deliberately not a signal. `predict_next_round.py` applies it by default
      (`--no-infer-withdrawals` opts out); `validate_prediction.py` now scores three ways.
      Measured on the 2026 British, exact pairings including colours:

      | round | blind | inferred | true field |
      | --- | --- | --- | --- |
      | 7 | 37/51 | **39/51** | 51/51 |
      | 8 | 44/51 | **49/51** | 51/51 |
      | 9 | 42/50 | **44/50** | 50/50 |

      12 of the 18 absent players found across the three rounds, one false alarm (Elgar,
      unpaired in round 7 and back in round 8 — and it cost almost nothing: round 8 still
      scored 49/51). `consecutive=1` beat 2 and 3 on the same data.

- [x] **The residual withdrawal gap is irreducible.** Settled 2026-08-10 by the experiment
      this item asked for, against a live event: tournament 1473782, the Jeddah Season
      Chess Championship Qualifiers, a 32-player 7-round Swiss caught with round 1
      complete, round 2 paired and 9 of its 16 games played, and round 3 not yet paired.

      **`art=40` carries a column for every one of the seven rounds and a marker in
      round 1 only.** Rounds 3-7 are unpaired and say nothing about anybody, so the page
      is contemporaneous rather than predictive, exactly as the semantics suggested. It
      cannot tell you who will be missing from the round you are about to pair.

      Round 2 is blank too, but that argues nothing either way — it pairs the whole
      field, so there is no absence for the page to record. The unpaired rounds carry
      the finding; the guard is a test of its own so nobody later mistakes the one for
      the other.

      Captured as `jeddah2026_*` fixtures and pinned by
      `test_not_paired.TestItDoesNotWarnInAdvance`. They cannot be regenerated: the page
      ignores `&rd=`, so this state existed only while that round was live.

      So **132/152 stands as the ceiling**, and the three players absent from round 9 of
      the British with no prior signal — Dupuis, Jermy, Majeed — remain undetectable in
      principle rather than merely in our implementation.

- [x] **Check the TRF we emit against TRF-2026.** Done 2026-08-09, and it found a real bug.
      Checked empirically rather than by reading alone: bbpPairings has a check mode
      (`--dutch file -c`) that parses a whole tournament and lists discrepancies.

      **The format is accepted.** Rounds 1-8 of the British parse cleanly, exit 0, no
      complaint about columns, `XXR`, the `Z` entries used for withdrawals, or the `+`/`-`
      forfeit characters. We rely on no inference a stricter reader would reject: no `XXA`
      (no acceleration, which is the Dutch default anyway), and no `BBW`/`BBD`, which are
      only needed for a non-standard win/draw value.

      **But `bye_value` was doing nothing.** The crosstable prints every pairing-allocated
      bye as a full point whatever the event awards, and `add_crosstable` copied that
      straight through — so on the British, where all four byes reach the history from the
      crosstable because their round pages had been superseded, `--bye-value 0.5` changed
      no score at all. Fixed: `Tournament.bye_value` rescores a recovered bye, the client
      passes it through, and `to_trf` now emits the `BBU` line automatically when the value
      is not a full point. This matters because bbpPairings recomputes every score from the
      results and **refuses the file** when the totals disagree — which is exactly what it
      did when handed the old output with a `BBU 0.5` line: *"The score for player 104 does
      not match the game results."* The crosstable's convention is deliberately exempt from
      the disagreement check; it is a difference of convention, not a contradiction.
- [x] **bbpPairings' checker disagrees with the published round 2 on six boards.**
      Investigated 2026-08-09. **Nothing to fix on our side**, and the hypothesis recorded
      here was wrong. Four candidate explanations, all tested and all dead:

      - **Not the field.** Two players missed round 2 (Mannion 59, Kothari 69). Supplying
        exactly those gives the *best* result, 47 of 53; supplying neither gives 37, either
        one alone 33. So the correct field is already in use and the six boards remain.
      - **Not how a late entrant's missing round is encoded.** Brown (108) did not play
        round 1 and is in the differing set, which is what made this look like a
        representation problem. Emitting her round 1 as `0000 - Z`, as a blank, or as
        `0000 - -` produces *identical* pairings — 47 of 53 in all three cases.
      - **Not colours.** Every board on which the two agree agrees on colour too: 47 pairs,
        47 with colours.
      - **Not same-federation avoidance.** The published round 2 has 24 of its 53 boards
        between players of the same federation, so no such rule is operating.

      What it is: a six-board cyclic shift confined to one scoregroup — the 42 players on
      zero after round 1. bbpPairings pairs 32-81, 44-82, 54-84, 56-87, 57-89, 108-79; the
      arbiter published 32-79, 44-81, 54-82, 56-84, 57-87, 108-89, each of the five S1
      players taking an opponent one step earlier in the sequence. Structurally the
      published pairing behaves as though 79 were the *top of S2* rather than the *bottom of
      S1* — a one-place difference in where a 42-player group was split — but inserting
      either absent player to force that split does not reproduce it either.

      The checker lists the difference without flagging the published pairing as illegal,
      and exits 0. So both are presumably admissible Dutch pairings on a group where a great
      many are, and the two implementations resolve the choice differently. Rounds 1 and 3-8
      reproduce exactly, as do 7, 8 and 9 given the right field, so this does not undermine
      prediction — it caps it on rounds with one very large all-equal scoregroup, which in
      practice means round 2.

## Scope

- [x] **Parse `art=40`.** Done 2026-08-09: `parse_not_paired` returns `NotPairedEntry`
      rows (starting number, name, rating, title, federation, and a round → `Absence`
      marker map), `ChessResults.not_paired()` fetches it on the live TTL, and
      `tests/test_not_paired.py` covers both a British and a Frome capture.

      **It does not replace the crosstable, which is not what this item assumed.** Checked
      both ways against the crosstables: only a *pairing-allocated* full-point bye prints
      `bye`, while a *requested* half-point bye prints `*`, exactly as a withdrawal does.
      Every one of Frome's round 1 half-point byes appears as `*`; every British `bye`
      marker is a full point. `likely_withdrawn` deliberately does not count a requested bye
      as a signal, so feeding this page to it naively would invent a withdrawal for every
      half-point bye. A forfeit is one-sided too: only the defaulting player is listed, not
      the opponent who took the point.

      So the division is: this page is the authority on *which* rounds were missed and is
      one request rather than a whole crosstable to mine; the crosstable stays the authority
      on *what* a missed round was worth.
- [x] **Feed `art=40` to the withdrawal inference.** Done 2026-08-09.
      `likely_withdrawn(not_paired=...)` takes the parsed page as a second source of
      absences. Measured offline against the 2026 British fixtures, players flagged per
      round:

      | after round | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
      | --- | --- | --- | --- | --- | --- | --- | --- |
      | round pages alone | 0 | 0 | 0 | 0 | 0 | 3 | 5 |
      | round pages + `art=40` | **2** | **2** | **2** | **2** | **3** | 3 | 5 |
      | crosstable-reconciled | 2 | 2 | 2 | 2 | 3 | 3 | 5 |

      Round pages alone find *nobody* for a superseded round; add one request for `art=40`
      and they find exactly what the crosstable finds, at every round. On a
      crosstable-reconciled history it is identical to passing nothing, as it must be — the
      crosstable already holds everything the page says.

      No engine run was needed to settle it: a prediction is a pure function of the
      withdrawn set, and the sets are equal, so the pairings are equal too. For the same
      reason `predict_next_round.py` is left alone — it reconciles against the crosstable,
      where this provably changes nothing.

      The half-point-bye hazard turns out to be narrower than feared. The marker is
      consulted **only** for a round the player has no play for at all, so anything a round
      page or the crosstable has said wins. Frome's twelve round 1 half-point byes therefore
      produce no false alarm: their round page still lists them. The hazard needs all three
      of a half-point bye, a round page that has dropped the row, and no crosstable.
- [ ] **More views.** Parsed today: round pairings (`art=2`), starting rank (`art=0`),
      starting-rank crosstable (`art=5`), not paired (`art=40`). Not parsed: alphabetical
      (`art=3`), ranking crosstable (`art=4`, same data as 5 but keyed by current rank).
      Three were inspected
      on 2026-08-09 against the 2026 British and are described here so nobody has to fetch
      them again:

      - **`art=1` — ranking list.** One row per player, in rank order, after the latest
        round; `&rd=N` gives the standing after round N. Columns
        `Rk. | SNo | (flag) | (title) | Name | Typ | sex | FED | Rtg | TB1 | K | rtg+/-`,
        where TB1 is the score. It lists withdrawn players in place with their frozen score
        (Mannion 108th on 0) and **carries no withdrawal marker of any kind**. Note the
        score is printed with a decimal comma — `6,5` — which is the locale item below.
      - **`art=9` — player info.** Needs `&snr=<starting number>`; without one it renders an
        empty shell. Gives a bio table (performance rating, FIDE rtg +/-, club, Ident-Number,
        Fide-ID, year of birth) and a per-round table
        `Rd. | Bo. | SNo | (title) | Name | Rtg | FED | Pts. | Res. | K | rtg+/- | PGN`,
        with a downloadable PGN per game. A round the player missed appears explicitly as a
        `not paired` row with opponent SNo `-2`. One request per player, so 108 for a field.
      - **`art=40` — "not paired".** Parsed as of 2026-08-09 by `parse_not_paired`, with
        `ChessResults.not_paired()` to fetch it; see the item below for what it turned out
        to be worth. Undocumented and not linked from the views we already use; found in the
        nav bar as *not paired*. A single page listing only the players who missed at least
        one round, as a grid of one column per round with three markers — `*` not paired,
        `bye` a bye, `0F` a forfeit, blank played. Fifteen rows covered the whole British
        field once the event finished. It ignores `&rd=`.
- [x] **Locale decimal commas.** Done 2026-08-09. `parse_points` now normalises a decimal
      comma, so `4,5` reads as 4.5 exactly as `4½` does. A comma is always a decimal
      separator here — no points value is ever large enough to need a thousands separator.

      `parse_result` had the same latent bug and is fixed with it: untreated, `0,5 - 0,5`
      tokenises as the four numbers 0, 5, 0, 5, and the first two would be taken as the two
      players' scores, recording the game as 0-5. Neither failure was loud — `parse_points`
      returned `None`, which is indistinguishable from a round not yet played.

      Still latent in the pipeline: nothing we parse today emits commas, the round pages
      using `½` throughout. The tests therefore sweep every `n,n` string in the British
      crosstable (the `TB1` column) to prove the fix works on real data.
- [x] **Read the crosstable's published totals and check them.** Done 2026-08-09.
      `parse_published_totals` reads the `TB1` column, and `check_published_totals` requires
      the round-by-round cells we parsed from the same row to sum to it, recording a
      `Disagreement` with `field="total"` when they do not. The client runs it as part of
      `tournament()`, fetching the page once and parsing it twice. CLAUDE.md's manual "all
      108 must agree" is now automatic.

      **It passes everywhere**: 254 player-rows across the three crosstable fixtures, and
      all 108 against the finished live event.

      The design point that took measuring: it compares the crosstable **against itself**,
      not against the assembled history. A published total and an assembled score are
      comparable only when both cover exactly the same rounds, and they routinely do not —
      the crosstable is often a fresher capture and may run to rounds we never fetched.
      Comparing them gives **75** mismatches on the mid-event fixture and 5 on the played-out
      one, none of them faults. A test pins that 75 so nobody "fixes" the check into
      uselessness. Published scores are also used exactly as printed, so a pairing-allocated
      bye counts 1 here whatever `bye_value` says — that is the crosstable's own convention,
      and the rescaling belongs downstream.
- [ ] **Team tournaments are untested.** Unknown whether `parse_pairings` copes with a team
      pairing table; do not claim support until there is a fixture.

## Housekeeping

- [ ] **The caching self-correction costs one extra fetch per round.** requests-cache fixes
      expiry at write time, so a round that settles between runs is fetched once more before
      it takes the 30-day lifetime. Fixable by rewriting the cache entry at the moment a
      round is recorded as settled. Documented in DESIGN.md as a known caveat; low value.
- [x] **Two round-6 fixtures now exist.** Renamed 2026-08-09. The mid-round captures are
      `british2026_champ_r6_midround.html` and `_r7_midround.html`, sitting beside their
      `_finished` counterparts, so a directory listing states which is which and neither
      holds the plain `_r6.html` name. Tests ask `conftest._round_fixture(rnd, played_out=…)`
      for the name.

      The rename immediately earned itself: three places in `test_cache.py` were building
      `f"british2026_champ_r{rnd}.html"` and silently getting the mid-round capture, which
      is what they wanted but had never said. They now say so.
