#!/usr/bin/env python3
"""data/phrases.json → src/phrases.js 변환."""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
src = json.loads((BASE / "data/phrases.json").read_text(encoding="utf-8"))
phrases = src["phrases"]

def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')

out = [
    "// 생활 일본어 문장 데이터 (자동 생성: data/phrases.json → 이 파일)",
    "// 수정은 data/phrases.json 을 고친 뒤 `npm run build:phrases` 로 재생성하세요.",
    "",
    "export const PHRASES = [",
]
for p in phrases:
    out += [
        "  {",
        f'    jp: "{esc(p["jp"])}",',
        f'    kr: "{esc(p["kr_read"])}",',
        f'    ko: "{esc(p["ko"])}",',
        f'    scene: "{esc(p["scene"])}",',
        f'    tip: "{esc(p["tip"])}",',
        f'    level: {p["level"]},',
        "  },",
    ]
out += ["];", "", "export const TOTAL = PHRASES.length;", ""]

(BASE / "src/phrases.js").write_text("\n".join(out), encoding="utf-8")
print(f"src/phrases.js 생성 완료: {len(phrases)}문장")
