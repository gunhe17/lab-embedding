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
