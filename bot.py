import os
import time
import logging
from datetime import datetime, timedelta, timezone, time as dtime

import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

# ── Настройки из переменных окружения ─────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]      # токен от BotFather
CHAT_ID        = os.environ["CHAT_ID"]             # ваш chat_id (для ежедневной рассылки)
FINNHUB_KEY    = os.environ["FINNHUB_KEY"]         # ключ Finnhub
TICKER         = "OUST"

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


def get_news(max_items=4):
    today = datetime.now(timezone.utc).date()
    frm = (today - timedelta(days=2)).isoformat()
    items = get_json("https://finnhub.io/api/v1/company-news",
                     {"symbol": TICKER, "from": frm,
                      "to": today.isoformat(), "token": FINNHUB_KEY})
    return [{"headline": n["headline"], "url": n["url"], "source": n["source"]}
            for n in items[:max_items]]


def build_message():
    q = get_quote()
    news = get_news()
    arrow = "🟢▲" if q["change"] >= 0 else "🔴▼"
    date_str = datetime.now().strftime("%d.%m.%Y")

    lines = [
        f"📊 <b>OUST · Ouster, Inc.</b> — {date_str}",
        "",
        f"💵 Цена: <b>${q['price']:.2f}</b>  {arrow} {q['change']:+.2f} ({q['percent']:+.2f}%)",
        f"📈 День: ${q['low']:.2f} – ${q['high']:.2f}  ·  Пред. закрытие: ${q['prev_close']:.2f}",
        "",
    ]
    if abs(q["percent"]) >= 5:
        lines.append("⚡ <b>Сильное движение сегодня</b> — смотрите новости ниже.")
    elif q["change"] >= 0:
        lines.append("Акция закрылась в плюсе.")
    else:
        lines.append("Акция закрылась в минусе.")
    lines.append("")

    if news:
        lines.append("📰 <b>Свежие новости:</b>")
        for n in news:
            lines.append(f"• <a href=\"{n['url']}\">{n['headline']}</a> ({n['source']})")
    else:
        lines.append("📰 Свежих новостей не найдено.")

    lines.append("")
    lines.append("<i>Не является инвестиционной рекомендацией.</i>")
    return "\n".join(lines)


# ── Обработчики ───────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Реакция на /start — сразу присылает свежий отчёт."""
    await update.message.reply_text("Собираю данные по OUST…")
    try:
        msg = build_message()
    except Exception as e:
        msg = f"⚠️ Не удалось получить данные: {e}"
    await update.message.reply_text(
        msg, parse_mode="HTML", disable_web_page_preview=True
    )


async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    """Ежедневная авторассылка в CHAT_ID."""
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

    # /start → мгновенный отчёт
    app.add_handler(CommandHandler("start", start))

    # ежедневная отправка по расписанию (интервал задаётся ЗДЕСЬ)
    app.job_queue.run_daily(
        daily_job,
        time=dtime(hour=DAILY_HOUR_UTC, minute=DAILY_MIN_UTC, tzinfo=timezone.utc),
    )

    logging.info("Бот запущен, слушает команды.")
    app.run_polling()


if __name__ == "__main__":
    main()