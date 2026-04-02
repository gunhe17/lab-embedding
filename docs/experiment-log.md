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

## v2.4 — 2-Step kNN (2026-04-02)

**변경**: read 45개 tool만 대상. 2-Step 분류 도입 + Layer별 전용 variation + score threshold.

### Layer 1 (30 groups, test 84건)

| Strategy | Correct | Acc |
|---|---|---|
| **majority k=5** | **84/84** | **100.0%** |
| **weighted k=5** | **84/84** | **100.0%** |
| majority k=3 | 83/84 | 98.8% |
| weighted k=3 | 83/84 | 98.8% |
| top-1 | 79/84 | 94.0% |
| majority k=5 strict | 65/84 | 77.4% |

Score 분포 (majority k=5): 에러 없음. 최소 correct score: 0.549

### Layer 2 (26 tools, test 125건)

| Strategy | Correct | Acc |
|---|---|---|
| **majority k=5** | **119/125** | **95.2%** |
| weighted k=5 | 117/125 | 93.6% |
| majority k=3 | 116/125 | 92.8% |
| weighted k=3 | 116/125 | 92.8% |
| majority k=5 strict | 113/125 | 90.4% |
| top-1 | 111/125 | 88.8% |

Score 분포 (majority k=5):

|  | min | p25 | mean | p75 | max |
|---|---|---|---|---|---|
| correct | 0.5345 | 0.6525 | 0.7482 | 0.8214 | 0.9653 |
| error | 0.6040 | 0.6379 | 0.6695 | 0.6924 | 0.7479 |

**Suggested threshold: 0.76**
- correct 중 통과: 62/119 (52.1%)
- error 중 거부: 6/6 (100%)

→ score ≥ 0.76이면 **reliable** (reflex 처리), score < 0.76이면 후속 파이프라인으로 넘김.
→ 0.76 적용 시 reflex 처리 대상의 정확도는 **100%** (62건 전부 정답).

### Combined

```
Layer 1: 100.0% × Layer 2: 95.2% = 95.2%
```

### 에러 (Layer 2, majority k=5, 6건)

| expected | got | score |
|---|---|---|
| assessment_case.query | assessment_case.validate_update | 0.6981 |
| assessment_case.validate_update | assessment_participant.query | 0.6300 |
| assessment_participant.query | assessment_case.query | 0.7479 |
| client.query | client_resource.query | 0.6617 |
| client_resource.query | client.query | 0.6040 |
| operating_time.check_slot | operating_time.available_slots | 0.6751 |
