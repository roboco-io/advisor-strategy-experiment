# Advisor Strategy — RealWorld 실험 결과 (N=5)

> 실행일: 2026-07-05~08 · 50회(10 arm × 5 반복) · 원본: [`n5-raw/`](n5-raw/)
> ※ 본문은 실험 진행 순서대로 누적된 기록이다: §1~4(초기 5 arm) → §개발동생 위임 방식
> (opus-solo·deleg-opus) → §Plan-then-Execute(plan-fable-haiku → 플래너 3종 → **Opus 플래너
> 분리 검증**). 최종 결론은 마지막 절이 우선한다.

## 요약

Anthropic **Advisor Strategy**(강한 모델이 조언만, 약한 모델이 루프를 소유·실행)를
`Fable=advisor`, `Haiku`/`Sonnet`=worker 구성으로 검증했다. 각 arm이 RealWorld(Conduit)
백엔드를 구현하고 공식 Postman 컬렉션(Newman)으로 채점받았다.

**결론: Advisor는 약한 워커의 "재앙 런"을 막아 일관성(분산 축소)을 주지만, 평균 품질
향상폭(+1.6~2.4pp)은 3~4배 비용 증가를 정당화하지 못한다.**

## 결과 표

| Arm | 합격률 (per-run) | pass 범위 | 회당 비용 | advisor 호출 |
|---|---|---|---|---|
| haiku-solo | 46.4 ± 6.0% | 78–154 | **$0.22** | 0 |
| **haiku+fable** | 48.0 ± 2.2% | 115–158 | $0.95 | 3 |
| sonnet-solo | 48.3 ± 2.0% | 125–150 | $0.60 | 0 |
| **sonnet+fable** | **50.7 ± 2.1%** | 125–153 | $1.84 | 3 |
| fable-solo | 45.1 ± 1.3% | 116–127 | $1.23 | 0 |

- **합격률**은 런마다 분모(Newman total)가 226~292로 변동하므로 per-run `pass/total(%)`로
  정규화한 뒤 5회 평균±모표준편차.
- **비용**은 토큰 × 공시 단가(`harness/models.py`) 계산값(실제 청구 아님).

## Advisor 승격폭

| 전이 | 합격률 | Δ | 비용 |
|---|---|---|---|
| haiku-solo → haiku+fable | 46.4% → 48.0% | **+1.6pp** | $0.22 → $0.95 (**4.3배**) |
| sonnet-solo → sonnet+fable | 48.3% → 50.7% | **+2.4pp** | $0.60 → $1.84 (**3.1배**) |

## 핵심 발견

1. **승격폭은 실재하나 작다.** 두 전이 모두 방향이 일관되게 양(+)이지만 +1.6~2.4pp에
   그치고, 비용은 3~4배로 뛴다. 품질/비용 관점에서 Advisor는 본전을 못 뽑는다.

2. **Advisor의 진짜 효과는 평균이 아니라 분산 축소.** haiku-solo는 편차 6.0pp에
   78/226(34%)짜리 폭망 런이 있었으나, haiku+fable은 편차 2.2pp·최저 pass 115로 하한선을
   끌어올렸다. **약한 워커의 재앙 런을 막아 일관성을 준다** — Advisor Strategy 취지와 부합.

3. **"가장 강한 모델 단독"이 최선이 아니다.** fable-solo가 합격률 최하(45.1%)이면서
   haiku+fable보다 비쌌다. 8~12턴 만에 조기 종료(과소 반복)해 오히려 손해.

4. **실용 권고**
   - **최고 품질**: `sonnet+fable` (50.7%, $1.84)
   - **최고 가성비**: `sonnet-solo` (48.3%, $0.60) — advisor 없이 sonnet+fable의 95% 품질을
     1/3 비용에
   - **최저 비용**: `haiku-solo` ($0.22)이나 폭망 위험 있음 → 안정성 필요 시 `haiku+fable`

## 방법론 주의

- **체이닝 컬렉션**: gothinkster 레거시 Postman 컬렉션은 요청이 연쇄되어, 앞 단계 실패 시
  뒤 단계가 스킵되며 분모(total) 자체가 런마다 달라진다. 절대 pass 수 비교는 오해를 부르므로
  per-run 비율로 정규화했다.
- **advisor 강제**: advisor arm은 워커의 자발적 위임이 0이던 문제를 해결하기 위해 하니스가
  라운드마다 Fable 상담을 강제(총 3회)한 설정값이다.
- **시스템 프롬프트 오버헤드**: 모든 SDK query에 ~24k cache-creation 토큰의 Claude Code
  시스템 프롬프트가 실린다(arm 간 상수 → 상대 비교는 유효, 절대 비용에는 포함).
- **N=5의 한계**: 표본이 작아 편차 큰 haiku-solo에서 특히 신뢰구간이 넓다. 방향성은 견고하나
  정밀한 효과 크기 추정에는 더 큰 N이 필요하다.

---

## §개발동생 위임 방식 (opus-solo · deleg-opus)

유튜버 **개발동생**의 Advisor Strategy 변형을 추가 검증했다. 메인 세션이 **Advisor(판단·검증)**,
구현 노동을 **Opus 워커 서브에이전트**에 위임하고 diff·테스트로 검증하는 방식이다. 우리 실험의
"약한 워커 업리프트"와 반대로 **워커가 강한 모델(Opus)**이라는 점이 핵심 차이다.

### 전체 7-arm 결과

| Arm | 워커 | 조언/위임 | 합격률(per-run) | pass 범위 | 회당 비용 |
|---|---|---|---|---|---|
| haiku-solo | Haiku | — | 46.4 ± 6.0% | 78–154 | $0.22 |
| haiku+fable | Haiku | Fable 조언 | 48.0 ± 2.2% | 115–158 | $0.95 |
| sonnet-solo | Sonnet | — | 48.3 ± 2.0% | 125–150 | $0.60 |
| **sonnet+fable** | Sonnet | Fable 조언 | **50.7 ± 2.1%** | 125–153 | $1.84 |
| fable-solo | Fable | — | 45.1 ± 1.3% | 116–127 | $1.23 |
| **opus-solo** | Opus | — | 48.8 ± 2.3% | 125–151 | **$0.56** |
| deleg-opus | Opus | 개발동생 위임+검증 | 47.3 ± 0.8% | 125–140 | $2.24 |

### 판정

| 비교 | 합격률 | 비용 |
|---|---|---|
| opus-solo → deleg-opus | 48.8% → 47.3% (**−1.5pp**) | $0.56 → $2.24 (**4.0배**) |
| sonnet-solo → deleg-opus | 48.3% → 47.3% (−1.0pp) | 3.8배 |

1. **자율 벤치마크에서 위임 방식은 품질을 못 올렸다.** `opus-solo`가 `deleg-opus`보다 더
   정확하고(48.8 vs 47.3%) **4배 저렴**. Sonnet Advisor + Opus Worker를 둘 다 과금하는데, 위임
   오버헤드가 Opus의 실력을 오히려 제약했다(deleg 최고 140 vs opus-solo 최고 151).

2. **분산은 최소(±0.8).** 앞선 5-arm과 동일 패턴 — 위임+검증 구조는 품질이 아니라
   **안정성(하한선)**을 산다.

3. **opus-solo가 숨은 승자.** 강한 워커 단독이 가성비 최상위. 조기 종료로 손해였던 `fable-solo`와
   달리 Opus는 solo로도 충실히 반복했다.

### ⚠️ 이 하니스는 개발동생 방식을 과소평가한다

개발동생 방식은 *인터랙티브 메인 세션*에서 **컨텍스트 분리 + 검증 규율**로 빛나는데, 이 측정은
자율 1회 빌드 품질만 본다. 그 진가는 **구현 과정 도그푸딩에서 직접 드러났다** — deleg-opus를
구현할 때 위임이 조용히 0점 나던 버그 2건을 잡았다:

- **도구명 혼동**: 헤드리스 SDK에서 서브에이전트 소환 도구는 `Agent`/`Task`인데 `allowed_tools`
  누락으로 위임 실패 → 전 회차 0/0(server did not boot). 커밋 `eece68b`.
- **백그라운드 fire-and-forget**: Advisor가 워커를 백그라운드로 던지고 "완료되면 알림받겠다"며
  턴 종료 → 워커가 완성 전에 죽음(Opus 사용량 0). 동기 실행 강제로 해결. 커밋 `e131852`.

두 버그 모두 "advisor=0, 비용 $0.05" 같은 **무음 실패**였고, Advisor가 diff·테스트로 직접
검증했기에 성공으로 오독하지 않았다. **이것이 개발동생 규율(완료 보고를 믿지 말고 검증)의 실효다.**

### 재현

```bash
uv run python -m harness.run --arms opus-solo,deleg-opus --n 5 \
  --collection tasks/Conduit.postman_collection.json --results-dir results --max-turns 40
```

워킹스타일 규율은 `CLAUDE.md`(§모델 역할 분담)와 `.claude/agents/worker.md`(model: opus)에 고정.

---

## §Plan-then-Execute — model-splitting (plan-fable-haiku)

개발동생 위임 방식은 본질적으로 **Plan-then-Execute** 패턴이다: 강한 플래너가 전역 계획을
수립하고, 값싼 실행자가 단계별로 실행한다(계보: Plan-and-Solve ACL 2023 · BabyAGI · LangChain
Plan-and-Execute · ReWOO; Anthropic의 Advisor/orchestrator-worker와 정렬). 이를 **강한 모델=계획,
약한 모델=실행**의 model-splitting으로 순수 검증한 arm이 `plan-fable-haiku`(Fable 계획 → Haiku 실행)다.

### 전체 8-arm 결과

| Arm | 구조 | 합격률(per-run) | pass 범위 | 회당 비용 |
|---|---|---|---|---|
| haiku-solo | Haiku 단독 | 46.4 ± 6.0% | 78–154 | $0.22 |
| haiku+fable | Fable 조언→Haiku | 48.0 ± 2.2% | 115–158 | $0.95 |
| sonnet-solo | Sonnet 단독 | 48.3 ± 2.0% | 125–150 | $0.60 |
| **sonnet+fable** | Fable 조언→Sonnet | **50.7 ± 2.1%** | 125–153 | $1.84 |
| fable-solo | Fable 단독 | 45.1 ± 1.3% | 116–127 | $1.23 |
| **opus-solo** | Opus 단독 | 48.8 ± 2.3% | 125–151 | $0.56 |
| deleg-opus | Sonnet 계획→Opus 실행 | 47.3 ± 0.8% | 125–140 | $2.24 |
| **plan-fable-haiku** | Fable 계획→Haiku 실행 | 49.1 ± 1.8% | 122–147 | $2.94 |

### 판정

| 비교 | 합격률 | 비용 |
|---|---|---|
| haiku-solo → plan-fable-haiku | 46.4% → 49.1% (**+2.7pp**) | 13배 |
| fable-solo → plan-fable-haiku | 45.1% → 49.1% (**+4.0pp**) | 2.4배 |
| deleg-opus → plan-fable-haiku | 47.3% → 49.1% (+1.8pp) | 더 저렴 |

1. **Plan-then-Execute는 품질을 실제로 올린다 — 8개 중 2위(49.1%).** Fable 계획이 Haiku를
   solo 대비 +2.7pp 끌어올렸고 분산도 6.0→1.8pp로 축소. model-splitting 가설이 자율 벤치마크에서도 성립.

2. **강한 모델은 실행자보다 플래너로 써라.** Fable이 다 하는 `fable-solo`(45.1%)보다 **Fable이
   계획만 하고 Haiku가 실행**한 경우(49.1%)가 **+4.0pp 높다**. 강한 모델의 강점은 전역 설계에 있다.

3. **플래너 강도 > 실행자 강도.** `plan-fable-haiku`(Fable계획+Haiku실행, 49.1%)가
   `deleg-opus`(Sonnet계획+Opus실행, 47.3%)보다 높다 — 약한 실행자라도 강한 플래너가 있으면
   강한 실행자+약한 플래너를 이긴다.

4. **그러나 비용이 발목.** Fable 플래너 토큰($10/$50)이 비싸 회당 $2.94로 최고. haiku-solo 대비
   +2.7pp에 13배. 절대 가성비 승자는 여전히 `opus-solo`(48.8%, $0.56).

**종합**: Plan-then-Execute의 품질 효과는 실재하고 "강한 모델 단독"보다도 낫지만(Fable 기준),
강한 플래너의 토큰값 때문에 절대 가성비에선 저렴한 강한 모델 단독에 밀린다. 저렴한 플래너
(예: Sonnet/Haiku 계획)로 갈수록 가성비는 오르나 품질 이득은 줄어드는 트레이드오프.

### 재현

```bash
uv run python -m harness.run --arms plan-fable-haiku --n 5 \
  --collection tasks/Conduit.postman_collection.json --results-dir results --max-turns 40
```

---

## §Plan-then-Execute 플래너 3종 비교 (plan-opus-sonnet 추가)

`plan-opus-sonnet`(Opus 계획 → Sonnet 실행)을 추가해 플래너 강도 스펙트럼을 채웠다. **부팅 실패를
낸 유일한 arm**이라 부팅률과 품질을 분리해 본다.

### 9-arm 전체 (부팅률·실질품질)

| Arm | 구조 | 부팅 | 합격률(부팅런) | 실질%(실패=0) | 비용 |
|---|---|---|---|---|---|
| haiku-solo | Haiku 단독 | 5/5 | 46.4 ± 6.0% | 46.4 | $0.22 |
| haiku+fable | Fable 조언→Haiku | 5/5 | 48.0 ± 2.2% | 48.0 | $0.95 |
| sonnet-solo | Sonnet 단독 | 5/5 | 48.3 ± 2.0% | 48.3 | $0.60 |
| **sonnet+fable** | Fable 조언→Sonnet | 5/5 | **50.7 ± 2.1%** | 50.7 | $1.84 |
| fable-solo | Fable 단독 | 5/5 | 45.1 ± 1.3% | 45.1 | $1.23 |
| **opus-solo** | Opus 단독 | 5/5 | 48.8 ± 2.3% | 48.8 | $0.56 |
| deleg-opus | Sonnet 계획→Opus 실행 | 5/5 | 47.3 ± 0.8% | 47.3 | $2.24 |
| **plan-fable-haiku** | Fable 계획→Haiku 실행 | 5/5 | 49.1 ± 1.8% | 49.1 | $2.94 |
| plan-opus-sonnet | Opus 계획→Sonnet 실행 | **3/5** | 46.6 ± 1.6% | **28.0** | $1.48 |

### 플래너 3종 (부팅런 기준)

| 플래너 → 실행자 | 부팅 | 합격률 | 비용 |
|---|---|---|---|
| Fable → Haiku | 5/5 | **49.1%** | $2.94 |
| Sonnet → Opus | 5/5 | 47.3% | $2.24 |
| Opus → Sonnet | **3/5** | 46.6% | $1.48 |

### 판정 (앞 절 결론의 갱신)

1. **`plan-opus-sonnet`은 신뢰성이 무너졌다 — 부팅 5회 중 2회 실패(40%).** 위임 자체는 정상
   (Opus·Sonnet 모두 소환)이었으나 Sonnet 실행자가 부팅 안 되는 서버를 만들었다. 실패를 0점으로
   반영한 실질 품질은 **28.0%로 전 arm 최저**. (다른 8개 arm은 45회 중 0회 실패 — 대비가 뚜렷하다.)

2. **플래너 강도와 품질이 단조 비례하진 않는다.** 모델 강도 서열은 **Fable > Opus > Sonnet**이고,
   최강 Fable 플래너가 1위(49.1%)인 것은 "플래너 강도" 가설과 부합한다. 그러나 서열 2위 Opus
   플래너가 서열 3위 Sonnet 플래너에도 밀렸다(46.6% < 47.3%) — 강도 서열만으로 결과가 정해지지
   않고, 플래너-실행자 **궁합**이 함께 작용한다.

3. **실행자의 "계획→작동 코드" 역량이 신뢰성을 좌우한다.** 같은 Plan-then-Execute라도 Opus→Sonnet은
   부팅 실패, Fable→Haiku·Sonnet→Opus는 5/5 성공. 플래너 못지않게 실행자가 계획을 실제 작동 코드로
   옮기는 능력이 결과를 가른다.

4. **가성비·품질 종합 승자는 변함없이 `opus-solo`(48.8%, $0.56).** Plan-then-Execute 3종 모두 이를
   넘지 못했다.

> ⚠️ N=5라 40% 부팅 실패가 노이즈일 여지는 있으나, 다른 8개 arm이 45회 중 0회 실패한 것과 대비되어
> 실재 신뢰성 문제로 판단한다. 정밀 추정엔 더 큰 N 필요.

### 재현

```bash
uv run python -m harness.run --arms plan-opus-sonnet --n 5 \
  --collection tasks/Conduit.postman_collection.json --results-dir results --max-turns 40
```

---

## §Opus 플래너 분리 검증 (plan-opus-haiku, 2026-07-08)

`plan-opus-sonnet`의 부팅 실패(2/5)가 **플래너 탓인지 실행자 궁합 탓인지** 분리하기 위해
실행자만 Haiku로 바꾼 `plan-opus-haiku`(Opus 계획 → Haiku 실행)를 추가했다.

### 결과 (N=5)

| 지표 | 값 |
|---|---|
| 부팅 | **3/5** (2회 실패, plan-opus-sonnet과 동일) |
| 합격률(부팅런) | 44.4 ± 4.2% |
| 실질%(실패=0) | **26.7%** (전 arm 최저) |
| 회당 비용 | $1.09 |

### 플래너 4종 최종 비교

| 플래너 → 실행자 | 부팅 | 부팅런 합격률 | 실질% |
|---|---|---|---|
| Fable → Haiku | **5/5** | **49.1%** | 49.1 |
| Sonnet → Opus | **5/5** | 47.3% | 47.3 |
| Opus → Sonnet | 3/5 | 46.6% | 28.0 |
| Opus → Haiku | 3/5 | 44.4% | 26.7 |

### 판정 — 앞 절 결론의 교체

1. **부팅 실패는 실행자가 아니라 Opus 플래너를 따라다닌다.** 같은 Haiku 실행자로 Fable 계획은
   5/5, Opus 계획은 3/5. 실행자를 바꿔도(Sonnet↔Haiku) Opus 플래너는 똑같이 2회 실패 —
   **Opus 플래너 10회 중 4회 실패, Fable·Sonnet 플래너는 10회 중 0회.**

2. **앞 절의 "실행자의 계획→작동 코드 역량이 신뢰성을 좌우한다"(§플래너 3종 판정 3)는 기각.**
   실행자 무관하게 실패가 재현됐으므로, **Opus가 만드는 계획 자체가 부팅까지 도달하기 어려운
   형태**(과도한 복잡성 또는 불완전한 마무리 지시로 추정)라는 해석이 유력하다.

3. **나쁜 계획은 없느니만 못하다.** Opus 계획을 받은 Haiku는 부팅된 런에서도 44.4%로
   **haiku-solo(46.4%)보다 낮다.** Fable 계획은 같은 Haiku를 +2.7pp 끌어올렸다(49.1%) —
   플래너의 가치는 모델 등급이 아니라 **실행 가능한 계획을 쓰는 능력**에서 나오고, 이 과제에선
   Fable만 그것을 해냈다.

4. **실질 품질 최종 서열**: Fable 플래너(49.1) ≫ Sonnet 플래너(47.3) ≫ Opus 플래너(26.7~28.0,
   신뢰성 붕괴).

> ⚠️ N=5 × 2 조합이지만 Opus 플래너 실패 4/10 vs 타 플래너 0/10의 대비는 우연으로 보기 어렵다.

### 재현

```bash
uv run python -m harness.run --arms plan-opus-haiku --n 5 \
  --collection tasks/Conduit.postman_collection.json --results-dir results --max-turns 40
```
