# Advisor Strategy — RealWorld 실험

> **약한 모델에 강한 조언자/플래너를 붙이면 저렴하게 품질이 오를까?**
> Anthropic **Advisor Strategy**와 **Plan-then-Execute** 패턴을 9개 arm × 5회, RealWorld(Conduit)
> 백엔드 자동 구현 + Newman e2e 채점으로 실측했다.

## 한눈에 보는 결론

| 질문 | 답 |
|---|---|
| 조언자/플래너가 품질을 올리나? | **올린다, 그러나 +2~3pp 수준.** 비용은 3~13배 |
| 진짜 효과는? | **분산 축소(일관성).** 약한 워커의 폭망 런을 막아 하한선을 끌어올림 (Haiku 편차 6.0→1.8pp) |
| 강한 모델은 어디에 써야 하나? | **실행자보다 플래너.** Fable 단독 45.1% < Fable계획+Haiku실행 49.1% (**+4.0pp**) |
| 최강 조합은? | 품질 **`sonnet+fable`(50.7%)**, 가성비 **`opus-solo`(48.8%, $0.56)** — 종합 승자는 opus-solo |
| 함정은? | **Opus 플래너는 실행자와 무관하게 부팅 실패**(Sonnet 2/5, Haiku 2/5) — 계획 능력은 모델 등급과 별개 |

**한 줄 요약**: 조언자/플래너 구조는 *점수를 사는 도구가 아니라 일관성을 사는 보험*이다.
평균 품질만 보면 저렴한 강한 모델 단독(`opus-solo`)이 최선이고, 강한 모델을 쓸 거면
실행자가 아니라 **플래너**로 써라.

## 결과 (N=5 × 10 arm, 2026-07-05~08)

| Arm | 구조 | 부팅 | 합격률(부팅런) | 실질%(실패=0) | 회당 비용 |
|---|---|---|---|---|---|
| **sonnet+fable** | Fable 조언→Sonnet | 5/5 | **50.7 ± 2.1%** | 50.7 | $1.84 |
| **plan-fable-haiku** | Fable 계획→Haiku 실행 | 5/5 | 49.1 ± 1.8% | 49.1 | $2.94 |
| **opus-solo** | Opus 단독 | 5/5 | 48.8 ± 2.3% | 48.8 | **$0.56** |
| sonnet-solo | Sonnet 단독 | 5/5 | 48.3 ± 2.0% | 48.3 | $0.60 |
| haiku+fable | Fable 조언→Haiku | 5/5 | 48.0 ± 2.2% | 48.0 | $0.95 |
| deleg-opus | Sonnet 계획→Opus 실행 | 5/5 | 47.3 ± 0.8% | 47.3 | $2.24 |
| plan-opus-sonnet | Opus 계획→Sonnet 실행 | **3/5** | 46.6 ± 1.6% | **28.0** | $1.48 |
| haiku-solo | Haiku 단독 | 5/5 | 46.4 ± 6.0% | 46.4 | **$0.22** |
| fable-solo | Fable 단독 | 5/5 | 45.1 ± 1.3% | 45.1 | $1.23 |
| plan-opus-haiku | Opus 계획→Haiku 실행 | **3/5** | 44.4 ± 4.2% | **26.7** | $1.09 |

합격률은 Newman 체이닝 특성상 per-run `pass/total(%)`로 정규화(분모 226–292 변동). 비용은
토큰 × 공시 단가 계산값(실제 청구 아님). 상세·원본:
[`docs/results/2026-07-05-advisor-strategy-n5-results.md`](docs/results/2026-07-05-advisor-strategy-n5-results.md)

### 승격폭 (조언자/플래너를 붙였을 때)

| 전이 | Δ합격률 | Δ비용 |
|---|---|---|
| haiku-solo → haiku+fable (조언) | +1.6pp | 4.4배 |
| sonnet-solo → sonnet+fable (조언) | **+2.4pp** | 3.1배 |
| haiku-solo → plan-fable-haiku (계획) | **+2.7pp** | 13배 |
| fable-solo → plan-fable-haiku | **+4.0pp** | 2.4배 |
| opus-solo → deleg-opus (계획) | −1.5pp | 4.0배 |

### 발견 4가지

1. **강한 모델은 실행자보다 플래너다 — 단, 플래너 능력은 모델 등급과 별개다.** 모델 강도
   서열은 Fable > Opus > Sonnet > Haiku. 최강 Fable이 직접 다 하면 꼴찌(45.1%)지만, **계획만
   하고 실행을 Haiku에 넘기면 2위(49.1%)**. 그러나 서열 2위 Opus 플래너는 Sonnet 플래너에도
   밀렸다(실질 26.7~28.0% vs 47.3%).

2. **부팅 실패는 실행자가 아니라 Opus 플래너를 따라다닌다.** 같은 Haiku 실행자로 Fable 계획은
   5/5 부팅, **Opus 계획은 3/5**. 실행자를 Sonnet으로 바꿔도 똑같이 3/5 — Opus 플래너 10회 중
   4회 실패, Fable·Sonnet 플래너는 10회 중 0회. **Opus의 계획 자체가 부팅까지 도달하기 어려운
   형태**라는 뜻이다. 부팅런만 봐도 Opus 계획을 받은 Haiku(44.4%)는 **haiku-solo(46.4%)보다
   낮다** — 나쁜 계획은 없느니만 못하다.

3. **조언자/플래너의 본질은 보험이다.** 평균 +2pp 안팎 vs 비용 3~13배로 가성비는 나쁘지만,
   분산이 일관되게 준다(haiku 6.0→1.8~2.2pp). 폭망 런이 용납 안 되는 곳에서만 가치가 있다.

4. **검증 규율은 실증됐다.** 개발동생 방식의 "완료 보고를 믿지 말고 diff·테스트로 검증"은
   이 실험 구현 중 위임이 조용히 0점 나는 무음(無音) 버그 2건(도구명 혼동, 백그라운드
   fire-and-forget)을 잡아냈다. 자율 벤치마크 점수보다 이쪽이 진짜 가치다.

## 실험 구조

### 비교군 (arms)

| key | 패턴 | 플래너/조언자 | 실행자 |
|---|---|---|---|
| `haiku-solo` / `sonnet-solo` / `fable-solo` / `opus-solo` | 단독 | — | 각 모델 |
| `haiku+fable` / `sonnet+fable` | Advisor (하니스가 상담 3회 강제 주입) | Fable | Haiku / Sonnet |
| `deleg-opus` | Plan-then-Execute | Sonnet | Opus |
| `plan-fable-haiku` | Plan-then-Execute (model-splitting) | Fable | Haiku |
| `plan-opus-sonnet` | Plan-then-Execute | Opus | Sonnet |
| `plan-opus-haiku` | Plan-then-Execute | Opus | Haiku |

- **Advisor arm**: 하니스가 루프를 소유(`ClaudeSDKClient`)하고 라운드마다 Fable 상담을 워커
  세션에 주입한다(자발 위임은 0이었음).
- **Plan-then-Execute arm**(유튜버 **개발동생**의 Advisor Strategy 변형): 플래너가 루프를
  소유하고 구현을 실행자 서브에이전트에 `Agent`/`Task`로 위임한 뒤 curl로 직접 검증.
  계보: Plan-and-Solve(ACL 2023) · BabyAGI · LangChain Plan-and-Execute.
  워킹스타일 규율은 [`CLAUDE.md`](CLAUDE.md)(§모델 역할 분담)와
  [`.claude/agents/worker.md`](.claude/agents/worker.md)에 박제.

### 실행 채널

Claude **Agent SDK**(`claude-agent-sdk`)를 **Claude Code 구독 인증**으로 실행한다(per-token
API 과금 없음 — 하니스가 `ANTHROPIC_API_KEY`를 자동 unset). 비용은 토큰 × 공시 단가
(`harness/models.py`)로 계산하므로 결제 채널과 무관하게 산출된다.

### 채점

각 arm이 임시 디렉토리에 Node/Express/SQLite 백엔드를 구현 → `npm start` 부팅 → 헬스체크
(`/api/tags`) → gothinkster RealWorld **Postman 컬렉션**을 Newman으로 실행해 assertion
통과 수를 센다.

## 재현하기

### 사전 요건

- Python 3.12+, [uv](https://docs.astral.sh/uv/) · Node.js + npm · **newman**
  (`npm install -g newman`; asdf는 `asdf reshim nodejs`)
- **Claude Code 로그인(구독)**: `~/.claude/.credentials.json` 존재. 헤드리스는
  `claude setup-token`으로 `CLAUDE_CODE_OAUTH_TOKEN` 발급. **Fable 접근** 플랜 필요(Max 권장).

### 실행

```bash
uv run pytest -q                                   # 테스트 (라이브 API 미호출)

# 전체 9 arm, N=1
uv run python -m harness.run --collection tasks/Conduit.postman_collection.json

# 특정 arm / 반복 횟수
uv run python -m harness.run --arms plan-fable-haiku,opus-solo --n 5 \
  --collection tasks/Conduit.postman_collection.json --max-turns 40
```

결과는 `results/<arm>-<n>.json`: `total_cost`(공시 단가), `sdk_cost_usd`(SDK 추정),
`by_model`(모델별 토큰), `worker_turns`, `advisor_calls`, `fallback_used`,
`grade`(`server_ok`, `passed`/`total`, `failures`).

## ⚠️ 주의

- **보안**: worker는 `bypassPermissions`로 **LLM이 생성한 임의 bash를 사용자 권한으로 실행**한다.
  격리 컨테이너/VM/제한 사용자에서 실행을 강력 권장.
- **구독 사용량**: 5시간/주간 한도에 합산 차감. 실행 전 `/usage` 확인. 달러 수치는 계산값이며
  실제 청구가 아님.
- **오버헤드**: Claude Code 시스템 프롬프트로 쿼리당 ~24k 캐시 토큰(전 arm 공통 → 상대 비교
  유효).
- **ToS**: Agent SDK 구독 인증은 제3자 제품엔 제한 — 개인 연구는 회색지대.

## 알려진 한계

- **N=5**: 방향성은 견고하나 정밀한 효과 크기엔 표본 부족. plan-opus-sonnet의 부팅 실패율
  40%도 노이즈 여지가 있다(단, 타 8개 arm 45회 중 실패 0회와 대비).
- advisor 서브에이전트에 per-agent fallback이 없어 Fable advisor refusal 시 무방비(코딩 과제라
  위험 낮음). Fable이 루프 오너일 땐 `fallback_model="opus"` 적용.
- Newman 컬렉션은 gothinkster **legacy Postman**(현재 upstream은 Bruno/Hurl로 이전, 출처:
  `tasks/COLLECTION_SOURCE.txt`). 요청이 체이닝되어 분모가 런마다 변동 → per-run % 정규화로 대응.

## 문서

- 결과 리포트: [`docs/results/2026-07-05-advisor-strategy-n5-results.md`](docs/results/2026-07-05-advisor-strategy-n5-results.md)
- 설계: `docs/superpowers/specs/2026-07-04-advisor-strategy-realworld-design.md`
- 하니스 가이드: [`CLAUDE.md`](CLAUDE.md)
