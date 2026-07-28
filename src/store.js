// D1 저장소 계층 — 구독자와 학습 진도를 보관한다.

import { PHRASES, TOTAL } from "./phrases.js";

/** 구독자 등록. 이미 있으면 다시 활성화만 한다. @returns {boolean} 신규 여부 */
export async function addSubscriber(db, chatId) {
  const row = await db
    .prepare("SELECT chat_id, active FROM subscribers WHERE chat_id = ?")
    .bind(String(chatId))
    .first();

  if (row) {
    if (row.active === 1) return false;
    await db
      .prepare("UPDATE subscribers SET active = 1 WHERE chat_id = ?")
      .bind(String(chatId))
      .run();
    return true;
  }

  await db
    .prepare(
      "INSERT INTO subscribers (chat_id, active, created_at) VALUES (?, 1, datetime('now'))",
    )
    .bind(String(chatId))
    .run();
  return true;
}

export async function removeSubscriber(db, chatId) {
  await db
    .prepare("UPDATE subscribers SET active = 0 WHERE chat_id = ?")
    .bind(String(chatId))
    .run();
}

export async function listSubscribers(db) {
  const { results } = await db
    .prepare("SELECT chat_id FROM subscribers WHERE active = 1")
    .all();
  return (results ?? []).map((r) => r.chat_id);
}

/** 이번 회차에서 이미 낸 문장 index 집합과 회차 번호를 읽는다. */
export async function getProgress(db) {
  const row = await db
    .prepare("SELECT round, seen FROM progress WHERE id = 1")
    .first();

  if (!row) {
    await db
      .prepare("INSERT INTO progress (id, round, seen) VALUES (1, 1, '[]')")
      .run();
    return { round: 1, seen: new Set() };
  }

  let seen = [];
  try {
    seen = JSON.parse(row.seen || "[]");
  } catch {
    seen = [];
  }
  // 문장 목록이 줄어든 경우를 대비해 유효 범위만 남긴다
  const valid = seen.filter((i) => Number.isInteger(i) && i >= 0 && i < TOTAL);
  return { round: row.round || 1, seen: new Set(valid) };
}

async function saveProgress(db, round, seenSet) {
  await db
    .prepare("UPDATE progress SET round = ?, seen = ? WHERE id = 1")
    .bind(round, JSON.stringify([...seenSet]))
    .run();
}

/**
 * 중복 없이 다음 문장을 고른다.
 * 한 바퀴 다 돌면 초기화하고 회차를 올린다.
 */
export async function pickNext(db) {
  let { round, seen } = await getProgress(db);

  let remaining = [];
  for (let i = 0; i < TOTAL; i++) if (!seen.has(i)) remaining.push(i);

  if (remaining.length === 0) {
    seen = new Set();
    round += 1;
    remaining = Array.from({ length: TOTAL }, (_, i) => i);
  }

  const idx = remaining[Math.floor(Math.random() * remaining.length)];
  seen.add(idx);
  await saveProgress(db, round, seen);

  return {
    phrase: PHRASES[idx],
    progress: { done: seen.size, total: TOTAL, round },
  };
}

/** 진도에 영향 주지 않는 무작위 1개 */
export function pickRandom() {
  return PHRASES[Math.floor(Math.random() * TOTAL)];
}

export async function resetProgress(db) {
  await db
    .prepare("UPDATE progress SET round = 1, seen = '[]' WHERE id = 1")
    .run();
}
