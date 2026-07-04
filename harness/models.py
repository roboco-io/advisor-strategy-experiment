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
    # 구독 CLI의 "sonnet" 별칭은 Sonnet 4.6으로 해석됨 → 별도 단가.
    "claude-sonnet-4-6": (3.0, 15.0),
    OPUS: (5.0, 25.0),
}

# Agent SDK `model` 파라미터에 넘길 별칭 (풀 ID → alias)
ALIAS: dict[str, str] = {
    FABLE: "fable",
    HAIKU: "haiku",
    SONNET: "sonnet",
    OPUS: "opus",
}

_M = 1_000_000


def normalize(model_id: str) -> str:
    """model_usage 키(날짜 포함 풀 ID)를 PRICES 키로 정규화.

    예: 'claude-haiku-4-5-20251001' -> 'claude-haiku-4-5'. 매칭 없으면 원본 반환.
    """
    if model_id in PRICES:
        return model_id
    for key in PRICES:
        if model_id.startswith(key):
            return key
    return model_id


def cost_of(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read: int = 0,
    cache_write: int = 0,
) -> float:
    """토큰 사용량을 단가로 환산. cache_read≈0.1x, cache_write≈1.25x(5분 TTL) 입력단가.

    단가표에 없는 모델은 크래시 대신 0.0을 반환(토큰은 계속 기록되고 데이터 유실 방지)."""
    if model not in PRICES:
        return 0.0
    in_price, out_price = PRICES[model]
    return (
        input_tokens / _M * in_price
        + output_tokens / _M * out_price
        + cache_read / _M * in_price * 0.1
        + cache_write / _M * in_price * 1.25
    )
