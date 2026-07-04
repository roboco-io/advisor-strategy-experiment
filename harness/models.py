"""모델 ID, 단가($/1M 토큰), 비용 계산."""

FABLE = "claude-fable-5"
HAIKU = "claude-haiku-4-5"
SONNET = "claude-sonnet-5"
OPUS = "claude-opus-4-8"

# (input $/1M, output $/1M). Sonnet는 2026-08-31까지 도입가 2/10.
PRICES: dict[str, tuple[float, float]] = {
    FABLE: (10.0, 50.0),
    HAIKU: (1.0, 5.0),
    SONNET: (2.0, 10.0),  # 도입가; 만료 후 3/15로 갱신
    OPUS: (5.0, 25.0),
}

_M = 1_000_000


def cost_of(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read: int = 0,
    cache_write: int = 0,
) -> float:
    """토큰 사용량을 단가로 환산. cache_read≈0.1x, cache_write≈1.25x(5분 TTL) 입력단가."""
    in_price, out_price = PRICES[model]
    return (
        input_tokens / _M * in_price
        + output_tokens / _M * out_price
        + cache_read / _M * in_price * 0.1
        + cache_write / _M * in_price * 1.25
    )
