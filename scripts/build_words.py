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
    "// 한자 단어 데이터 (자동 생성: data/words.json → 이 파일)",
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
        f'    koMeaning: "{esc(w["ko_meaning"])}",',
        f'    jpMeaning: "{esc(w["jp_meaning"])}",',
        "  },",
    ]
out += ["];", "", "export const WORD_TOTAL = WORDS.length;", ""]

(BASE / "src/words.js").write_text("\n".join(out), encoding="utf-8")
print(f"src/words.js 생성 완료: {len(words)}단어")
