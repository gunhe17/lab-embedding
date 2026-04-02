"""
[1] gen_intent_pool
Input:  input/agent-tool-v1.json
Output: datasets/intent-pool.json, datasets/confusion-groups.json
"""

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
INPUT = BASE / "input" / "agent-tool-v1.json"
OUTPUT_POOL = BASE / "datasets" / "intent-pool.json"
OUTPUT_GROUPS = BASE / "datasets" / "confusion-groups.json"

NONE_INTENTS = []  # NONE intents removed — tool intents only


def extract_facade(name: str) -> str:
    """tool name에서 facade(도메인) 추출.

    schedule.create → schedule
    counseling_case.query → counseling
    counseling.create_case → counseling
    member_working_time.query → member_working_time
    """
    prefix = name.split(".")[0]
    # counseling_case, counseling_session, counseling_note → counseling 그룹
    if prefix.startswith("counseling"):
        return "counseling"
    # assessment_case, assessment_session 등 → assessment 그룹
    if prefix.startswith("assessment"):
        return "assessment"
    # member_invitation, member_working_time 등 → member 그룹
    if prefix.startswith("member"):
        return "member"
    # non_operating_time → operating 그룹
    if prefix == "non_operating_time":
        return "operating"
    # form_instance, form_template, form.* → form 그룹
    if prefix.startswith("form"):
        return "form"
    # client_relation, client_resource → client 그룹
    if prefix.startswith("client"):
        return "client"
    # center_application → center 그룹
    if prefix.startswith("center"):
        return "center"
    # message_log, message_template → message 그룹
    if prefix.startswith("message"):
        return "message"
    # send_link, send_result → send 그룹
    if prefix.startswith("send"):
        return "send"

    return prefix


def make_canonical(tool: dict) -> str:
    """tool description에서 핵심 동작을 추출하여 canonical query 생성."""
    desc = tool.get("description", "")
    # 첫 문장만 사용
    first = desc.split(".")[0].split("합니다")[0].strip()
    if first:
        return first
    return tool["name"]


def main():
    with open(INPUT, encoding="utf-8") as f:
        tools = json.load(f)

    # --- intent-pool.json ---
    intent_pool = []
    for tool in tools:
        intent_pool.append({
            "intent_id": tool["name"],
            "canonical": make_canonical(tool),
            "risk": tool["risk"],
            "facade": extract_facade(tool["name"]),
            "tool_config": {"type": "single", "tool_name": tool["name"]},
            "description": tool.get("description", ""),
        })

    # NONE intents 추가
    intent_pool.extend(NONE_INTENTS)

    # --- confusion-groups.json ---
    groups: dict[str, list[str]] = {}
    for item in intent_pool:
        facade = item["facade"]
        if facade is None:
            continue
        groups.setdefault(facade, []).append(item["intent_id"])

    # 1개짜리 그룹 제거 (혼동 대상 없음)
    groups = {k: sorted(v) for k, v in groups.items() if len(v) > 1}

    # --- 저장 ---
    with open(OUTPUT_POOL, "w", encoding="utf-8") as f:
        json.dump(intent_pool, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_GROUPS, "w", encoding="utf-8") as f:
        json.dump(groups, f, ensure_ascii=False, indent=2)

    # --- 통계 ---
    print(f"Intent pool: {len(intent_pool)} intents")
    print(f"  tool intents: {len(tools)}")
    print(f"  NONE intents: {len(NONE_INTENTS)}")
    print()

    from collections import Counter
    risks = Counter(t["risk"] for t in intent_pool if t["risk"])
    for r, c in risks.most_common():
        print(f"  {r:8s} {c}")
    print()

    print(f"Confusion groups: {len(groups)}")
    for name, members in sorted(groups.items()):
        print(f"  {name} ({len(members)}): {', '.join(members)}")

    print(f"\nSaved: {OUTPUT_POOL}")
    print(f"Saved: {OUTPUT_GROUPS}")


if __name__ == "__main__":
    main()
