import os
import time
import logging
from datetime import datetime, timedelta, timezone, time as dtime

import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

# ── Настройки из переменных окружения ─────────────────────────────
TELEGRAM_TOKEN  = os.environ["TELEGRAM_TOKEN"]      # токен от BotFather
CHAT_ID         = os.environ["CHAT_ID"]             # ваш chat_id (для ежедневной рассылки)
FINNHUB_KEY     = os.environ["FINNHUB_KEY"]         # ключ Finnhub
ANTHROPIC_KEY   = os.environ.get("ANTHROPIC_API_KEY")  # ключ Claude API (для выжимки)
TICKER          = "OUST"

# Время ежедневной отправки (UTC). 21:00 UTC ≈ после закрытия рынка США.
DAILY_HOUR_UTC = 21
DAILY_MIN_UTC  = 0


# ── Получение данных ──────────────────────────────────────────────
def get_json(url, params, retries=3):
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            last_err = e
            time.sleep(3 * (attempt + 1))
    raise last_err


def get_quote():
    d = get_json("https://finnhub.io/api/v1/quote",
                 {"symbol": TICKER, "token": FINNHUB_KEY})
    return {"price": d["c"], "change": d["d"], "percent": d["dp"],
            "high": d["h"], "low": d["l"], "prev_close": d["pc"]}


def get_news(max_items=6):
    today = datetime.now(timezone.utc).date()
    frm = (today - timedelta(days=2)).isoformat()
    items = get_json("https://finnhub.io/api/v1/company-news",
                     {"symbol": TICKER, "from": frm,
                      "to": today.isoformat(), "token": FINNHUB_KEY})
    return [{"headline": n["headline"], "url": n["url"],
             "source": n["source"], "summary": n.get("summary", "")}
            for n in items[:max_items]]


def summarize(quote, news):
    """Короткая связная выжимка через Claude API. Если ключа/ошибки нет — вернёт None."""
    if not ANTHROPIC_KEY or not news:
        return None

    headlines = "\n".join(
        f"- {n['headline']}" + (f" — {n['summary']}" if n['summary'] else "")
        for n in news
    )
    prompt = (
        f"Акция OUST (Ouster) сегодня: цена ${quote['price']:.2f}, "
        f"изменение {quote['percent']:+.2f}%.\n\n"
        f"Заголовки новостей за последние дни:\n{headlines}\n\n"
        "Напиши на русском 2–3 предложения: что главное происходит с компанией "
        "и чем вероятно объясняется движение цены. Только суть, без вступлений."
    )

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5",
                "max_tokens": 400,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=40,
        )
        r.raise_for_status()
        data = r.json()
        parts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
        text = "".join(parts).strip()
        return text or None
    except Exception as e:
        logging.warning("Не удалось получить выжимку: %s", e)
        return None


def build_message():
    quote = get_quote()
    news = get_news()
    digest = summarize(quote, news)

    arrow = "🟢▲" if quote["change"] >= 0 else "🔴▼"
    date_str = datetime.now().strftime("%d.%m.%Y")

    lines = [
        f"📊 <b>OUST · Ouster, Inc.</b> — {date_str}",
        "",
        f"💵 Цена: <b>${quote['price']:.2f}</b>  {arrow} {quote['change']:+.2f} ({quote['percent']:+.2f}%)",
        f"📈 День: ${quote['low']:.2f} – ${quote['high']:.2f}  ·  Пред. закрытие: ${quote['prev_close']:.2f}",
        "",
    ]

    if digest:
        lines.append(f"🧭 <b>Кратко:</b> {digest}")
        lines.append("")

    if news:
        lines.append("📰 <b>Источники:</b>")
        for n in news[:4]:
            lines.append(f"• <a href=\"{n['url']}\">{n['headline']}</a> ({n['source']})")
    else:
        lines.append("📰 Свежих новостей не найдено.")

    lines.append("")
    lines.append("<i>Не является инвестиционной рекомендацией.</i>")
    return "\n".join(lines)


# ── Обработчики ───────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Собираю данные по OUST…")
    try:
        msg = build_message()
    except Exception as e:
        msg = f"⚠️ Не удалось получить данные: {e}"
    await update.message.reply_text(
        msg, parse_mode="HTML", disable_web_page_preview=True
    )


async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = build_message()
    except Exception as e:
        msg = f"⚠️ Ошибка при сборке ежедневного отчёта: {e}"
    await context.bot.send_message(
        chat_id=CHAT_ID, text=msg,
        parse_mode="HTML", disable_web_page_preview=True
    )


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.job_queue.run_daily(
        daily_job,
        time=dtime(hour=DAILY_HOUR_UTC, minute=DAILY_MIN_UTC, tzinfo=timezone.utc),
    )
    logging.info("Бот запущен, слушает команды.")
    app.run_polling()


if __name__ == "__main__":
    main()