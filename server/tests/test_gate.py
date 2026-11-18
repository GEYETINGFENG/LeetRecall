from leetrecall_ai.agents.critic import passed


def verdict(**kw):
    base = dict(idea_correct=True, complexity_correct=True, pattern_correct=True, issues=[], fix_instructions="",
                hint_checks=[{"index": i, "spoils": False, "why": ""} for i in (1, 2, 3)])
    return {**base, **kw}


def test_gate_passes_only_when_every_check_is_clean():
    assert passed(verdict())
    assert not passed(verdict(complexity_correct=False))
    assert not passed(verdict(hint_checks=[{"index": 1, "spoils": False, "why": ""}, {"index": 2, "spoils": False, "why": ""},
                                           {"index": 3, "spoils": True, "why": "names the stack"}]))


def test_malformed_verdict_fails_closed_instead_of_crashing():
    from leetrecall_ai.agents.critic import review_round

    # the real failure the eval caught: 1 hint check instead of 3
    bad = verdict(hint_checks=[{"index": 1, "spoils": False, "why": ""}])
    rec = review_round(bad, {"hints": ["a", "b", "c"]})
    assert rec["passed"] is False and rec["malformed"] is True and "hint_checks" in rec["error"]
    assert review_round(verdict(), {})["malformed"] is False
