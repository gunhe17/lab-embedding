# Versioning 규칙

## 버전 체계

`v{major}.{minor}` 형식을 사용한다.

### Major 변경 (v1.0 → v2.0)

- intent 추가/삭제 (input/agent-tool-v1.json 변경)
- 분류 방식 자체 변경 (mean vector → kNN 등)

### Minor 변경 (v1.0 → v1.1)

- variation 보강/수정
- 벡터 재생성
- 채점 방식 튜닝 (k값, threshold 등)

### 버전 불변

- 채점 방식 비교 실험 (같은 데이터로 여러 전략 비교)
- 문서 수정

## 파일별 역할

| 파일 | 역할 | 갱신 시점 |
|---|---|---|
| `VERSION.json` | 현재 버전 메타데이터 | 매 버전 변경 시 |
| `evaluation/results/v{X.Y}.json` | 해당 버전의 평가 결과 | run_eval.py 실행 시 자동 생성 |
| `docs/experiment-log.md` | 전체 실험 이력 | 매 버전 변경 시 추가 |

## 워크플로

```
1. 변경 작업 수행 (variation 보강, tool 추가 등)
2. VERSION.json 업데이트 (version, changes 필드)
3. pipeline 재실행 (해당 step부터)
4. run_eval.py 실행 → evaluation/results/v{X.Y}.json 자동 생성
5. experiment-log.md에 결과 추가
```
