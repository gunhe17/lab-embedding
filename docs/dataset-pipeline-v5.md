# Dataset Pipeline v5 — 2-Step kNN Intent Matcher

## 1. 목표

사용자 자연어 입력을 **read 45개 tool** 중 하나로 매칭하는 시스템.
2-Step 구조로 **Layer 1 (그룹 분류) → Layer 2 (tool 분류)**를 수행.

write/delete tool은 매칭 대상이 아님 — 후속 파이프라인에서 처리.

---

## 2. 소스 (Input)

| 파일 | 역할 |
|---|---|
| `input/agent-tool-v1.json` | 114개 tool 정의 |
| `input/real-user-data.json` | 실제 유저 데이터 (variation seed + 평가) |

---

## 3. 2-Step 구조

```
유저 입력
    │
    ▼
Layer 1: 30개 그룹 중 1개 선택 (weighted k=5, 100%)
    │
    ├── 19개 그룹 → 바로 확정 (tool 1개뿐)
    │
    └── 11개 그룹 → Layer 2
          │
          ▼
        Layer 2: 그룹 내 2~3개 tool 중 1개 선택 (majority k=5, 95.2%)
          │
          ▼
        최종 tool 반환
```

### Layer 1 그룹 (30개)

19개 단일 그룹 (Layer 1에서 확정):
상담노트, 상담참여자, 직원휴무, 양식인스턴스, 양식템플릿,
메시지발송, 메시지템플릿, 알림, 센터휴무, 결제,
프로그램, 프로그램배정, 상담실, 검사링크, 검사결과전송,
활동로그, 문서, 필드노트, 기관

11개 다중 그룹 (Layer 2 필요):

| 그룹 | tools |
|---|---|
| 상담케이스 | counseling_case.query, counseling.get, counseling.list |
| 상담회기 | counseling_session.query, counseling.list_session_participants |
| 검사도구 | assessment.query, assessment_set.query |
| 검사케이스 | assessment_case.query, assessment_case.validate_update, assessment_participant.query |
| 검사실행 | assessment_session.query, assessment_task.query |
| 내담자 | client.query, client_relation.query, client_resource.query |
| 직원 | member.query, member_invitation.query |
| 근무시간 | member_working_time.query, member_working_time.available_slots |
| 운영시간 | operating_time.query, operating_time.available_slots, operating_time.check_slot |
| 센터정보 | center.query, center_application.query |
| 일정 | schedule.query, schedule.validate_batch |

---

## 4. Variation 설계

Layer 1과 Layer 2의 variation은 **별도로 생성**.
역할이 다르기 때문:

| | Layer 1 variation | Layer 2 variation |
|---|---|---|
| 목적 | "어떤 그룹이냐" | "그룹 내 어떤 tool이냐" |
| 예시 | "상담 현황", "상담 기록" | "상담 상세 조회" vs "상담 목록" |
| 구분 기준 | 도메인 키워드 | tool 고유 키워드 |

### Variation 생성 규칙

- 존댓말/반말/구어체 mix
- 오타 2~3개/그룹
- 혼동 그룹과 구분되는 키워드 필수
- 파라미터 활용 표현 포함
- 실제 유저 표현(real-user-data.json) 참고

---

## 5. 파일 구조

```
lab-embedding/
├── input/                              # SOURCE
│   ├── agent-tool-v1.json
│   └── real-user-data.json
│
├── datasets/                           # 파이프라인 생성물
│   ├── intent-pool.json                #   114개 tool 정의
│   ├── layer1-groups.json              #   30개 그룹 매핑
│   ├── variations-layer1.json          #   Layer 1 전용 variation
│   └── variations-layer2.json          #   Layer 2 전용 variation
│
├── training/                           # 벡터 DB
│   ├── layer1/knn-vectors.json         #   30그룹 분류용
│   └── layer2/{그룹명}/knn-vectors.json #   그룹별 tool 분류용 (11개)
│
├── evaluation/                         # 평가
│   ├── layer1/
│   │   ├── eval-test-fixed.csv         #   고정 test (84건)
│   │   └── results/
│   └── layer2/
│       ├── eval-test-fixed.csv         #   고정 test (125건)
│       └── results/
│
├── production/                         # 배포용
│   ├── matcher.py                      #   TwoStepMatcher
│   └── __init__.py
│
├── scripts/
│   └── gen_intent_pool.py
│
├── docs/
│   ├── dataset-pipeline-v5.md          #   이 문서
│   ├── experiment-log.md               #   실험 이력
│   └── versioning.md
│
└── VERSION.json
```

---

## 6. Matcher 사용법

```python
from production import TwoStepMatcher

matcher = TwoStepMatcher(
    layer1_vectors="training/layer1/knn-vectors.json",
    layer2_dir="training/layer2",
    groups_path="datasets/layer1-groups.json",
    k=5,
    voting="majority",
)

result = matcher.match("오늘 상담 현황 보여줘")
print(result.tool)        # "counseling_case.query"
print(result.group)       # "상담케이스"
print(result.score)       # 0.89
print(result.confidence)  # 0.8
```

---

## 7. 성능

| Layer | Test | Best Strategy | Acc |
|---|---|---|---|
| Layer 1 | 84건 (고정) | weighted k=5 | **100%** |
| Layer 2 | 125건 (고정) | majority k=5 | **95.2%** |
| **Combined** | | | **95.2%** |

---

## 8. Versioning

`docs/versioning.md` 참조.
- `v{major}.{minor}` — major: intent/구조 변경, minor: variation/벡터 변경
- 실험 이력: `docs/experiment-log.md`
