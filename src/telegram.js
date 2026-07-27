// 텔레그램 Bot API 래퍼 (Cloudflare Workers 용)

const API_ROOT = "https://api.telegram.org";

export class Telegram {
  constructor(token) {
    if (!token) throw new Error("봇 토큰이 없습니다.");
    this.token = token;
  }

  get base() {
    return `${API_ROOT}/bot${this.token}`;
  }

  async call(method, payload) {
    const res = await fetch(`${this.base}/${method}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload ?? {}),
    });
    const body = await res.json().catch(() => ({}));
    if (!body.ok) {
      const desc = body.description || `HTTP ${res.status}`;
      const err = new Error(`${method} 실패: ${desc}`);
      err.description = desc;
      err.code = res.status;
      throw err;
    }
    return body.result;
  }

  getMe() {
    return this.call("getMe");
  }

  sendMessage(chatId, text) {
    return this.call("sendMessage", {
      chat_id: chatId,
      text,
      parse_mode: "HTML",
      disable_web_page_preview: true,
    });
  }

  /** 음성은 multipart 로 보내야 해서 FormData 사용 */
  async sendVoice(chatId, mp3Bytes, caption = "") {
    const form = new FormData();
    form.append("chat_id", String(chatId));
    if (caption) {
      form.append("caption", caption);
      form.append("parse_mode", "HTML");
    }
    form.append(
      "voice",
      new Blob([mp3Bytes], { type: "audio/mpeg" }),
      "pron.mp3",
    );

    const res = await fetch(`${this.base}/sendVoice`, {
      method: "POST",
      body: form,
    });
    const body = await res.json().catch(() => ({}));
    if (!body.ok) {
      throw new Error(`sendVoice 실패: ${body.description || res.status}`);
    }
    return body.result;
  }

  setWebhook(url, secretToken) {
    return this.call("setWebhook", {
      url,
      secret_token: secretToken,
      allowed_updates: ["message"],
      drop_pending_updates: false,
    });
  }

  deleteWebhook() {
    return this.call("deleteWebhook", {});
  }

  getWebhookInfo() {
    return this.call("getWebhookInfo");
  }

  setMyCommands(commands) {
    return this.call("setMyCommands", { commands });
  }
}
