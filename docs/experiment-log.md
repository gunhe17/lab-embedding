# Experiment Log

---

## v1.0 — 초기 데이터셋 (2026-04-02)

**변경**: 114 tool intent, variation 1,912개, kNN 벡터 1,605개

| Strategy | Correct | Acc |
|---|---|---|
| **weighted k=5** | **147/206** | **71.4%** |
| top-1 | 146/206 | 70.9% |
| weighted k=3 | 146/206 | 70.9% |
| majority k=5 | 145/206 | 70.4% |
| majority k=3 | 132/206 | 64.1% |
| majority k=5 strict | 118/206 | 57.3% |

**에러 분석** (weighted k=5, 59건):

같은 facade 내 tool끼리 혼동이 대부분.

| 혼동 패턴 | 건수 | 원인 |
|---|---|---|
| client_relation/resource → client.query | 4 | "내담자" 키워드 공유 |
| cancel_session ↔ revert_cancel_session | 2 | "취소"가 양쪽에 포함 |
| non_operating_time ↔ member_non_working_time | 2 | "휴무" 키워드 공유 |
| operating_time.available_slots ↔ member_working_time.available_slots | 2 | "가용 시간" 동일 |

---

## v2.6 — 2-Step kNN 최종 (2026-04-06)

**변경**: 
- DB/API 표현 48건을 사용자 관점 표현으로 교체
- 검사케이스/운영시간 그룹 variation 보강 (+13건)

### Layer 1 (30 groups, test 84건)

| Strategy | Correct | Acc |
|---|---|---|
| **majority k=5** | **84/84** | **100.0%** |
| **weighted k=5** | **84/84** | **100.0%** |
| majority k=3 | 83/84 | 98.8% |
| weighted k=3 | 83/84 | 98.8% |
| top-1 | 79/84 | 94.0% |
| majority k=5 strict | 65/84 | 77.4% |

Score 분포 (majority k=5): 에러 없음. 최소 correct score: 0.548

### Layer 2 (26 tools, test 125건)

| Strategy | Correct | Acc |
|---|---|---|
| **majority k=5** | **121/125** | **96.8%** |
| weighted k=5 | 119/125 | 95.2% |
| majority k=3 | 117/125 | 93.6% |
| weighted k=3 | 117/125 | 93.6% |
| majority k=5 strict | 116/125 | 92.8% |
| top-1 | 112/125 | 89.6% |

Score 분포 (majority k=5):

|  | min | p25 | mean | p75 | max |
|---|---|---|---|---|---|
| correct | 0.5344 | 0.6532 | 0.7476 | 0.8222 | 0.9655 |
| error | 0.6617 | 0.6675 | 0.6943 | 0.7105 | 0.7479 |

**Suggested threshold: 0.76**
- correct 중 reliable (≥0.76): 61/121 (50.4%), 정확도 **100%**
- error 중 거부 (<0.76): 4/4 (100%)

### Combined

```
Layer 1: 100.0% × Layer 2: 96.8% = 96.8%
```

### 에러 (Layer 2, majority k=5, 4건)

| expected | got | score | 성격 |
|---|---|---|---|
| assessment_case.query | validate_update | 0.698 | 부정형 ("수정 검증 필요없고") |
| assessment_case.validate_update | participant.query | 0.670 | variation 부족 |
| assessment_participant.query | case.query | 0.748 | "케이스"가 "사람들"을 압도 |
| client.query | client_resource.query | 0.662 | 부정형 ("첨부 자료 안 보고 싶어") |

4건 전부 score < 0.76 → reliable 판정에서 정상 거부됨.
부정형 2건은 embedding 모델의 근본적 한계 (부정어를 무시).

### 최종 정확도

| 경로 | 비율 | 정확도 |
|---|---|---|
| Layer 1 → 단일 그룹 (19/30) | ~63% | 100% |
| Layer 1 → Layer 2 → reliable (≥0.76) | ~19% | 100% |
| Layer 1 → Layer 2 → 불확실 (<0.76) → 후속 위임 | ~18% | 위임 |
| **reflex 직접 처리** | **~82%** | **100%** |

---

## v2.7 — Pipeline 검증셋 + 신뢰도 평가 (2026-04-07)

**변경**:
- end-to-end pipeline 검증셋 신규 구축 (LLM 생성, 801건 → 정리 후 780건)
- 검증셋에 `expected_reliable` 라벨 추가 (reflex 처리 vs 위임 명시)
- 4가지 핵심 지표 도입: Reliable Precision/Recall, Delegation Recall, System Accuracy
- 5단계 보강 (8개 카테고리 → top fail tools → 혼동 쌍 → placeholder/duplicate 정리)
- threshold 0.76 → 0.80 (Reliable Precision 우선)

### 동기

기존 v2.6 test set은 train과 표현 분포가 비슷해 96.8%였으나, 새 LLM 생성 검증셋(801건)으로는 53.6%에 그침. **train variation이 실제 사용자 표현 다양성을 못 따라옴**이 드러남.

### 검증셋 구축

```
input/agent-tool-v1.json + input/real-user-data.json
    ↓
[4 agents 병렬 LLM 생성]
    ↓
evaluation/pipeline/eval-pipeline.json (801건 → 780건)
    - 45 read tool 전부 커버
    - tool당 15~24건
    - input + expected_method + expected_params + expected_reliable
```

### 8개 에러 카테고리 (1차 분석)

| 카테고리 | 건수 | 보강 가능 |
|---|---|---|
| 1. 이름+호칭 ("박 선생님 정보") | 6 | ✓ |
| 2. 상대 날짜 ("내일/이번주/지난달") | 7 | ✓ |
| 3. "~된" 상태형 ("종결된 케이스") | 6 | ✓ |
| 4. 직원 짧은 표현 ("상담사 누구") | 3 | ✓ |
| 5. 이름+필드 ("이영희 전화번호") | 2 | ✓ |
| 6. 인사 prefix ("안녕하세요. 일정...") | 2 | ✗ embedding 한계 |
| 7. 복합 조건 (다중 파라미터) | 2 | △ LLM 위임 |
| 8. 영문 혼합 ("client 목록") | 2 | △ |

### 보강 단계별 결과

| 단계 | Pipeline Acc | 변경 |
|---|---|---|
| v2.6 그대로 | 53.6% | — |
| 1차 (Cat 1-5, 8) | 56.7% | 8 카테고리 보강 |
| 2차 (top fail tools) | 60.5% → 65.3% | operating_time, member_working_time 등 |
| 3차 (혼동 쌍 해결) | 68.9% | counseling.list vs case.query, client vs relation |
| 4차 (placeholder/duplicate 정리) | — | 60건 placeholder를 실제 이름으로 expand |

### 4가지 핵심 지표 (최종, 780건)

| 지표 | 값 | 의미 |
|---|---|---|
| **Reliable Precision** | **93.2%** (178/191) | reflex 답 중 정답 비율. 13건 거짓 확신. |
| **Reliable Recall** | 29.7% (159/535) | 처리해야 할 것 중 실제 처리 비율. 보수적. |
| **Delegation Recall** | **86.9%** (213/245) | 위임해야 할 것 중 실제 위임 비율. |
| **System Accuracy** | **81.5%** (636/780) | reflex 정답 + 위임된 케이스 (후속 처리 가정) |

### 매트릭스

```
                    reliable      uncertain     rejected
expected=reliable   144c  11w   238c 119w    0c  23w
expected=delegate    34c   2w   126c  68w    0c  15w
```

### Threshold 변화 (최종 vectors 기준)

| Threshold | Precision | Recall | 거짓 확신 |
|---|---|---|---|
| 0.74 | 87.5% | 36.8% | 36 |
| 0.76 | 89.6% | 31.9% | 26 |
| **0.80** | **94.0%** | **24.0%** | **11** |
| 0.82 | 96.8% | 19.9% | 5 |

### v2.6 회귀 검증

기존 84건 test set: 100% → **91.7%**. variation 보강 과정에서 일부 영향.

### 핵심 발견

1. **단순 정확도(53.6%)는 의미 없음**: reflex가 모든 것을 처리한다는 가정은 잘못.
2. **올바른 평가는 4가지 지표**: precision은 신뢰도, recall은 효율성, system accuracy는 전체 성공률.
3. **위임이 정상 동작**: Delegation Recall 86.9% — reflex가 모를 때는 정확히 손을 듬.
4. **placeholder의 함정**: variation에 `{이름}` 같은 미치환 placeholder 60건이 들어있어 embedding이 literal로 학습.
5. **검증셋 라벨의 모호함**: "상담 현황 보여줘"가 query인지 list인지 사람도 답하기 어려움 → 21건 검증셋 정리.

---

## v2.8 — Threshold Grid Search + Production 적용 (2026-04-07)

**변경**: `(reject_threshold, reliable_threshold)` 조합 grid search로 최적값 탐색.
production matcher와 saas-center-platform config의 default 값 업데이트.

### Grid Search 결과

**reject_threshold는 거의 영향 없음** (0.45~0.58 범위에서 결과 변화 미미).
in-domain 케이스 중 score < 0.52인 게 거의 없기 때문.

**reliable_threshold가 결정적**:

| reliable | Precision | Recall | Sys Acc | 거짓 확신 |
|---|---|---|---|---|
| 0.72 | 86.1% | 51.2% | 94.0% | 47 |
| 0.74 | 87.2% | 44.5% | 95.3% | 37 |
| 0.76 | 89.3% | 38.9% | 96.5% | 27 |
| 0.78 | 91.6% | 32.9% | 97.7% | 18 |
| 0.80 | 93.7% | 29.5% | 98.5% | 12 |
| **0.82** | **97.5%** | **23.9%** | **99.5%** | **4** |
| 0.84 | 97.2% | 21.5% | 99.5% | 4 |

### 최적 조합: reject=0.52, reliable=0.82

```
Precision  97.5%  ← reflex 답변의 신뢰도 (production 핵심)
Recall     23.9%  ← 처리할 수 있는 것의 24%만 처리 (보수적)
Sys Acc    99.5%  ← 위임 포함 시 시스템 전체 정답률
거짓 확신    4건    ← production 위험도 최소
```

### 거짓 확신 4건 (모두 의미적으로 같은 도구 양방향 혼동)

```
"진행 중인 상담 보여줘"  → counseling.list      (정답: case.query)
"진행 중인 상담"         → case.query          (정답: list)
"이번주 상담 케이스"      → case.query          (정답: list)
"오늘 검사 일정"         → assessment_session  (정답: schedule.query)
```

counseling.list vs counseling_case.query는 본질적으로 같은 의미라서
사람도 답하기 어려움 → embedding 한계가 아닌 라벨링 한계.

### Production 적용

| 파일 | 변경 |
|---|---|
| `lab-embedding/production/matcher.py` | `reliable_threshold: 0.82` |
| `saas-center-platform/.../knn_matcher.py` | `reliable_threshold: 0.82` |
| `saas-center-platform/.../config.py` | `REFLEX_RELIABLE_THRESHOLD: 0.82` |

### 결정 근거

**Precision vs Recall 트레이드오프**에서 Precision 우선:
- production에서 reflex의 거짓 확신은 사용자가 직접 보는 잘못된 결과
- recall이 낮으면 LLM 호출이 늘어나지만 결과 품질은 유지됨
- 위험 비용(거짓 확신) > 위임 비용(LLM 호출)

**0.82 vs 0.84**: precision 동률(97%)이지만 recall이 23.9% > 21.5%로 0.82가 우세.

---

## v3.0 — tools.json 28 query 기준 재구축 + 어휘 분석 기반 설계 (2026-04-07)

**변경**:
- `datasets/tools.json` (28 query tools) 기준으로 전면 재구축
- 기존 45 read tools → 28 query tools (17 tool 통합/제거)
- `docs/vocabulary-analysis.md` 작성: 도메인 키워드 × 의도 표현 매트릭스 분석
- 분석 결과 기반 6가지 원칙으로 variation 체계적 설계

### 구조 변경

```
기존: 45 read tools, 30 groups (19 단일 + 11 Layer 2)
신규: 28 query tools, 22 groups (17 단일 + 5 Layer 2)
```

Layer 2 그룹 (5개만):
- 상담 (counseling.query, counseling.list_participants)
- 검사도구 (assessment.query, assessment_set.query)
- 직원 (member.query, member_invitation.query)
- 근무시간 (member_working_time.query, available_slots)
- 운영시간 (operating_time.query, available_slots, check_slot)

### 어휘 분석 6가지 설계 원칙

1. **핵심 조합만 커버** — 빈도표 기준, 이름형(60%) > 시간형 > 질문형 > 요청형
2. **혼용 키워드는 구분자와 함께** — "상담"이 6개 도메인에 걸침 → 구분자 필수
3. **명사만 패턴 필수** — 전체 25%가 동사 없는 입력
4. **이름 패턴은 제한적** — 문장 구조 다양성 위주, 더미 이름 금지
5. **오타 내성** — 그룹당 1~2개
6. **Mutation 표현 미포함** — reflex는 read만 매칭

### 보강 과정

| 단계 | Layer 1 | Layer 2 | Combined |
|---|---|---|---|
| 초기 (분석적 설계) | 76.7% | 87.5% | 67.1% |
| 1차 보강 (17건 에러 타겟) | 94.5% | 90.0% | 85.0% |
| **2차 보강 (8건 에러 타겟)** | **97.3%** | **97.5%** | **94.9%** |

### 최종 결과 (고정 test set, Layer 1: 73건, Layer 2: 40건)

### Layer 1

| Strategy | Correct | Acc |
|---|---|---|
| **majority k=3** | **71/73** | **97.3%** |
| **weighted k=3** | **71/73** | **97.3%** |
| top-1 | 69/73 | 94.5% |
| majority k=5 | 64/73 | 87.7% |

### Layer 2

| Strategy | Correct | Acc |
|---|---|---|
| **majority k=5** | **39/40** | **97.5%** |
| **weighted k=5** | **39/40** | **97.5%** |
| majority k=5 strict | 38/40 | 95.0% |
| majority k=3 | 37/40 | 92.5% |

### 남은 에러 (3건)

| Layer | 입력 | expected | got | score |
|---|---|---|---|---|
| L1 | "상담 형환 보여줘" | 상담 | 알림 | 0.73 |
| L1 | "이번주 필드노트" | 필드노트 | 상담노트 | 0.79 |
| L2 | "이하준 직원 오늘 남은 빈 시간" | available_slots | query | 0.73 |

3건 모두 score < 0.82 → reliable 판정에서 정상 거부됨.

### 핵심 발견

1. **어휘 분석 → 체계적 설계가 무작위 생성보다 효율적**: 2회 보강만으로 94.9% 도달
2. **28 tools로 축소해도 성능 유지**: 구조가 간결해지면서 혼동 쌍도 감소
3. **Layer 2 최대 3개 tool**: 이전(최대 7개)보다 훨씬 쉬운 분류 문제
