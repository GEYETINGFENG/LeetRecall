import pytest

from leetrecall_ai.obs.metrics import call_cost


def test_cost_uses_cache_rates_and_served_model():
    # 1M uncached in + 1M out on Opus 5.5 = $4 + $20
    assert call_cost("claude-opus-5-5", 1_000_000, 0, 0, 1_000_000) == pytest.approx(24.0)
    # cache write billed at 1.25x input, cache read at the cache-read rate
    assert call_cost("claude-opus-5-5", 2_000_000, 1_000_000, 1_000_000, 0) == pytest.approx(0.20 + 5.0)


def test_unknown_model_fails_loud_instead_of_zero_cost():
    with pytest.raises(KeyError):
        call_cost("claude-unknown", 1, 0, 0, 1)
