#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""오늘 나간 일본어 문장(또는 단어)이 실제로 들리는 유튜브 클립을 찾아 보낸다.

집 PC 의 예약작업(매일 12:05 KST, scripts/clip_task.ps1)으로 돈다.
GitHub Actions 는 쓰지 않는다 — 유튜브가 러너 IP 를 봇으로 막아 자막·영상을
한 건도 못 받는다(스페인어 봇에서 2026-09-02 확인). 집 IP 는 잘 된다.

흐름:
  1. 워커의 /today 로 오늘 카드를 받는다 (12:00 발송이 아직이면 잠시 기다린다)
  2. 유튜브에서 그 말을 검색해 후보 영상의 일본어 자막만 내려받는다
  3. 자막에서 그 말이 나오는 시각을 찾는다
  4. 그 부분만 잘라 받아 워커 POST /clip 으로 넘긴다 — 봇 토큰은 워커만
     갖고 있으니 텔레그램 전송은 워커가 한다. 여기엔 ADMIN_KEY 만 있으면 된다.

일본어라서 스페인어판(Espanol_teacher)과 다른 곳 — 그대로 복사하면 안 되는 곳:
  · 정규화는 NFKC. 반각 가나·전각 영숫자를 한 모양으로 모은다. 악센트 제거
    (NFD + Mn 제거)는 일본어에서 濁点/半濁点까지 떼어 が→か 가 되므로 쓰면 안 된다.
  · 일본어에는 띄어쓰기가 없다. 스페인어판의 " 낱말 " 경계 대조 대신 공백·문장부호를
    통째로 지운 문자열끼리 부분 문자열로 대조한다. 자막에 후리가나가 붙어도
    (前回(ぜんかい) → 前回ぜんかい) 부분 문자열이면 걸린다.
  · 자막 언어는 ja. 'ja.*' 글롭은 ja-en·ja-ar 같은 자동 번역본까지 끌어와
    요청이 몇 배로 늘고 429(Too Many Requests)를 부른다 — 딱 'ja' 만 받는다.
  · 영상 언어(%(language)s)를 함께 읽어 일본어 영상이 아니면 건너뛴다.
    유튜브는 영어 영상에도 기계번역 일본어 자막을 달아 주는데, 그 자막은
    실제로 들리는 소리와 아무 상관이 없다.
  · '두 낱말 이상' 같은 공백 기준 판정은 뜻이 없다. 정규화 후 글자 수로 자른다.
  · 카드 필드가 다르다. 문장=jp/kr/ko/parts[].jp, 단어=kanji/jp/kr/koReading.

전체 문장이 자막에 그대로 나오는 영상은 드물다. 그래서 문장 → parts 의
긴 조각 순서로 눈높이를 낮춰가며 찾는다. 그래도 없으면 못 찾았다고 한 줄만
알린다 — TTS 로 되돌아가지 않는다(mp3 는 그만 보내기로 했다).

ADMIN_KEY 는 환경변수 또는 저장소의 .dev.vars(ADMIN_KEY=...) 에서 읽는다.
워커 주소는 환경변수 WORKER_URL 로 덮어쓸 수 있다.
"""

import datetime
import glob
import html
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

WORKER = os.environ.get(
    "WORKER_URL", "https://japanese-teacher-bot.imissyou55aa.workers.dev"
).rstrip("/")
SEARCH_CANDIDATES = 8    # 검색 결과에서 자막을 확인할 영상 수 (많으면 429)
SUB_DELAY = 2.0          # 자막 요청 사이 쉬는 시간(초). 유튜브 429 완화
MAX_VIDEO_MINUTES = 90   # 이보다 긴 영상은 건너뛴다 (생방송·통합본 배제)
PAD_BEFORE = 1.5         # 대사 앞 여유(초)
PAD_AFTER = 2.0          # 대사 뒤 여유(초)
MIN_CLIP = 4.0           # 클립 최소 길이(초)
MAX_CLIP = 20.0          # 클립 최대 길이(초)
MIN_TERM_CHARS = 4       # 문장 조각은 정규화 후 이만큼은 돼야 찾는다
MIN_WORD_CHARS = 2       # 단어 카드 표제어는 이만큼은 돼야 찾는다
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKDIR = os.path.join(REPO, "state", "clip_work")
WAIT_FOR_CARD_MIN = 20   # 12:00 카드가 아직 안 나갔으면 이만큼 기다린다(분)
KST = datetime.timezone(datetime.timedelta(hours=9))


def log(*a):
    print(*a, flush=True)


def admin_key():
    key = os.environ.get("ADMIN_KEY", "").strip()
    if key:
        return key
    try:
        for line in open(os.path.join(REPO, ".dev.vars"), encoding="utf-8"):
            if line.startswith("ADMIN_KEY="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    raise SystemExit("ADMIN_KEY 가 없습니다 (환경변수 또는 .dev.vars)")


def api(path, data=None, files=None):
    """워커 관리 엔드포인트 호출. files 는 {필드: (파일명, bytes)} → multipart POST."""
    sep = "&" if "?" in path else "?"
    url = "%s%s%skey=%s" % (WORKER, path, sep, urllib.parse.quote(admin_key()))
    # Cloudflare 가 Python-urllib 기본 UA 를 봇 서명으로 막는다(403, error 1010)
    headers = {"User-Agent": "japanese-clip-bot/1.0"}
    body = None
    if files or data:
        boundary = "----clipbound7259"
        parts = []
        for k, v in (data or {}).items():
            parts.append(
                ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n"
                 % (boundary, k)).encode() + str(v).encode("utf-8") + b"\r\n"
            )
        for k, (fname, blob) in (files or {}).items():
            parts.append(
                ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; "
                 "filename=\"%s\"\r\nContent-Type: video/mp4\r\n\r\n"
                 % (boundary, k, fname)).encode() + blob + b"\r\n"
            )
        parts.append(("--%s--\r\n" % boundary).encode())
        body = b"".join(parts)
        headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


# ------------------------------------------------------------------ 문자 정규화

# 남길 글자: 히라가나·가타카나(장음 ー 포함)·한자(々 반복부호 포함)·숫자·영문.
# 그 밖(공백, 。、!?「」・…, 후리가나 괄호 등)은 전부 지운다. 지운 뒤에는
# 공백이 하나도 없는 문자열이 되므로 부분 문자열로 곧장 대조할 수 있다.
DROP = re.compile(
    "[^0-9a-z"
    "々"              # 々 반복부호
    "぀-ゟ"       # 히라가나
    "゠-ヿ"       # 가타카나 (장음 ー U+30FC 포함)
    "㐀-䶿"       # 한자 확장 A
    "一-鿿"       # 한자
    "]+"
)


# 후리가나: 한자 뒤 괄호 안에 읽기를 가나로 적어 주는 관습.
# 「電話（でんわ）で居酒屋の予約（よやく）を」처럼 자막에 흔하다. 안 지우면
# 문장 전체 대조가 이것 때문에 어긋난다(실측). 괄호 속이 전부 가나일 때만 지운다.
FURIGANA = re.compile("[(\\[【〔]\\s*[぀-ゟ゠-ヿ]+\\s*[)\\]】〕]")


def norm(s):
    """자막 대조용 정규화: NFKC → 소문자 → 후리가나 제거 → 가나·한자·영숫자만 남김.

    NFKC 로 반각 가나(ｱ)·전각 영숫자(Ａ)·전각 괄호(（)를 한 모양으로 모은다.
    스페인어판처럼 NFD 로 결합문자를 떼면 안 된다 — 濁点이 분리돼
    が 가 か 로 바뀌어 버린다(다른 소리다).
    """
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = FURIGANA.sub("", s)
    return DROP.sub("", s)


def query_text(term):
    """유튜브 검색어. 문장부호만 털고 원문 그대로 넣는다(정규화하면 안 읽힌다)."""
    s = unicodedata.normalize("NFKC", term or "")
    s = re.sub(r"[。、！？!?…「」『』（）()\"']+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def search_terms(kind, content):
    """찾을 말을 눈높이 순서로.

    단어 카드: 표기(kanji) → 읽기(jp). 자막이 한자로 쓰면 표기가, 가나로 쓰면
      읽기가 걸린다. 한 글자짜리 표기(袋)는 手袋 같은 딴 낱말에 얹혀 걸리므로
      제외하고 읽기(ふくろ)로 찾는다.
    문장 카드: 문장 전체 → parts 의 일본어 조각 중 긴 것 순. 일본어는 띄어쓰기가
      없으니 '두 낱말 이상' 대신 글자 수로 자른다. 너무 짧은 조각(は, の)은
      아무 영상에나 있어서 뜻이 없다.
    """
    terms = []
    seen = set()

    def add(v, floor):
        v = (v or "").strip()
        n = norm(v)
        if not v or len(n) < floor or n in seen:
            return
        seen.add(n)
        terms.append(v)

    if kind == "word":
        add(content.get("kanji"), MIN_WORD_CHARS)
        add(content.get("jp"), MIN_WORD_CHARS)
        if not terms:  # 한 글자 표기뿐이면 그거라도 쓴다
            add(content.get("kanji"), 1)
        return terms

    add(content.get("jp"), 1)
    frags = sorted(
        (p.get("jp", "") for p in content.get("parts", [])),
        key=lambda x: -len(norm(x)),
    )
    for p in frags:
        add(p, MIN_TERM_CHARS)
    return terms


def card_label(kind, content):
    """(찾을 대상 표기, 텔레그램 캡션)."""
    if kind == "word":
        head = content.get("kanji") or content.get("jp") or ""
        reading = content.get("jp") or ""
        kr = content.get("kr") or ""
        mean = (
            content.get("meaning")
            or content.get("jpMeaning")
            or content.get("koReading")
            or ""
        )
        title = "%s (%s)" % (head, reading) if reading and reading != head else head
        return head, "🎬 %s\n🗣 %s\n%s" % (title, kr, mean)
    jp = content.get("jp") or ""
    return jp, "🎬 %s\n🗣 %s\n%s" % (jp, content.get("kr") or "", content.get("ko") or "")


# ------------------------------------------------------------------ 자막 검색

def run(cmd, timeout=180):
    return subprocess.run(cmd, capture_output=True, timeout=timeout)


def yt_search(query, n):
    """유튜브 검색 → [{id, duration, title}] (긴 영상 제외)."""
    r = run([
        "yt-dlp", "--flat-playlist", "--dump-json",
        "ytsearch%d:%s" % (n, query),
    ])
    if r.returncode != 0:
        log("  검색 실패:", r.stderr.decode("utf-8", "replace")[-400:])
    out = []
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        try:
            j = json.loads(line)
        except ValueError:
            continue
        dur = j.get("duration") or 0
        if dur and dur > MAX_VIDEO_MINUTES * 60:
            continue
        if j.get("id"):
            out.append({"id": j["id"], "duration": dur, "title": j.get("title", "")})
    return out


def fetch_subs(video_id):
    """일본어 자막(vtt)을 내려받아 (경로, 영상언어)를 돌려준다. 없으면 (None, lang).

    --sub-langs 는 'ja' 하나만 준다. 'ja.*' 는 ja-en·ja-ar 같은 자동 번역본까지
    받아 오느라 요청이 몇 배로 늘고 곧장 429 를 맞는다(실측).
    --print 는 기본이 --simulate 라 자막이 안 써진다. --no-simulate 를 같이 준다.
    """
    for f in glob.glob(os.path.join(WORKDIR, video_id + "*.vtt")):
        os.remove(f)
    r = run([
        "yt-dlp", "--skip-download", "--no-simulate",
        "--write-subs", "--write-auto-subs",
        "--sub-langs", "ja",
        "--sub-format", "vtt",
        "--print", "LANG=%(language)s",
        "-o", os.path.join(WORKDIR, "%(id)s"),
        "https://www.youtube.com/watch?v=" + video_id,
    ], timeout=120)
    lang = ""
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith("LANG="):
            lang = line[5:].strip()
    hits = glob.glob(os.path.join(WORKDIR, video_id + "*.vtt"))
    if not hits:
        err = r.stderr.decode("utf-8", "replace").strip().splitlines()
        log("  자막 없음: %s %s" % (video_id, err[-1][-200:] if err else ""))
    return (hits[0] if hits else None), lang


def is_japanese_video(lang):
    """일본어 영상인가. 'NA'(모름)는 통과시킨다 — 자막 대조가 한 번 더 거른다.

    유튜브는 영어 영상에도 기계번역 일본어 자막을 붙여 준다. 그 자막의 글자는
    실제로 들리는 소리와 무관하므로, 언어를 알 수 있으면 일본어가 아닌 영상은
    자막을 보기 전에 버린다.
    """
    l = (lang or "").strip().lower()
    if not l or l in ("na", "none", "null"):
        return True
    return l.split("-")[0] == "ja"


TS = re.compile(r"(\d+):(\d\d):(\d\d)\.(\d\d\d)\s*-->\s*(\d+):(\d\d):(\d\d)\.(\d\d\d)")


def parse_vtt(path):
    """[(start초, end초, 정규화 텍스트)] 목록.

    타임스탬프 줄 뒤에 붙는 배치 설정(align:start position:0%)은 텍스트가 아니다.
    줄 단위로 잘라 타임스탬프 줄 자체를 통째로 버린다.
    """
    cues = []
    try:
        raw = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return cues
    for block in re.split(r"\r?\n\s*\r?\n", raw):
        lines = block.strip().splitlines()
        m = None
        idx = 0
        for k, line in enumerate(lines):
            m = TS.search(line)
            if m:
                idx = k
                break
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000.0
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000.0
        text = " ".join(lines[idx + 1:])
        text = html.unescape(re.sub(r"<[^>]+>", "", text))
        text = norm(text)
        if text:
            cues.append((start, end, text))
    return cues


def find_in_cues(cues, needle):
    """이웃 큐 두세 개를 이어붙여도 찾는다 — 대사가 줄로 쪼개져 있는 게 보통이다.

    일본어에는 낱말 경계가 없으니 스페인어판처럼 앞뒤에 공백을 붙여 대조할 수
    없다. 공백을 다 지운 문자열끼리 부분 문자열로 본다. 큐를 이을 때도 사이에
    아무것도 넣지 않는다 — 실제로 한 낱말이 두 큐에 걸쳐 잘리기 때문이다.

    묶음 크기를 1 → 2 → 3 순으로 넓혀 가며 본다. 스페인어판처럼 시작 큐를
    바깥 고리로 두면 한 큐에 다 들어 있는 말도 두세 큐 앞에서 걸려 시작
    시각이 몇 초씩 앞으로 밀린다(실측: 居酒屋 5.4초 → 2.0초 로 보고됨).
    작은 묶음을 먼저 보면 그 말이 실제로 나오는 큐가 잡힌다.
    """
    if not needle:
        return None
    for span in (1, 2, 3):
        for i in range(len(cues) - span + 1):
            joined = "".join(c[2] for c in cues[i:i + span])
            if needle in joined:
                return cues[i][0], cues[i + span - 1][1]
    return None


# ------------------------------------------------------------------ 클립 추출

def cut_clip(video_id, start, end, out_path):
    a = max(0.0, start - PAD_BEFORE)
    b = end + PAD_AFTER
    if b - a < MIN_CLIP:
        b = a + MIN_CLIP
    if b - a > MAX_CLIP:
        b = a + MAX_CLIP
    r = run([
        "yt-dlp",
        "-f", "bv*[height<=720]+ba/b[height<=720]/b",
        "--download-sections", "*%.1f-%.1f" % (a, b),
        "--force-keyframes-at-cuts",
        "--merge-output-format", "mp4",
        "-o", out_path,
        "https://www.youtube.com/watch?v=" + video_id,
    ], timeout=300)
    if not os.path.exists(out_path):
        log("  다운로드 실패:", r.stderr.decode("utf-8", "replace")[-300:])
        return False
    return os.path.getsize(out_path) > 10_000


# ------------------------------------------------------------------ 찾기

def find_clip(kind, content):
    """(video_id, start, end, term) 또는 None."""
    terms = search_terms(kind, content)
    log("찾을 말:", terms)
    checked = set()
    for term in terms:
        needle = norm(term)
        # 그 말이 그대로 들리는 영상을 노린다. 검색어에 따옴표를 붙여 정확
        # 매치를 우선시키되, 유튜브가 무시해도 자막 확인이 걸러 준다.
        for video in yt_search('"%s"' % query_text(term), SEARCH_CANDIDATES):
            vid = video["id"]
            if vid in checked:
                continue
            checked.add(vid)
            sub, lang = fetch_subs(vid)
            time.sleep(SUB_DELAY)
            if not sub:
                continue
            if not is_japanese_video(lang):
                log("  일본어 영상이 아님(%s): %s" % (lang, vid))
                continue
            hit = find_in_cues(parse_vtt(sub), needle)
            if hit:
                log("일치: %s (%s) %.1f~%.1f초 [%s]"
                    % (vid, video["title"][:40], hit[0], hit[1], term))
                return (vid, hit[0], hit[1], term)
    return None


# ------------------------------------------------------------------ 메인

def wait_for_today_card():
    """오늘(KST) 12:00 카드가 나갔는지 /today 로 확인. 아직이면 잠시 기다린다.

    워커 cron 이 몇 분 늦을 수 있고, 예약작업이 정각보다 먼저 뜰 수도 있다.
    """
    today_kst = datetime.datetime.now(KST).date()
    deadline = time.time() + WAIT_FOR_CARD_MIN * 60
    while True:
        today = api("/today")
        sent = today.get("sent_at") if today.get("ok") else None
        if sent:
            # D1 의 datetime('now') 는 UTC
            d = datetime.datetime.strptime(sent, "%Y-%m-%d %H:%M:%S")
            d = d.replace(tzinfo=datetime.timezone.utc).astimezone(KST).date()
            if d == today_kst or os.environ.get("FORCE_CLIP"):
                return today
        if time.time() > deadline:
            log("오늘 카드가 아직 안 나갔습니다 (마지막 발송: %s). 포기." % sent)
            return None
        log("오늘 카드를 기다리는 중 (마지막 발송: %s)" % sent)
        time.sleep(60)


def main():
    os.makedirs(WORKDIR, exist_ok=True)

    today = wait_for_today_card()
    if not today:
        return 1
    if today.get("clip_at") and not os.environ.get("FORCE_CLIP"):
        # 예약작업이 재시도로 여러 번 떠도 한 번만 보낸다
        log("오늘 클립은 이미 보냈습니다:", today["clip_at"])
        return 0

    kind = today.get("kind") or "phrase"
    content = today["content"]
    head, caption = card_label(kind, content)
    log("오늘의 %s:" % ("단어" if kind == "word" else "문장"), head)
    if not head:
        log("내용이 비어 있어 종료")
        return 0

    found = find_clip(kind, content)
    if not found:
        log("자막에서 찾지 못했습니다. 오늘은 영상 없이 넘어갑니다.")
        # 개인 채널이므로 실패도 짧게 알린다 — 조용히 사라지면 영상이 왜
        # 안 왔는지 알 수 없다.
        try:
            r = api("/clip", {"text": "🎬 오늘 말이 나오는 클립을 못 찾았습니다: %s" % head})
            log("알림:", r)
        except Exception as e:
            log("실패 알림 전송 실패:", e)
        return 0

    vid, start, end, term = found
    out = os.path.join(WORKDIR, "clip.mp4")
    if os.path.exists(out):
        os.remove(out)
    if not cut_clip(vid, start, end, out):
        log("클립 추출 실패")
        return 1

    size = os.path.getsize(out)
    log("클립 %.1fKB" % (size / 1024))
    if size > 49_000_000:
        log("50MB 초과라 전송 불가")
        return 1

    blob = open(out, "rb").read()
    try:
        r = api("/clip", {"caption": caption}, files={"video": ("clip.mp4", blob)})
        log("전송:", r)
        return 0 if r.get("ok") else 1
    except Exception as e:
        log("전송 실패:", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
