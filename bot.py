import os
import requests
from datetime import datetime, timedelta

# ── Настройки из переменных окружения ─────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]      # токен от BotFather
CHAT_ID        = os.environ["CHAT_ID"]             # ваш chat_id
FINNHUB_KEY    = os.environ["FINNHUB_KEY"]         # ключ Finnhub
TICKER         = "OUST"                            # тикер Ouster, Inc.


def get_quote():
    """Текущая цена и дневное изменение."""
    url = "https://finnhub.io/api/v1/quote"
    r = requests.get(url, params={"symbol": TICKER, "token": FINNHUB_KEY}, timeout=15)
    r.raise_for_status()
    d = r.json()
    return {
        "price": d["c"],          # текущая цена
        "change": d["d"],         # изменение в $
        "percent": d["dp"],       # изменение в %
        "high": d["h"],
        "low": d["l"],
        "prev_close": d["pc"],
    }


def get_news(max_items=4):
    """Новости по компании за последние 2 дня."""
    today = datetime.utcnow().date()
    frm = (today - timedelta(days=2)).isoformat()
    url = "https://finnhub.io/api/v1/company-news"
    r = requests.get(url, params={
        "symbol": TICKER, "from": frm, "to": today.isoformat(),
        "token": FINNHUB_KEY
    }, timeout=15)
    r.raise_for_status()
    items = r.json()[:max_items]
    return [{"headline": n["headline"], "url": n["url"], "source": n["source"]}
            for n in items]


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

    # Простая аналитика "почему" — по движению цены
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


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, data={
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }, timeout=15)
    r.raise_for_status()


if __name__ == "__main__":
    try:
        msg = build_message()
        send_telegram(msg)
        print("Уведомление отправлено.")
    except Exception as e:
        # Ошибку тоже шлём себе, чтобы знать что что-то сломалось
        try:
            send_telegram(f"⚠️ Ошибка бота: {e}")
        except Exception:
            pass
        print("Ошибка:", e)
        raise
