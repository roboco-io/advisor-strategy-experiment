# Advisor Strategy — RealWorld 실험

Anthropic의 **Advisor Strategy**(강한 모델이 조언만, 약한 모델이 루프를 소유·실행)를
**Fable=advisor, Haiku/Sonnet=worker**로 검증하는 측정 하니스. 각 arm이 RealWorld(Conduit)
백엔드를 구현하고 공식 Postman 컬렉션(Newman)으로 채점받아 **승격폭·비용**을 계측한다.

- 설계: `docs/superpowers/specs/2026-07-04-advisor-strategy-realworld-design.md`
- 계획: `docs/superpowers/plans/2026-07-04-advisor-strategy-realworld.md`

## 실행 채널

Claude **Agent SDK**(`claude-agent-sdk`)를 **Claude Code 구독 인증**으로 실행한다
(per-token API 과금 없음). 비용은 토큰 사용량 × 공시 단가(`harness/models.py`)로 계산하므로,
결제 채널과 무관하게 산출된다. worker는 SDK 내장 Bash/Read/Write/Edit로 코드를 작성·실행하고,
advisor arm에서는 `AgentDefinition(model="fable")` 서브에이전트에 위임한다.

## 비교군 (arms)

| key | worker | advisor |
|---|---|---|
| `haiku-solo` | Haiku | — |
| `sonnet-solo` | Sonnet | — |
| `fable-solo` | Fable | — |
| `haiku+fable` | Haiku | Fable |
| `sonnet+fable` | Sonnet | Fable |

## 사전 요건

- Python 3.12+, [uv](https://docs.astral.sh/uv/)
- Node.js + npm, **newman** (`npm install -g newman`; asdf 사용 시 `asdf reshim nodejs`)
- **Claude Code 로그인(구독)**: `~/.claude/.credentials.json` 존재. CI/헤드리스는
  `claude setup-token`으로 `CLAUDE_CODE_OAUTH_TOKEN` 발급.
- 실행 시 하니스가 **`ANTHROPIC_API_KEY`를 자동 unset**(구독 인증 우선). 키를 유지하면 API 과금됨.
- **Fable 접근**이 구독 플랜에 있어야 함(Max 권장).

## 실행

```bash
# 테스트
uv run pytest -q

# 전체 5 arm, N=1
uv run python -m harness.run --collection tasks/Conduit.postman_collection.json

# 일부 arm / 반복 / 턴 상한
uv run python -m harness.run --arms haiku-solo,haiku+fable --n 1 \
  --collection tasks/Conduit.postman_collection.json --max-turns 60
```

결과: `results/<arm>-<n>.json` — `total_cost`(우리 단가 기준), `sdk_cost_usd`(SDK 추정),
`by_model`(모델별 토큰), `worker_turns`, `advisor_calls`, `fallback_used`, `wall_clock_s`,
`grade`(`server_ok`, `passed`/`total`, `failures`).

## 결과 (N=5, 2026-07-05)

25회(5 arm × 5) 실행. 상세·원본: [`docs/results/2026-07-05-advisor-strategy-n5-results.md`](docs/results/2026-07-05-advisor-strategy-n5-results.md)

| Arm | 합격률(per-run) | 회당 비용 | advisor |
|---|---|---|---|
| haiku-solo | 46.4 ± 6.0% | **$0.22** | 0 |
| haiku+fable | 48.0 ± 2.2% | $0.95 | 3 |
| sonnet-solo | 48.3 ± 2.0% | $0.60 | 0 |
| **sonnet+fable** | **50.7 ± 2.1%** | $1.84 | 3 |
| fable-solo | 45.1 ± 1.3% | $1.23 | 0 |

**Advisor 승격폭**: haiku +1.6pp(비용 4.3배), sonnet +2.4pp(비용 3.1배).

**결론**: Advisor는 약한 워커의 재앙 런을 막아 **일관성(분산 축소)**을 주지만(haiku 편차
6.0→2.2pp), 평균 품질 향상(+2pp 내외)은 3~4배 비용을 정당화하지 못한다. 가성비 최적은
`sonnet-solo`(48.3%, $0.60), 품질 최고는 `sonnet+fable`(50.7%, $1.84). "가장 강한 모델 단독"인
`fable-solo`는 조기 종료로 오히려 최하 합격률.

## ⚠️ 주의

- **보안**: worker는 `permission_mode="bypassPermissions"`로 임시 디렉토리에서 **임의 bash를
  사용자 권한으로 실행**한다(LLM이 생성한 명령 포함). **격리 컨테이너/VM/제한 사용자에서 실행**을
  강력 권장.
- **구독 사용량**: 5시간/주간 한도에 합산 차감. 5 arm × 다수 턴(특히 Fable)이 5시간 한도를
  소진할 수 있음. 실행 전 `/usage` 확인. 달러 수치는 토큰×단가 계산값이며 실제 청구가 아님.
- **오버헤드**: Claude Code 시스템 프롬프트로 쿼리당 ~24k 캐시 토큰이 붙는다(모든 arm 공통 →
  상대 비교엔 무영향, 절대비용엔 포함).
- **ToS**: Agent SDK의 구독 인증은 제3자 제품엔 제한 — 개인 연구는 회색지대.

## 알려진 한계

- advisor 서브에이전트에는 SDK가 per-agent fallback을 노출하지 않아, advisor=fable arm의
  advisor refusal엔 fallback이 없다(코딩 과제라 위험 낮음). Fable **worker**엔
  `fallback_model="opus"` 적용.
- advisor 호출 하드캡 대신 `max_turns` 상한 + 프롬프트 힌트 + `advisor_calls` 기록으로 대체.
- Newman 컬렉션은 gothinkster/realworld의 **legacy Postman**(현재는 Bruno/Hurl로 이전됨).
  출처는 `tasks/COLLECTION_SOURCE.txt`. `APIURL`은 `http://localhost:<port>/api`로 주입.
