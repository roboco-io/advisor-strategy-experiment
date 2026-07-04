from harness import models


def test_model_ids():
    assert models.FABLE == "claude-fable-5"
    assert models.HAIKU == "claude-haiku-4-5"
    assert models.SONNET == "claude-sonnet-5"
    assert models.OPUS == "claude-opus-4-8"


def test_cost_of_haiku():
    # Haiku: $1/1M in, $5/1M out
    c = models.cost_of(models.HAIKU, input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(c - 6.0) < 1e-9


def test_cost_of_fable_with_cache():
    # Fable: $10 in, $50 out; cache_read ~0.1x in, cache_write ~1.25x in
    c = models.cost_of(
        models.FABLE, input_tokens=1_000_000, output_tokens=0,
        cache_read=1_000_000, cache_write=1_000_000,
    )
    # 10 (in) + 1.0 (read 0.1x) + 12.5 (write 1.25x) = 23.5
    assert abs(c - 23.5) < 1e-6


def test_alias_map():
    assert models.ALIAS[models.HAIKU] == "haiku"
    assert models.ALIAS[models.SONNET] == "sonnet"
    assert models.ALIAS[models.FABLE] == "fable"
    assert models.ALIAS[models.OPUS] == "opus"


def test_normalize_dated_and_alias():
    assert models.normalize("claude-haiku-4-5-20251001") == models.HAIKU
    assert models.normalize("claude-fable-5") == models.FABLE
    assert models.normalize("claude-sonnet-5") == models.SONNET
    assert models.normalize("unknown-model") == "unknown-model"
