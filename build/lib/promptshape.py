"""promptshape —— 把一段提示词拆成可核查的结构。

设计原则：
1. **不改写**。这个工具只做逆向工程：把提示词还原成槽位结构。
2. **缺失要显式**。少哪个槽位直接标出来，不靠「读起来好像有」。
3. **矛盾要并排列出**。两句要求互相打架时，把两句并排放在输出里，
   而不是替用户猜哪句是本意。

槽位定义：角色 / 任务 / 约束 / 示例 / 输出格式。

仅依赖 Python 标准库。

用法:
    python promptshape.py --help
    python promptshape.py --file prompt.txt
    python promptshape.py --text "你是... 请... 输出 JSON"
    python promptshape.py --file prompt.txt --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys

# ---------------------------------------------------------------------------
# 槽位识别规则
# ---------------------------------------------------------------------------

SLOTS = ("role", "task", "constraint", "example", "format")

SLOT_LABEL = {
    "role": "角色",
    "task": "任务",
    "constraint": "约束",
    "example": "示例",
    "format": "输出格式",
}

# 每个槽位的识别特征。宁可少标，也不要把普通句子算成某个槽位。
SLOT_RULES: dict[str, list[re.Pattern]] = {
    "role": [
        re.compile(r"^\s*(你是|你作为|请扮演|扮演)"),
        re.compile(r"^\s*(act as|you are)\b", re.I),
        re.compile(r"^\s*我的身份是", re.I),
    ],
    "task": [
        re.compile(r"^\s*(请|帮我|需要|任务是|目标|请完成|请分析|请生成|请检查)"),
        re.compile(r"^\s*(analyze|generate|write|review|check|summarize)\b", re.I),
    ],
    "constraint": [
        re.compile(r"^\s*(不要|不得|禁止|必须|只能|至多|至少|不超过|不超过|"
                   r"限制|要求|只能使用|仅|最多|最少|不得包含)"),
        re.compile(r"\b(must not|do not|never|only|at most|at least|no more than)\b", re.I),
    ],
    "example": [
        re.compile(r"^\s*(例如|比如|例子|示例|样例|输入示例|输出示例)"),
        re.compile(r"^\s*(for example|e\.g\.|example[s]?:)", re.I),
        re.compile(r"^\s*[-*]\s.*[:：]\s*$"),
    ],
    "format": [
        re.compile(r"^\s*(输出|返回|结果|回答|回复)\s*(格式|形式|结构|样式|用|为)"),
        re.compile(r"^\s*(请)?(以|用)\s*(JSON|XML|YAML|CSV|Markdown|表格|列表|纯文本)\s*"
                   r"(格式|输出|返回|形式)?"),
        re.compile(r"\b(return|respond with|output)\s+(in\s+)?(json|xml|yaml|csv|markdown)\b", re.I),
        re.compile(r"^\s*(格式|结构)\s*[:：]"),
    ],
}

# 冲突判定：同一槽位里，两条要求方向相反。
# 规则写成 (正则, 冲突正则, 说明) —— 两条都命中才算冲突。
CONFLICT_RULES: list[tuple[re.Pattern, re.Pattern, str]] = [
    (re.compile(r"(只|仅|limit|only)\s*(用|使用)?\s*(一|1)\s*(句|行|段|words?|sentence)", re.I),
     re.compile(r"(至少|不少于|more than|至少)\s*(\d+|两|三|几)", re.I),
     "长度要求冲突：一处要求「只写一句」，另一处要求「至少若干」"),
    (re.compile(r"(不要|禁止|不得|never|do not use)\s*[^\n]{0,20}(JSON|json)", re.I),
     re.compile(r"(以|用|返回|输出)\s*JSON", re.I),
     "格式要求冲突：一处禁止 JSON，另一处要求 JSON 输出"),
    (re.compile(r"(不要|禁止|不得|never)\s*[^\n]{0,12}(代码|code)", re.I),
     re.compile(r"(写|给出|生成|提供)\s*[^\n]{0,8}代码", re.I),
     "内容要求冲突：一处禁止代码，另一处要求给代码"),
    (re.compile(r"(简短|简洁|精炼|一句话|briefly|concise)", re.I),
     re.compile(r"(详细|详尽|逐步|step.by.step|详细说明|in detail)", re.I),
     "详略要求冲突：一处要求简短，另一处要求详细"),
    (re.compile(r"(必须|一定要|务必)\s*[^\n]{0,10}(包含|包括)", re.I),
     re.compile(r"(不要|不得|禁止)\s*[^\n]{0,10}(包含|包括)", re.I),
     "包含要求冲突：一处要求必须包含，另一处禁止包含"),
]

# 槽位里的关键信息（用来判断「这个槽位到底说了什么」）
SLOT_PROBE = {
    "role": re.compile(r"你是[^，。\n]{2,30}|扮演[^，。\n]{2,30}", re.I),
    "task": re.compile(r"(请|帮我|需要)[^，。\n]{2,40}"),
    "constraint": re.compile(r"(不要|不得|必须|只能|至多|至少|不超过)[^，。\n]{2,40}"),
    "format": re.compile(r"(JSON|XML|YAML|CSV|Markdown|表格|列表|纯文本)", re.I),
}

REQUIRED_SLOTS = ("role", "task")


# ---------------------------------------------------------------------------
# 分析
# ---------------------------------------------------------------------------

def split_sentences(text: str) -> list[str]:
    """按句切分。中文按句号/问号/感叹号/分号，英文按句点（避开小数与缩写）。"""
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # 先按中英文句末标点切
        parts = re.split(r"(?<=[。！？；])\s*|(?<=[.!?])\s+(?=[A-Z一-鿿])", line)
        for p in parts:
            p = p.strip()
            if p:
                lines.append(p)
    return lines


def classify(sentence: str) -> list[str]:
    """判断一句话落进哪些槽位。一个句子可能同时是多个槽位。"""
    hits: list[str] = []
    for slot, rules in SLOT_RULES.items():
        if any(r.search(sentence) for r in rules):
            hits.append(slot)
    return hits


def find_conflicts(sentences: list[str]) -> list[dict]:
    """找出互相冲突的要求。"""
    conflicts: list[dict] = []
    for i, a in enumerate(sentences):
        for j in range(i + 1, len(sentences)):
            b = sentences[j]
            for pa, pb, why in CONFLICT_RULES:
                if pa.search(a) and pb.search(b):
                    conflicts.append({
                        "reason": why,
                        "a": {"index": i, "text": a},
                        "b": {"index": j, "text": b},
                    })
                elif pb.search(a) and pa.search(b):
                    conflicts.append({
                        "reason": why,
                        "a": {"index": j, "text": b},
                        "b": {"index": i, "text": a},
                    })
    return conflicts


def analyze(text: str) -> dict:
    """把一段提示词拆成结构化结果。"""
    sentences = split_sentences(text)
    slots: dict[str, list[dict]] = {s: [] for s in SLOTS}
    unclassified: list[str] = []

    for idx, sent in enumerate(sentences):
        hits = classify(sent)
        if not hits:
            unclassified.append(sent)
            continue
        for slot in hits:
            probe = SLOT_PROBE.get(slot)
            detail = ""
            if probe:
                m = probe.search(sent)
                if m:
                    detail = m.group(0)
            slots[slot].append({
                "index": idx,
                "text": sent,
                "detail": detail,
            })

    missing = [s for s in REQUIRED_SLOTS if not slots[s]]
    conflicts = find_conflicts(sentences)

    return {
        "sentence_count": len(sentences),
        "slots": {s: slots[s] for s in SLOTS},
        "missing_required": missing,
        "conflicts": conflicts,
        "unclassified": unclassified,
        "coverage": {
            "filled": sum(1 for s in SLOTS if slots[s]),
            "total": len(SLOTS),
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def render(result: dict) -> str:
    out: list[str] = []
    out.append(f"句子数：{result['sentence_count']}")
    out.append(f"槽位覆盖：{result['coverage']['filled']}/{result['coverage']['total']}")
    out.append("")

    for slot in SLOTS:
        items = result["slots"][slot]
        label = SLOT_LABEL[slot]
        if not items:
            mark = " [缺失]" if slot in result["missing_required"] else ""
            out.append(f"[{label}]{mark}  （空）")
            continue
        out.append(f"[{label}]  {len(items)} 条")
        for it in items:
            out.append(f"  · {it['text']}")
        out.append("")

    if result["conflicts"]:
        out.append("冲突：")
        for c in result["conflicts"]:
            out.append(f"  ! {c['reason']}")
            out.append(f"    A: {c['a']['text']}")
            out.append(f"    B: {c['b']['text']}")
        out.append("")

    if result["unclassified"]:
        out.append("未归类（可能只是上下文，也可能漏了约束）：")
        for s in result["unclassified"]:
            out.append(f"  - {s}")
        out.append("")

    if not result["conflicts"] and not result["missing_required"]:
        out.append("未发现槽位缺失或要求冲突。")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="promptshape",
        description="把一段提示词拆成可核查的结构（仅依赖标准库）",
        epilog=(
            "示例:\n"
            "  python promptshape.py --file prompt.txt\n"
            "  python promptshape.py --text '你是客服。只用一句话回答。输出 JSON。'\n"
            "  python promptshape.py --file prompt.txt --json\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="提示词文件路径")
    src.add_argument("--text", help="直接给出提示词文本")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            print(f"读不了文件：{e}", file=sys.stderr)
            return 2
    else:
        text = args.text

    if not text.strip():
        print("提示词是空的。", file=sys.stderr)
        return 2

    result = analyze(text)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(render(result))
    # 有冲突或缺失时退出码 1，方便在 CI 里用
    if result["conflicts"] or result["missing_required"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
