"""参考度审计：写稿到底“像”参考片多少。

    python similarity.py --work work/demo            # 自动找 script.md + reference.json/evidence.json
    python similarity.py --script work/demo/script.md --reference work/demo/reference.json --max 60

口径：
- 结构相似度（60% 权重）：镜头时长分布 + 镜头数，按归一化直方图算余弦
- 文案重合度（40% 权重）：字符 5-gram Jaccard，直接反映“有没有抄句子”
- 参考度 = 结构 × 0.6 + 文案 × 0.4，0–100
- 默认目标 40，硬上限 60；超过上限退出码 2

没有参考片时输出 no_reference，不做限制。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CJK = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")


def read_text(path: Path) -> str:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("beats"):
            return "".join(str(b.get("text", "")) for b in data["beats"])
        return json.dumps(data, ensure_ascii=False)
    return path.read_text(encoding="utf-8")


def clean(text: str) -> str:
    return "".join(CJK.findall(text)).lower()


def ngrams(text: str, n: int = 5) -> set[str]:
    t = clean(text)
    return {t[i:i + n] for i in range(max(0, len(t) - n + 1))}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def duration_hist(durs: list[float], bins: int = 8) -> list[float]:
    if not durs:
        return []
    total = sum(durs) or 1.0
    norm = [d / total for d in durs]
    hist = [0.0] * bins
    for v in norm:
        idx = min(bins - 1, int(v * bins))
        hist[idx] += 1
    n = sum(hist) or 1.0
    return [h / n for h in hist]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def load_reference(work: Path, explicit: str | None) -> tuple[list[float], str]:
    cand = [Path(explicit)] if explicit else [
        work / "reference.json", work / "evidence.json",
    ]
    for p in cand:
        if p and p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            shots = data.get("shots") or data.get("beats") or []
            durs = []
            for s in shots:
                d = s.get("duration_sec") or s.get("dur")
                if d is None and s.get("start") is not None and s.get("end") is not None:
                    d = float(s["end"]) - float(s["start"])
                if d:
                    durs.append(float(d))
            text = ""
            tr = data.get("transcript") or {}
            if isinstance(tr, dict):
                text = " ".join(str(s.get("text", "")) for s in (tr.get("segments") or []))
                text = text or str(tr.get("text") or "")
            return durs, text
    return [], ""


def main() -> int:
    ap = argparse.ArgumentParser(description="参考度审计")
    ap.add_argument("--work", default="")
    ap.add_argument("--script", default="")
    ap.add_argument("--reference", default=None)
    ap.add_argument("--target", type=float, default=40)
    ap.add_argument("--max", type=float, default=60)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    work = Path(a.work) if a.work else Path(a.script).parent
    script_path = Path(a.script) if a.script else None
    if script_path is None:
        for name in ("script.md", "script.json"):
            if (work / name).exists():
                script_path = work / name
                break
    if not script_path or not script_path.exists():
        raise SystemExit("[audit] 找不到 script.md / script.json")

    script_text = read_text(script_path)
    ref_durs, ref_text = load_reference(work, a.reference)

    script_durs: list[float] = []
    sj = work / "script.json"
    if sj.exists():
        try:
            data = json.loads(sj.read_text(encoding="utf-8"))
            script_durs = [float(b.get("duration_sec") or 0) for b in data.get("beats") or []]
        except Exception:
            script_durs = []

    phrase = jaccard(ngrams(script_text), ngrams(ref_text)) if ref_text else 0.0
    structure = cosine(duration_hist(ref_durs), duration_hist(script_durs)) if ref_durs and script_durs else None
    if structure is None and not ref_text:
        out = {"ok": True, "no_reference": True, "score": 0}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    structure_pct = round((structure or 0) * 100, 1)
    phrase_pct = round(phrase * 100, 1)
    # 文案重合度按“越低越好”折算成相似度贡献：重合 0% = 0 分，重合 ≥25% 直接顶格
    phrase_score = min(100.0, phrase_pct / 25 * 100)
    if structure is None:
        score = phrase_score
    else:
        score = structure_pct * 0.6 + phrase_score * 0.4
    score = round(min(100.0, score), 1)

    verdict = "pass"
    if score > a.max:
        verdict = "fail"
    elif score > a.target:
        verdict = "warn"

    out = {
        "ok": verdict != "fail",
        "score": score,
        "verdict": verdict,
        "target": a.target,
        "max": a.max,
        "structure_similarity": structure_pct,
        "phrase_overlap": phrase_pct,
        "phrase_score": round(phrase_score, 1),
        "script": str(script_path),
        "reference_shots": len(ref_durs),
        "script_beats": len(script_durs),
        "hint": (
            "超过上限：重写结构和句式，不要只换词"
            if verdict == "fail" else
            ("接近上限：至少换掉两个镜头的组织方式" if verdict == "warn" else "")
        ),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 2 if verdict == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
