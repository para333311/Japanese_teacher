#!/usr/bin/env python3
"""data/words.json → src/words.js 변환."""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
src = json.loads((BASE / "data/words.json").read_text(encoding="utf-8"))
words = src["words"]


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


out = [
    "// 단어 데이터 (자동 생성: data/words.json → 이 파일)",
    "// 수정은 data/words.json 을 고친 뒤 `npm run build:words` 로 재생성하세요.",
    "",
    "export const WORDS = [",
]
for w in words:
    out += [
        "  {",
        f'    kanji: "{esc(w["kanji"])}",',
        f'    jp: "{esc(w["jp"])}",',
        f'    kr: "{esc(w["kr_read"])}",',
        f'    koReading: "{esc(w["ko_reading"])}",',
    ]
    # 비교형: 한국/일본 뜻이 다른 단어. 일반형: 그 외 생활·여행 어휘.
    if "jp_meaning" in w:
        out += [
            f'    koMeaning: "{esc(w["ko_meaning"])}",',
            f'    jpMeaning: "{esc(w["jp_meaning"])}",',
        ]
    else:
        out.append(f'    meaning: "{esc(w["meaning"])}",')
    if w.get("scene"):
        out.append(f'    scene: "{esc(w["scene"])}",')
    out.append("  },")
out += ["];", "", "export const WORD_TOTAL = WORDS.length;", ""]

(BASE / "src/words.js").write_text("\n".join(out), encoding="utf-8")
print(f"src/words.js 생성 완료: {len(words)}단어")
