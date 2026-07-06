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
| `opus-solo` | Opus | — |
| `deleg-opus` | Opus | Sonnet(계획+검증) |
| `plan-fable-haiku` | Haiku | Fable(계획+검증) |
| `plan-opus-sonnet` | Sonnet | Opus(계획+검증) |

`deleg-opus`·`plan-fable-haiku`는 유튜버 **개발동생**의 Advisor Strategy 변형(**Plan-then-Execute**)이다:
루프 오너가 **플래너(계획·검증)**로서 구현을 **워커(실행자) 서브에이전트**에 `Agent`/`Task`로 위임한 뒤
diff·curl로 검증한다. `deleg-opus`는 Sonnet 계획→Opus 실행, `plan-fable-haiku`는 강한 모델을 계획에·
약한 모델을 실행에 배정하는 **model-splitting**(Fable 계획→Haiku 실행)이다. 워킹스타일 규율은
[`CLAUDE.md`](CLAUDE.md)(§모델 역할 분담)와 [`.claude/agents/worker.md`](.claude/agents/worker.md)에 박제돼 있다.

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

# 전체 7 arm, N=1
uv run python -m harness.run --collection tasks/Conduit.postman_collection.json

# 개발동생 위임 방식만 (opus-solo 기준선 + deleg-opus)
uv run python -m harness.run --arms opus-solo,deleg-opus --n 5 \
  --collection tasks/Conduit.postman_collection.json --max-turns 40
```

결과: `results/<arm>-<n>.json` — `total_cost`(우리 단가 기준), `sdk_cost_usd`(SDK 추정),
`by_model`(모델별 토큰), `worker_turns`, `advisor_calls`, `fallback_used`, `wall_clock_s`,
`grade`(`server_ok`, `passed`/`total`, `failures`).

## 결과 (N=5, 2026-07-05~06)

9 arm × 5회. 상세·원본: [`docs/results/2026-07-05-advisor-strategy-n5-results.md`](docs/results/2026-07-05-advisor-strategy-n5-results.md)

| Arm | 구조 | 부팅 | 합격률(부팅런) | 실질%(실패=0) | 회당 비용 |
|---|---|---|---|---|---|
| haiku-solo | Haiku 단독 | 5/5 | 46.4 ± 6.0% | 46.4 | **$0.22** |
| haiku+fable | Fable 조언→Haiku | 5/5 | 48.0 ± 2.2% | 48.0 | $0.95 |
| sonnet-solo | Sonnet 단독 | 5/5 | 48.3 ± 2.0% | 48.3 | $0.60 |
| **sonnet+fable** | Fable 조언→Sonnet | 5/5 | **50.7 ± 2.1%** | 50.7 | $1.84 |
| fable-solo | Fable 단독 | 5/5 | 45.1 ± 1.3% | 45.1 | $1.23 |
| **opus-solo** | Opus 단독 | 5/5 | 48.8 ± 2.3% | 48.8 | **$0.56** |
| deleg-opus | Sonnet 계획→Opus 실행 | 5/5 | 47.3 ± 0.8% | 47.3 | $2.24 |
| **plan-fable-haiku** | Fable 계획→Haiku 실행 | 5/5 | **49.1 ± 1.8%** | 49.1 | $2.94 |
| plan-opus-sonnet | Opus 계획→Sonnet 실행 | **3/5** | 46.6 ± 1.6% | **28.0** | $1.48 |

**Plan-then-Execute 플래너 3종**(부팅런 기준): Fable→Haiku **49.1%**(5/5) > Sonnet→Opus 47.3%(5/5)
> Opus→Sonnet 46.6%(**3/5**).

**결론**
- **Plan-then-Execute(강한 플래너+약한 실행자)는 품질·일관성을 올린다.** `plan-fable-haiku`가
  Haiku solo 대비 +2.7pp(분산 6.0→1.8pp), **Fable 단독보다도 +4.0pp** — 강한 모델은 실행자보다
  플래너로 쓰는 게 낫다.
- **단, "강한 플래너=최고"는 아니다.** 가장 강한 Opus 플래너(→Sonnet)가 Fable·Sonnet 플래너를
  못 이겼고, **유일하게 부팅 실패(2/5)**로 실질 품질 최저(28.0%). **실행자가 계획을 작동 코드로
  옮기는 역량**이 신뢰성을 좌우한다.
- **강한 플래너의 토큰값이 가성비를 깎는다.** plan-fable-haiku는 회당 $2.94로 최고 — 가성비·품질
  종합 승자는 여전히 **`opus-solo`(48.8%, $0.56)**, 품질 최고는 `sonnet+fable`(50.7%).
- **위임 방식의 진짜 가치인 *검증 규율***은 도그푸딩에서 위임 무음(無音) 버그 2건을 잡아내며
  실증됐다(리포트 §개발동생 참조).

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
