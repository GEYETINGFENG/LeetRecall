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
