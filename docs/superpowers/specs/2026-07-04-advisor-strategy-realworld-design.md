# Advisor Strategy RealWorld 실험 — 설계 문서

- 작성일: 2026-07-04
- 상태: 승인 대기 (사용자 리뷰 게이트)

## 1. 목표 (What / Why)

Anthropic의 **Advisor Strategy**(강한 모델이 조언만, 약한 모델이 루프를 소유·실행하는
역전형 멀티모델 패턴)를 **Fable = Advisor**, **Haiku = Worker** 조합으로 검증한다.
벤치마크 과제는 **RealWorld(Conduit) 백엔드 API** — 공식 Newman e2e 테스트 스위트로
품질을 객관적 pass/fail로 측정할 수 있어 측정 실험에 적합하다.

검증하려는 핵심 가설:
1. **약한 모델 승격** — Haiku 단독으로는 낮은 pass율을, Fable의 조언으로 얼마나 끌어올리는가.
2. **비용 대비 품질** — advisor 조합이 Fable 단독 대비 비용을 낮추면서 품질을 유지하는가.
3. **오케스트레이션 패턴 확립** — 재사용 가능한 Advisor-Worker 하니스를 만든다.

RealWorld 앱 자체는 **벤치마크 수단**이며 목적이 아니다.

## 2. 배경 조사에서 확정된 제약 (Non-obvious constraints)

- **"Advisor Strategy"는 실제 Anthropic 서버사이드 툴**(`advisor_20260301`)이며, 통상적
  orchestrator-worker를 역전시킨 구조다. 약한 executor가 메인 루프를 소유하고, 필요할 때
  강한 advisor를 호출해 조언(번호매긴 스텝)을 받는다. advisor는 "pure brain, no hands" —
  툴/파일편집/사용자대면 출력 불가.
- **네이티브 advisor 툴은 Fable-advisor를 지원하지 않는다.** 지원 조합표상 executor(Haiku
  등)의 허용 advisor는 `claude-opus-4-8` / `claude-opus-4-7`뿐이고, Fable은 self-pair
  (Fable executor + Fable advisor)로만 등재된다. 따라서 **Fable-advisor + Haiku-worker는
  커스텀 오케스트레이션으로 구현**한다(Fireworks가 오픈소스 워커 + Opus advisor로 한 방식과
  동일한 개념).
- **승격 효과는 벤치마크로 입증됨(가설에 유리):** BrowseComp에서 Haiku 4.5 단독 19.7% →
  Haiku + Opus advisor 41.2%(2배+), 비용은 Sonnet 단독 대비 -85%. 효과는 executor가
  약할수록 크다.
- **RealWorld를 이 패턴으로 돌린 선례는 없음** → 본 실험은 새로운 시도.
- 위 수치·툴은 assistant 지식 컷오프(2026-01) 이후 자료(Perplexity 인용)라, 실제 SDK/툴
  가용성은 빌드 전 스모크 테스트로 검증한다.

## 2.5 실행 채널 결정 (2026-07-04 개정)

초기 설계는 Anthropic Messages API(유료 API 키)로 직접 오케스트레이션했으나,
**Claude Agent SDK(`claude-agent-sdk`) + Claude Code 구독 인증**으로 전환한다.

- **동기**: per-token API 과금 회피. 구독 사용량 한도(5시간/주간)로 차감.
- **비용 지표 유지**: 비용은 토큰 사용량 × 공시 단가(`models.cost_of`)로 계산하므로,
  결제 채널과 무관하게 산출된다. Agent SDK의 `ResultMessage.modelUsage`(모델별
  input/output/cache 토큰)를 소스로 쓴다 — 기존 수기 usage 배관보다 정확.
- **하니스 재구현 제거**: Agent SDK가 Bash/Read/Write/Edit/Glob/Grep를 내장 제공하므로
  **직접 만든 `tools.py` 샌드박스는 폐기**(기존 도구 재구현 금지 원칙에 부합).
- **advisor 구조**: 공식 패턴대로 `AgentDefinition(model="fable")` **서브에이전트**로
  advisor를 배치하고, worker(haiku/sonnet)가 이를 위임 호출한다. (커스텀 consult 도구의
  중첩 쿼리는 비공식이라 지양.)
- **인증**: `claude setup-token`으로 `CLAUDE_CODE_OAUTH_TOKEN` 발급, `ANTHROPIC_API_KEY`는
  unset. 헤드리스에서 bash가 승인 프롬프트 없이 돌도록 permission mode를 완화.
- **주의**: (a) Agent SDK 구독 인증은 제3자 제품엔 제한 — 개인 연구는 ToS 회색지대,
  위험 인지하고 진행. (b) 5시간 사용량 한도로 5 arm 실험이 도중 소진될 수 있음(Max 권장,
  시작 전 `/usage` 확인). (c) Fable의 구독 접근은 플랜 의존 — 현재 세션에서 Fable 사용
  가능함을 확인.

**하니스 재사용/교체**: 유지 = `models.py`, `metrics.py`(modelUsage 어댑터 추가),
`grade.py`, `run.py`(워커 호출부 교체), `tasks/realworld_spec.md`. 교체 = `worker.py`
(Agent SDK `query`), 삭제 = `tools.py`. `advisor.py`는 Fable 서브에이전트 정의로 축소.

이하 §5의 raw Messages API 세부(§5.1 수동 루프, §5.2 커스텀 consult 도구, `tools.py`
샌드박스)는 이 결정으로 **대체됨**. 나머지(arms, 계측 항목, 채점, 제어, 규모, 산출물)는 유효.

## 3. 모델 및 단가 (2026-07 기준)

| 역할 | 모델 ID | 입력 $/1M | 출력 $/1M | 비고 |
|---|---|---|---|---|
| Advisor | `claude-fable-5` | 10.00 | 50.00 | thinking 상시 ON(파라미터 생략), refusal 가능→fallback 필수, 30일 데이터 보존 필수, prefill 불가 |
| Worker | `claude-haiku-4-5` | 1.00 | 5.00 | 200K ctx, 64K max out, `effort` 파라미터 미지원(에러), thinking은 `{type:"enabled", budget_tokens:N}` 형식 |
| Worker | `claude-sonnet-5` | 3.00 | 15.00 | 도입가 2.00/10.00(2026-08-31까지), adaptive thinking 기본 ON, `effort` low~max/xhigh 지원 |

- Fable arm에는 `betas=["server-side-fallback-2026-06-01"]` +
  `fallbacks=[{"model":"claude-opus-4-8"}]`를 기본 탑재. refusal 시 계측에 별도 표기.
- 비용은 응답 `usage`의 input/output/cache 토큰을 위 단가로 곱해 계산. Sonnet 도입가 적용.

## 4. 비교군 (Arms)

동일한 RealWorld API 과제·동일 스택·격리된 workdir에서 5개 arm 실행.

| arm 키 | worker | advisor | 목적 |
|---|---|---|---|
| `haiku-solo` | Haiku | — | 약한 모델 바닥 |
| `sonnet-solo` | Sonnet | — | 중간 참조선 |
| `fable-solo` | Fable | — | 품질·비용 천장 |
| `haiku+fable` | Haiku | Fable | 본물(약한 워커 승격폭) |
| `sonnet+fable` | Sonnet | Fable | 강한 워커 승격폭 |

## 5. 아키텍처

Python 3.12+ (uv) + 공식 `anthropic` SDK. 단일 하니스가 5 arm을 순차/병렬 실행.

### 5.1 Worker 루프 (executor)
- 수동 에이전트 루프(`client.messages.create` 반복). 도구:
  - `bash_20250124` (Anthropic 정의, client-executed) — 하니스가 workdir 샌드박스에서 실행,
    allowlist·타임아웃·리소스 제한 적용.
  - `text_editor_20250728` (Anthropic 정의, client-executed) — path를 workdir 루트로 정규화
    후 traversal 차단.
  - (advisor arm 한정) `consult_advisor` 커스텀 툴 — 아래 5.2.
- Worker는 RealWorld API 스펙(엔드포인트 명세)과 목표("Newman 스위트를 통과시켜라. 스택은
  Node.js + Express + SQLite")를 시스템/유저 프롬프트로 받는다. **테스트 컬렉션 원본은 워커에
  주지 않는다**(오버피팅 방지) — 채점만 하니스가 수행.
- 종료 조건: worker가 완료 선언(`end_turn`) 또는 최대 반복/토큰/시간 상한 도달.

### 5.2 Advisor 연결 (커스텀 오케)
- `consult_advisor(question, context)` 커스텀 툴을 advisor arm에만 제공.
- 호출 시 하니스가 현재 대화 트랜스크립트 요약 + 최근 diff/에러를 Fable Messages API로 전송.
  advisor 시스템 프롬프트: "너는 조언자다. 코드를 쓰지 말고, 100단어 이내로 번호매긴 실행
  스텝만 반환하라." 응답을 `tool_result`로 worker에 주입.
- 제어: `max_advisor_calls`(기본 3), advisor 응답 `max_tokens=2048`.
- Fable 호출에는 fallback 파라미터·refusal 처리 포함.

### 5.3 계측 (Metrics)
run별로 다음을 JSON에 기록:
- 모델별 input/output/cache 토큰, 계산된 비용($).
- advisor 호출 횟수, worker 반복(턴) 수, wall-clock 초.
- refusal 발생 여부/카테고리, fallback 발동 여부.
- 서버 기동 성공 여부, Newman pass/total, 실패 테스트 목록.

### 5.4 채점 (Grading)
- arm 종료 후 하니스가 workdir에서 `npm install` → 서버 기동(헬스체크) →
  공식 RealWorld **Newman(Postman) e2e 컬렉션**을 실행.
- pass 수 / 전체 수를 품질 지표로 기록. 서버 기동 실패 시 pass=0으로 기록하고 사유 로깅.

### 5.5 제어·안전
- `max_worker_turns`(기본 40–60), `max_advisor_calls`(2–3), per-run 토큰 하드스톱,
  per-run 타임아웃.
- bash 도구는 격리 환경(전용 디렉토리/제한 사용자)에서 실행, allowlist·타임아웃 적용.
- 각 arm은 fresh temp workdir에서 독립 실행(상호 오염 방지).

## 6. 실행 규모

- **파일럿 N=1**: 5 arm 각 1회. 하니스 동작·계측 정확성·Newman 채점을 먼저 검증.
- N은 파라미터로 노출해 이후 N=3+ 확장 가능하게 설계(분산 측정).
- 파일럿 단계에서 실측 비용을 확인한 뒤 규모 확대 여부 결정.

## 7. 산출물

- arm별 결과 표: pass율, 비용($), advisor 호출수, worker 턴수, wall-clock.
- 승격폭 비교: `haiku-solo → haiku+fable`의 Δpass·Δcost, `sonnet-solo → sonnet+fable` 동.
- 비용 대비 품질: `fable-solo` 대비 advisor arm의 pass율·비용 위치.
- 하니스 자체(재사용 가능한 Advisor-Worker 오케스트레이션 코드).

## 8. 컴포넌트 경계 (파일 단위, 예정)

- `harness/models.py` — 모델 상수·단가·비용 계산.
- `harness/tools.py` — bash/text_editor client-side 실행(샌드박스), consult_advisor.
- `harness/advisor.py` — Fable 호출·fallback·advisor 프롬프트.
- `harness/worker.py` — executor 에이전트 루프.
- `harness/metrics.py` — 계측 수집·JSON 기록.
- `harness/grade.py` — 서버 기동·Newman 실행·pass 집계.
- `harness/run.py` — arm 정의·오케스트레이션·CLI(N, arm 선택).
- `tasks/realworld_spec.md` — 워커에 주는 RealWorld API 스펙(테스트 컬렉션 제외).

각 단위는 단일 책임·명확한 인터페이스로 독립 테스트 가능하게 구성.

## 9. 미해결/후속 결정

- Newman 공식 컬렉션의 정확한 소스·버전 고정(빌드 시 확정).
- Haiku thinking 사용 여부(budget_tokens) — 파일럿에서 on/off 비교 고려.
- arm 병렬 실행 여부(비용·레이트리밋 고려) — 파일럿은 순차 권장.
