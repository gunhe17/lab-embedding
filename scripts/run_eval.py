"""2-Step kNN eval — Layer 1 + Layer 2 통합 평가.

OpenAI API는 test text embed 1회만. 이후 numpy로 6가지 전략을 동시 계산.
Layer 1, Layer 2 각각 + Combined 결과를 출력.
"""

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

BASE = Path(__file__).resolve().parent.parent
MODEL = "text-embedding-3-large"

STRATEGIES = [
    {"name": "top-1", "method": "top1"},
    {"name": "majority k=3", "method": "majority", "k": 3},
    {"name": "majority k=5", "method": "majority", "k": 5},
    {"name": "majority k=5 strict", "method": "majority", "k": 5, "min_conf": 0.6},
    {"name": "weighted k=3", "method": "weighted", "k": 3},
    {"name": "weighted k=5", "method": "weighted", "k": 5},
]


def load_index(path: Path) -> tuple[np.ndarray, list[str]]:
    """벡터 파일 로드 → (normed_vectors, labels)"""
    with open(path) as f:
        records = json.load(f)
    labels = [r["_intent_id"] for r in records]
    vecs = np.array([r["embedding_vector"] for r in records], dtype=np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs, labels


def embed_texts(client: OpenAI, texts: list[str]) -> np.ndarray:
    """텍스트 목록을 embed → normed vectors"""
    embs = []
    for i in range(0, len(texts), 50):
        resp = client.embeddings.create(input=texts[i:i+50], model=MODEL)
        embs.extend([d.embedding for d in resp.data])
    vecs = np.array(embs, dtype=np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs


def apply_strategy(strategy: dict, scores: np.ndarray, labels: list[str]) -> tuple[str, float]:
    """채점 전략 적용. (winner_label, best_score) 반환."""
    method = strategy["method"]
    if method == "top1":
        idx = int(np.argmax(scores))
        return labels[idx], float(scores[idx])

    k = min(strategy["k"], len(labels))
    top_k = np.argsort(scores)[-k:][::-1]

    if method == "majority":
        votes = Counter(labels[idx] for idx in top_k)
        winner, count = votes.most_common(1)[0]
        min_conf = strategy.get("min_conf", 0.0)
        if min_conf and count / k < min_conf:
            return "NONE", float(scores[top_k[0]])
        best_score = max(float(scores[idx]) for idx in top_k if labels[idx] == winner)
        return winner, best_score

    if method == "weighted":
        weighted = defaultdict(float)
        for idx in top_k:
            weighted[labels[idx]] += float(scores[idx])
        winner = max(weighted, key=weighted.get)
        best_score = max(float(scores[idx]) for idx in top_k if labels[idx] == winner)
        return winner, best_score

    return "NONE", 0.0


def eval_layer(name: str, train_vecs: np.ndarray, train_labels: list[str],
               test_vecs: np.ndarray, test_labels: list[str]) -> dict:
    """한 layer를 6가지 전략으로 평가. 결과 dict 반환."""
    all_scores = test_vecs @ train_vecs.T
    n = len(test_labels)
    results = {}

    for strategy in STRATEGIES:
        sname = strategy["name"]
        correct = 0
        correct_scores = []
        errors = []
        for i in range(n):
            got, score = apply_strategy(strategy, all_scores[i], train_labels)
            if got == test_labels[i]:
                correct += 1
                correct_scores.append(round(score, 4))
            else:
                errors.append({"text": "", "expected": test_labels[i], "got": got, "score": round(score, 4)})
        acc = round(correct / n * 100, 1)
        results[sname] = {
            "correct": correct, "total": n, "accuracy": acc,
            "errors": errors, "correct_scores": correct_scores,
        }

    return results


def print_table(title: str, results: dict, n: int):
    best_name = max(results, key=lambda k: results[k]["accuracy"])
    print(f"\n### {title}\n")
    print(f"| Strategy | Correct | Acc |")
    print(f"|---|---|---|")
    for strategy in STRATEGIES:
        sname = strategy["name"]
        r = results[sname]
        bold = "**" if sname == best_name else ""
        print(f"| {bold}{sname}{bold} | {bold}{r['correct']}/{r['total']}{bold} | {bold}{r['accuracy']}%{bold} |")


def main():
    client = OpenAI()

    # --- Layer 1 ---
    print("Loading Layer 1...")
    l1_vecs, l1_labels = load_index(BASE / "training" / "layer1" / "knn-vectors.json")

    l1_test_path = BASE / "evaluation" / "layer1" / "eval-test-fixed.csv"
    with open(l1_test_path, encoding="utf-8") as f:
        l1_test = list(csv.DictReader(f))
    l1_test_texts = [r["text"] for r in l1_test]
    l1_test_labels = [r["group"] for r in l1_test]

    print(f"Embedding {len(l1_test_texts)} Layer 1 test texts...")
    l1_test_vecs = embed_texts(client, l1_test_texts)

    l1_results = eval_layer("Layer 1", l1_vecs, l1_labels, l1_test_vecs, l1_test_labels)

    # --- Layer 2 ---
    print("Loading Layer 2...")
    with open(BASE / "datasets" / "layer1-groups.json") as f:
        groups = json.load(f)
    multi_groups = {k: v for k, v in groups.items() if len(v) > 1}

    l2_test_path = BASE / "evaluation" / "layer2" / "eval-test-fixed.csv"
    with open(l2_test_path, encoding="utf-8") as f:
        l2_test = list(csv.DictReader(f))

    # Embed all Layer 2 test texts at once
    l2_test_texts = [r["text"] for r in l2_test]
    print(f"Embedding {len(l2_test_texts)} Layer 2 test texts...")
    l2_test_vecs = embed_texts(client, l2_test_texts)

    # Per-group eval, aggregate
    l2_agg = {s["name"]: {"correct": 0, "total": 0, "errors": [], "correct_scores": []} for s in STRATEGIES}

    for group_name in sorted(multi_groups.keys()):
        vec_path = BASE / "training" / "layer2" / group_name / "knn-vectors.json"
        if not vec_path.exists():
            continue

        g_vecs, g_labels = load_index(vec_path)

        # Filter test for this group
        indices = [i for i, r in enumerate(l2_test) if r["group"] == group_name]
        if not indices:
            continue

        g_test_vecs = l2_test_vecs[indices]
        g_test_labels = [l2_test[i]["tool"] for i in indices]

        g_results = eval_layer(group_name, g_vecs, g_labels, g_test_vecs, g_test_labels)

        for sname, r in g_results.items():
            l2_agg[sname]["correct"] += r["correct"]
            l2_agg[sname]["total"] += r["total"]
            l2_agg[sname]["errors"].extend(r["errors"])
            l2_agg[sname]["correct_scores"].extend(r["correct_scores"])

    # Finalize Layer 2 accuracy
    l2_results = {}
    for sname, agg in l2_agg.items():
        acc = round(agg["correct"] / agg["total"] * 100, 1) if agg["total"] else 0
        l2_results[sname] = {
            "correct": agg["correct"], "total": agg["total"], "accuracy": acc,
            "errors": agg["errors"], "correct_scores": agg["correct_scores"],
        }

    # --- Print ---
    print(f"\n{'='*60}")
    print(f" 2-Step kNN Eval")
    print(f" Layer 1: {len(l1_test)} test | Layer 2: {len(l2_test)} test")
    print(f"{'='*60}")

    print_table("Layer 1 (30 groups)", l1_results, len(l1_test))
    print_table("Layer 2 (26 tools)", l2_results, l2_agg[STRATEGIES[0]["name"]]["total"])

    # Combined
    l1_best = max(l1_results, key=lambda k: l1_results[k]["accuracy"])
    l2_best = max(l2_results, key=lambda k: l2_results[k]["accuracy"])
    combined = round(l1_results[l1_best]["accuracy"] * l2_results[l2_best]["accuracy"] / 100, 1)

    print(f"\n### Combined")
    print(f"\nLayer 1 best: {l1_best} ({l1_results[l1_best]['accuracy']}%)")
    print(f"Layer 2 best: {l2_best} ({l2_results[l2_best]['accuracy']}%)")
    print(f"**Combined: {combined}%**")

    # Errors for Layer 2 best
    errors = l2_results[l2_best]["errors"]
    if errors:
        print(f"\nLayer 2 errors ({l2_best}, {len(errors)}건):")
        for e in errors:
            print(f"  {e['expected']:40s} → {e['got']:35s} ({e['score']})")

    # --- Score 분포 분석 ---
    for layer_name, results, best in [
        ("Layer 1", l1_results, l1_best),
        ("Layer 2", l2_results, l2_best),
    ]:
        r = results[best]
        c_scores = sorted(r["correct_scores"])
        e_scores = sorted([e["score"] for e in r["errors"]])

        print(f"\n### Score 분포 ({layer_name}, {best})\n")
        print(f"{'':>14} {'min':>8} {'p25':>8} {'mean':>8} {'p75':>8} {'max':>8}")

        if c_scores:
            c_arr = np.array(c_scores)
            print(f"  {'correct':>12} {c_arr.min():>8.4f} {np.percentile(c_arr,25):>8.4f} {c_arr.mean():>8.4f} {np.percentile(c_arr,75):>8.4f} {c_arr.max():>8.4f}")

        if e_scores:
            e_arr = np.array(e_scores)
            print(f"  {'error':>12} {e_arr.min():>8.4f} {np.percentile(e_arr,25):>8.4f} {e_arr.mean():>8.4f} {np.percentile(e_arr,75):>8.4f} {e_arr.max():>8.4f}")
        else:
            print(f"  {'error':>12} (없음)")

        # Threshold 제안
        if c_scores and e_scores:
            e_max = max(e_scores)
            # threshold = 오답 max score 바로 위
            suggested = round(e_max + 0.01, 2)
            # 이 threshold 적용 시 결과
            c_pass = sum(1 for s in c_scores if s >= suggested)
            e_reject = sum(1 for s in e_scores if s < suggested)
            print(f"\n  suggested threshold: {suggested}")
            print(f"    correct 중 통과: {c_pass}/{len(c_scores)} ({c_pass/len(c_scores)*100:.1f}%)")
            print(f"    error 중 거부:   {e_reject}/{len(e_scores)} ({e_reject/len(e_scores)*100:.1f}%)")
        elif c_scores and not e_scores:
            print(f"\n  에러 없음 — threshold 불필요 (최소 correct score: {min(c_scores)})")

    # --- OOD (Out-of-Domain) 거부 테스트 ---
    print(f"\n{'='*60}")
    print(f" OOD (Out-of-Domain) Reject Test")
    print(f" Layer 1 best score < reject_threshold이면 거부")
    print(f"{'='*60}")

    ood_samples = [
        "안녕하세요", "고마워", "수고하셨습니다",
        "오늘 날씨 어때?", "지금 몇 시야?", "주말에 뭐 해?",
        "점심 뭐 먹지?", "커피 한 잔 어때?", "노래 추천해줘",
        "주식 어때?", "환율 알려줘", "번역해줘", "계산기 켜줘",
        "ㅋㅋㅋ", "ㅎㅎ", "...", "asdfasdf", "test",
        "그거", "이거", "음", "아",
        "메일 보내줘", "택시 불러줘", "알람 설정해줘",
        "오늘 힘들어", "기분이 안 좋아", "잘 모르겠어",
        "뭘 할 수 있어?", "도와줘", "사용법 알려줘",
    ]

    print(f"\nEmbedding {len(ood_samples)} OOD samples...")
    ood_vecs = embed_texts(client, ood_samples)
    ood_scores_arr = ood_vecs @ l1_vecs.T
    ood_top1 = [float(np.max(ood_scores_arr[i])) for i in range(len(ood_samples))]

    REJECT_THRESHOLD = 0.52
    in_min = min(l1_results[l1_best]["correct_scores"])

    rejected = [(t, s) for t, s in zip(ood_samples, ood_top1) if s < REJECT_THRESHOLD]
    passed = [(t, s) for t, s in zip(ood_samples, ood_top1) if s >= REJECT_THRESHOLD]

    print(f"\nReject threshold: {REJECT_THRESHOLD}")
    print(f"In-domain 최저 score: {in_min:.4f}")
    print(f"\nOOD 거부: {len(rejected)}/{len(ood_samples)} ({len(rejected)/len(ood_samples)*100:.1f}%)")
    print(f"OOD 통과 (false positive): {len(passed)}/{len(ood_samples)}")

    if passed:
        print(f"\nFalse positive (영역 밖인데 통과):")
        for t, s in sorted(passed, key=lambda x: -x[1]):
            print(f"  {s:.4f}  \"{t}\"")

    # In-domain 영향 확인
    in_rejected = [s for s in l1_results[l1_best]["correct_scores"] if s < REJECT_THRESHOLD]
    print(f"\nIn-domain false reject: {len(in_rejected)}/{l1_results[l1_best]['total']}")
    if in_rejected:
        print(f"  거부된 in-domain 최대 score: {max(in_rejected):.4f}")


if __name__ == "__main__":
    main()
