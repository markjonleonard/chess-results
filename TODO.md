# TODO

Open work on chess-results, roughly in the order it is worth doing.

## Before this goes anywhere

- [x] **CI.** Done 2026-08-09 as `.github/workflows/ci.yml`. Two jobs on push to `main`,
      every pull request and `workflow_dispatch`: `lint` runs `ruff check` and
      `ruff format --check` on 3.13 only, `test` runs `pytest` across 3.10–3.13 with
      `fail-fast: false`. Both were already clean locally, so the format gate is safe to
      enforce. No secrets and no network allowance — the suite is fixtures only. `mypy` is
      deliberately *not* wired in yet; it still fails (see below) and would red the badge
      from the first run.
- [ ] **Publish to PyPI as `chess-results`.** Free as at 2026-08-07; re-check at publish
      time.
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
- [ ] **Widen the ruff ruleset.** Currently `E, F, I, UP, B`. Adding `SIM, RET, C4, PTH,
      RUF` is real value at low noise. Leave `ANN`, `D` and `S` off for `tests/` — a test
      suite is meant to be full of bare asserts. `--select ALL` reports 549, of which only
      four were ever actionable and two are threshold warnings worth keeping suppressed
      (`parse_pairings` complexity 11, `trf.py` 7 returns).
- [ ] **Raise CLI coverage.** 86% overall, but `cli.py` sits at 45% while the library
      modules are 80–98%. The command handlers are barely exercised.
- [ ] **No retry or backoff.** A transient 5xx from chess-results aborts a whole scrape.
      A `requests` `HTTPAdapter` with `Retry` on 429/5xx would fix it.
- [ ] **Cross-check the crosstable instead of only filling gaps.** `add_crosstable`
      currently trusts the pairing pages wherever they have data. It could compare and warn
      on disagreement, which would catch a parse bug in either view.
- [ ] **Recovered rounds have no float direction beyond byes.** A `Play` restored from the
      crosstable has no `points_before`, so `_floats` cannot run on it. Only the
      bye-is-a-downfloat rule applies. The pre-round score could be reconstructed by summing
      earlier rounds if float history for those players ever matters.
- [ ] **`fixed_board_number` takes the modal board.** Fine for Hebden (boards 23, 18, 1,
      then 14 every round after), but it is a heuristic. chess-results flags *that* a player
      has a fixed board and never says which.

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

- [ ] **The residual withdrawal gap looks irreducible.** `likely_withdrawn` closes 9 of the
      29 missed pairings above; the rest are players with *no signal to find*. Three of the
      eight absent from round 9 — Dupuis, Jermy, Majeed — played round 8 in full and simply
      never came back, so rounds 1–8 contain nothing to detect.

      Checked on 2026-08-09: **no view marks a withdrawal in advance.** `art=1` ranks
      withdrawn players in place with no marker at all. `art=9` shows a `not paired` row per
      player, and `art=40` consolidates every absence onto one page — but both record a round
      that has already been paired. All three name Dupuis, Jermy and Majeed only under round
      9, which is the round we were trying to predict. So they are contemporaneous, not
      predictive, and add nothing the crosstable does not already have.

      This is inference from the semantics, not observation: `art=40` ignores `&rd=`, so its
      mid-event state cannot be recovered after the fact. Settle it by fetching `art=40`
      during a live round and checking whether a `*` ever appears for a round that is not yet
      paired. Until then, treat 132/152 as the ceiling.
- [ ] **Check the TRF we emit against TRF-2026.** `trf.py` writes TRF(x). bbpPairings'
      README says it targets TRF-2026 and reads TRF(bx)/TRF(x) for backwards compatibility,
      including its own extension codes (`BBW`/`BBD` for point values, acceleration via
      `XXA`). Worth confirming we are not relying on an inference that a stricter reader
      would reject.

## Scope

- [ ] **More views.** Parsed today: round pairings (`art=2`), starting rank (`art=0`),
      starting-rank crosstable (`art=5`). Not parsed: alphabetical (`art=3`), ranking
      crosstable (`art=4`, same data as 5 but keyed by current rank). Three were inspected
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
      - **`art=40` — "not paired".** Undocumented and not linked from the views we already
        use; found in the nav bar as *not paired*. The most interesting of the three: a
        single page listing only the players who missed at least one round, as a grid of one
        column per round with three markers — `*` not paired, `bye` a bye, `0F` a forfeit,
        blank played. Fourteen rows covered the whole British field. It ignores `&rd=`.
        Worth parsing as a cheaper, more explicit source than mining the crosstable.
- [ ] **Locale decimal commas.** The crosstable prints points as `1,5`. We do not currently
      read that column — the round-by-round tokens use `½` — but any ranking view will hit
      it, and `parse_points` does not handle a comma.
- [ ] **Team tournaments are untested.** Unknown whether `parse_pairings` copes with a team
      pairing table; do not claim support until there is a fixture.

## Housekeeping

- [ ] **The caching self-correction costs one extra fetch per round.** requests-cache fixes
      expiry at write time, so a round that settles between runs is fetched once more before
      it takes the 30-day lifetime. Fixable by rewriting the cache entry at the moment a
      round is recorded as settled. Documented in DESIGN.md as a known caveat; low value.
- [ ] **Two round-6 fixtures now exist.** `british2026_champ_r6.html` (mid-round, bye rows
      intact) and `british2026_champ_r6_finished.html` (complete, bye rows deleted). Keep
      both — the pair is what demonstrates the vanishing-bye problem — but the naming does
      not make the distinction obvious from a directory listing.
