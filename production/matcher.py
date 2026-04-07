"""2-Step kNN Intent Matcher — Layer 1 (그룹) → Layer 2 (tool) 매칭."""

import json
import numpy as np
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from openai import OpenAI


@dataclass
class MatchResult:
    tool: str | None          # 최종 매칭된 tool name (None이면 매칭 실패)
    group: str | None         # Layer 1에서 매칭된 그룹명
    score: float              # 최종 best cosine similarity
    confidence: float         # 투표 비율
    reliable: bool = True     # score >= reliable_threshold이면 True (reflex 처리 가능)
    rejected: bool = False    # Layer 1 score < reject_threshold이면 True (영역 밖)
    layer1_score: float = 0.0
    layer2_score: float = 0.0
    top_k: list[dict] = field(default_factory=list)


class KNNIndex:
    """kNN 벡터 인덱스. 벡터 로드 + cosine similarity 검색."""

    def __init__(self, vectors_path: str | Path):
        with open(vectors_path, 'r') as f:
            records = json.load(f)

        self._texts: list[str] = []
        self._labels: list[str] = []
        vectors: list[list[float]] = []

        for r in records:
            self._texts.append(r['text'])
            self._labels.append(r['_intent_id'])
            vectors.append(r['embedding_vector'])

        self._vectors = np.array(vectors, dtype=np.float32)
        norms = np.linalg.norm(self._vectors, axis=1, keepdims=True)
        self._vectors_normed = self._vectors / norms

    @property
    def size(self) -> int:
        return len(self._texts)

    @property
    def labels(self) -> list[str]:
        return self._labels

    def search(self, query_vec_normed: np.ndarray, k: int = 5) -> list[dict]:
        """top-k 이웃 반환. [{label, score}, ...]"""
        scores = query_vec_normed @ self._vectors_normed.T
        top_k_idx = np.argsort(scores)[-k:][::-1]
        return [
            {"label": self._labels[idx], "score": float(scores[idx])}
            for idx in top_k_idx
        ]


def _weighted_vote(top_k: list[dict]) -> tuple[str, float, float]:
    """score 가중 투표. (winner, best_score, confidence) 반환."""
    weighted = defaultdict(float)
    counts = Counter()
    for item in top_k:
        weighted[item['label']] += item['score']
        counts[item['label']] += 1

    winner = max(weighted, key=weighted.get)
    best_score = max(item['score'] for item in top_k if item['label'] == winner)
    confidence = counts[winner] / len(top_k)
    return winner, best_score, confidence


def _majority_vote(top_k: list[dict]) -> tuple[str, float, float]:
    """단순 다수결 투표. (winner, best_score, confidence) 반환."""
    counts = Counter(item['label'] for item in top_k)
    winner, count = counts.most_common(1)[0]
    best_score = max(item['score'] for item in top_k if item['label'] == winner)
    confidence = count / len(top_k)
    return winner, best_score, confidence


class TwoStepMatcher:
    """2-Step kNN Matcher.

    Layer 1: 30개 그룹 중 어디냐 (그룹 분류)
    Layer 2: 그룹 내 tool 중 어떤 거냐 (tool 분류, 2~3개 중 선택)

    19개 그룹은 Layer 1에서 바로 확정 (tool 1개).
    11개 그룹은 Layer 2로 넘어감.
    """

    def __init__(
        self,
        layer1_vectors: str | Path,
        layer2_dir: str | Path,
        groups_path: str | Path,
        openai_client: OpenAI | None = None,
        model: str = "text-embedding-3-large",
        k: int = 5,
        voting: str = "majority",  # "majority" or "weighted"
        reliable_threshold: float = 0.82,  # 이 이상이면 reflex 즉시 처리
        reject_threshold: float = 0.52,    # Layer 1 score가 이 미만이면 영역 밖으로 거부
    ):
        self._client = openai_client or OpenAI()
        self._model = model
        self._k = k
        self._voting = voting
        self._reliable_threshold = reliable_threshold
        self._reject_threshold = reject_threshold

        # Load groups
        with open(groups_path, 'r') as f:
            self._groups: dict[str, list[str]] = json.load(f)

        # Single-tool groups: Layer 1에서 바로 확정
        self._single_groups = {
            name: tools[0] for name, tools in self._groups.items() if len(tools) == 1
        }

        # Multi-tool groups: Layer 2 필요
        self._multi_groups = {
            name: tools for name, tools in self._groups.items() if len(tools) > 1
        }

        # Layer 1 index
        self._layer1 = KNNIndex(layer1_vectors)

        # Layer 2 indexes (그룹별)
        self._layer2: dict[str, KNNIndex] = {}
        layer2_dir = Path(layer2_dir)
        for group_name in self._multi_groups:
            vec_path = layer2_dir / group_name / "knn-vectors.json"
            if vec_path.exists():
                self._layer2[group_name] = KNNIndex(vec_path)

    @property
    def group_count(self) -> int:
        return len(self._groups)

    @property
    def single_group_count(self) -> int:
        return len(self._single_groups)

    @property
    def multi_group_count(self) -> int:
        return len(self._multi_groups)

    def _vote(self, top_k: list[dict]) -> tuple[str, float, float]:
        if self._voting == "weighted":
            return _weighted_vote(top_k)
        return _majority_vote(top_k)

    def _embed(self, text: str) -> np.ndarray:
        resp = self._client.embeddings.create(input=[text], model=self._model)
        vec = np.array(resp.data[0].embedding, dtype=np.float32)
        return vec / np.linalg.norm(vec)

    def match(self, text: str) -> MatchResult:
        """유저 입력을 2-Step으로 매칭.

        반환 분류:
          - rejected=True   → 영역 밖 (Layer 1 score < reject_threshold)
          - reliable=True   → reflex 즉시 처리 가능 (score >= reliable_threshold)
          - 둘 다 False     → 불확실, 후속 파이프라인 위임
        """
        query_vec = self._embed(text)

        # Layer 1: 그룹 분류
        l1_top_k = self._layer1.search(query_vec, k=self._k)
        group, l1_score, l1_conf = self._vote(l1_top_k)

        # 영역 밖 거부 (Layer 1 best score가 너무 낮으면)
        if l1_score < self._reject_threshold:
            return MatchResult(
                tool=None, group=None,
                score=l1_score, confidence=l1_conf,
                reliable=False, rejected=True,
                layer1_score=l1_score,
                top_k=l1_top_k,
            )

        # Single-tool group → 바로 확정
        if group in self._single_groups:
            tool = self._single_groups[group]
            return MatchResult(
                tool=tool, group=group,
                score=l1_score, confidence=l1_conf,
                reliable=l1_score >= self._reliable_threshold,
                layer1_score=l1_score,
                top_k=l1_top_k,
            )

        # Multi-tool group → Layer 2
        if group not in self._layer2:
            return MatchResult(
                tool=None, group=group,
                score=l1_score, confidence=0.0,
                layer1_score=l1_score,
            )

        l2_top_k = self._layer2[group].search(query_vec, k=self._k)
        tool, l2_score, l2_conf = self._vote(l2_top_k)

        return MatchResult(
            tool=tool, group=group,
            score=l2_score, confidence=l2_conf,
            reliable=l2_score >= self._reliable_threshold,
            layer1_score=l1_score,
            layer2_score=l2_score,
            top_k=l2_top_k,
        )
