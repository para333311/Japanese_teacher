// 텔레그램 메시지 포맷팅.
// 말하기 연습이 목적이라 한글 발음을 가장 크게 강조한다.

/** 텔레그램 HTML 모드 이스케이프. 작은따옴표는 그대로 둔다(&#x27; 노출 방지). */
export function esc(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/**
 * 진도 표시.
 *
 * 블록문자(█░)와 색상 이모지(🟩⬜)를 차례로 써봤지만 사용자 안드로이드
 * 폰트에서 각각 백슬래시·회색 네모로 깨져 보였다. 그래서 막대 그래픽을
 * 버리고 어떤 폰트에서도 확실히 보이는 표현으로 바꾼다.
 */
export function progressBar(done, total, unit = "문장") {
  if (!total || total <= 0) return "";
  const pct = Math.round((done / total) * 100);
  return `${done}/${total}${unit} (${pct}%)`;
}

/**
 * 낱말 쪼개기 블록.
 *
 * '오카와리 쿠다사이'처럼 통째로 외우면 응용이 안 되므로
 * '오카와리(한 그릇 더) + 쿠다사이(주세요)'로 끊어서 보여준다.
 *
 * 표기 우선순위는 한글 발음이다. 일본어 글자는 못 읽어도 학습에 지장이
 * 없어야 하므로 굵게 쓰지 않고 괄호 안 보조 표기로만 덧붙인다.
 *
 *   · <b>코레</b>(これ) — 이거
 */
export function formatParts(parts) {
  if (!Array.isArray(parts) || parts.length === 0) return [];
  const L = ["🧩 <b>끊어서 보기</b>"];
  for (const x of parts) {
    const jp = x.jp ? `(${esc(x.jp)})` : "";
    L.push(`· <b>${esc(x.kr)}</b>${jp} — ${esc(x.ko)}`);
  }
  return L;
}

/**
 * 한 문장 학습 메시지.
 * 핵심 순서: 한글 발음(제일 위) → 뜻 → 낱말 쪼개기 → 상황 → 팁
 */
export function formatLesson(p, { showJapanese = false, progress = null } = {}) {
  const L = [];
  L.push("🇯🇵 <b>오늘의 한 문장</b>", "");
  L.push(`🗣 <b>${esc(p.kr)}</b>`, "");
  L.push(`💬 ${esc(p.ko)}`);
  if (p.scene) L.push(`📍 ${esc(p.scene)}`);

  const partLines = formatParts(p.parts);
  if (partLines.length) L.push("", ...partLines);

  if (p.tip) L.push("", `💡 ${esc(p.tip)}`);
  if (showJapanese) L.push("", `<i>${esc(p.jp)}</i>`);

  if (progress) {
    const { done, total, round } = progress;
    L.push("", `📈 ${progressBar(done, total)} · ${round}회차`);
  }
  return L.join("\n");
}

/**
 * 단어 학습 메시지.
 *
 * 두 가지 형태를 함께 다룬다.
 *   비교형 — 같은 한자라도 한국·일본에서 뜻이 달라지는 단어(会計, 人参 등).
 *            jpMeaning 이 있으면 이쪽으로 판단해 두 나라 뜻을 나란히 보여준다.
 *   일반형 — 공항·숙소·식당처럼 생활·여행에 바로 쓰는 어휘. 뜻 하나와
 *            상황(scene)을 보여준다.
 */
export function formatWord(w, { progress = null } = {}) {
  const isCompare = Boolean(w.jpMeaning);
  const L = [];
  L.push(isCompare ? "🈺 <b>한자 단어</b>" : "📖 <b>오늘의 단어</b>", "");
  L.push(`<b>${esc(w.kanji)}</b>`, "");
  L.push(`🗣 ${esc(w.koReading)} / ${esc(w.kr)}`, "");

  if (isCompare) {
    L.push(`🇰🇷 한국 — ${esc(w.koMeaning)}`);
    L.push(`🇯🇵 일본 — ${esc(w.jpMeaning)}`);
  } else {
    L.push(`💬 ${esc(w.meaning)}`);
    if (w.scene) L.push(`📍 ${esc(w.scene)}`);
  }

  if (progress) {
    const { done, total, round } = progress;
    L.push("", `📈 ${progressBar(done, total, "단어")} · ${round}회차`);
  }
  return L.join("\n");
}

export function formatHelp(intervalHours) {
  return [
    "🇯🇵 <b>생활 일본어 봇</b>",
    "",
    `${intervalHours}시간마다 일본어 한 문장을 보내드려요.`,
    "한글 발음 그대로 소리 내어 읽으면 됩니다.",
    "",
    "<b>명령어</b>",
    "/start — 봇 시작 &amp; 이 채팅에 등록",
    "/now — 지금 바로 한 문장 받기",
    "/again — 진도와 상관없이 아무 문장",
    "/stats — 학습 진도 보기",
    "/reset — 진도 처음부터 다시",
    "/stop — 정기 발송 중지",
    "/help — 도움말",
  ].join("\n");
}

export function formatStart(intervalHours) {
  return [
    "✅ <b>등록 완료!</b>",
    "",
    `이제 <b>${intervalHours}시간</b>마다 일본어 한 문장을 보내드릴게요.`,
    "밤에는 알림이 가지 않으니 안심하세요. 🌙",
    "",
    "지금 바로 받아보려면 /now 를 눌러보세요.",
  ].join("\n");
}

export function formatStats(phrase, word, intervalHours) {
  const pPct = phrase.total ? Math.round((phrase.done / phrase.total) * 100) : 0;
  const wPct = word.total ? Math.round((word.done / word.total) * 100) : 0;
  return [
    "📊 <b>학습 진도</b>",
    "",
    `🗣 문장: <b>${phrase.done}</b> / ${phrase.total} (${pPct}%) · ${phrase.round}회차`,
    `🈺 단어: <b>${word.done}</b> / ${word.total} (${wPct}%) · ${word.round}회차`,
    "",
    `발송 주기: ${intervalHours}시간마다`,
  ].join("\n");
}
