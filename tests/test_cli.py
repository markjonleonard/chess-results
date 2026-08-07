from chess_results.cli import build_parser


def test_shared_options_parse_before_the_subcommand():
    args = build_parser().parse_args(["--after", "6", "colours", "1452107"])
    assert (args.after, args.tournament_id) == (6, "1452107")


def test_shared_options_parse_after_the_subcommand():
    args = build_parser().parse_args(["colours", "1452107", "--after", "6"])
    assert (args.after, args.tournament_id) == (6, "1452107")


def test_bye_value_defaults_to_a_full_point():
    assert build_parser().parse_args(["standings", "1"]).bye_value == 1.0
