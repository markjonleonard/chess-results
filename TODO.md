# TODO

Open work on chess-results, roughly in the order it is worth doing.

## Before this goes anywhere

- [ ] **CI.** GitHub Actions running `ruff check` and `pytest` on 3.10–3.13. The suite is
      fully offline, so it needs no secrets and no network allowance.
- [ ] **Publish to PyPI as `chess-results`.** Free as at 2026-08-07; re-check at publish
      time.
- [x] **Compare the round 8 prediction against the published pairings.** Done 2026-08-07 with
      `examples/validate_prediction.py`. Rounds 7 and 8 both reproduce **51 of 51 exactly,
      colours and bye included**, once withdrawals are supplied; 37/51 and 44/51 respectively
      without them. Withdrawals are the entire error term.

## Correctness and coverage

- [ ] **Forfeits are untested against real pages.** No fixture in the repo contains one.
      `parse_result` has unit tests for `"+ -"` / `"- +"`, but the crosstable's forfeit
      branch in `_crosstable_cell` (`54b+`, `54b-`) has *no* coverage at all — it was
      written from the format's shape, not from an observed page. Find a tournament with a
      default and add it as a fixture before trusting it.
- [ ] **`mypy --strict` fails with 22 errors.** The tools are now in the dev extra
      (`mypy`, `types-requests`, `types-beautifulsoup4`), but the errors are unfixed. Most
      will clear with the stubs installed. Two are real: `cache.py` types `**kwargs: object`,
      too loose to forward to `CachedSession`, and `client.py` builds `params` as
      `dict[str, object]` where `requests` wants stricter values. The package advertises
      `Typing :: Typed` and ships `py.typed`, so this ought to be clean.
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
- [ ] **Infer withdrawals rather than requiring `--withdrawn`.** Now the only source of
      prediction error. A player who has stopped appearing is detectable from the crosstable
      (`-0` in the latest rounds) even though the round pages have deleted the evidence.
      A heuristic — absent from the last N rounds, or `-0` in the most recent — would close
      most of the 44/51 to 51/51 gap without hindsight.
- [ ] **Check the TRF we emit against TRF-2026.** `trf.py` writes TRF(x). bbpPairings'
      README says it targets TRF-2026 and reads TRF(bx)/TRF(x) for backwards compatibility,
      including its own extension codes (`BBW`/`BBD` for point values, acceleration via
      `XXA`). Worth confirming we are not relying on an inference that a stricter reader
      would reject.

## Scope

- [ ] **More views.** Parsed today: round pairings (`art=2`), starting rank (`art=0`),
      starting-rank crosstable (`art=5`). Not parsed: ranking (`art=1`), alphabetical
      (`art=3`), ranking crosstable (`art=4`, same data as 5 but keyed by current rank),
      player info (`art=9`).
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
