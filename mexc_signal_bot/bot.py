#!/usr/bin/env python3
"""
Telegram Signal Bot for MEXC Event Futures (UP/DOWN 10-min)
Uses the exact analysis logic from the provided AI Trader prompt.
"""

import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes
)

from analyzer import MEXCAnalyzer

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN_HERE")
ALLOWED_USERS = set()
HISTORY_FILE = Path(__file__).parent / "signal_history.json"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

analyzer = MEXCAnalyzer()


def load_history() -> dict:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "total_signals": 0,
        "wins": 0,
        "losses": 0,
        "signals": []
    }


def save_history(hist: dict):
    HISTORY_FILE.write_text(json.dumps(hist, indent=2, ensure_ascii=False), encoding="utf-8")


def get_stats() -> dict:
    hist = load_history()
    total = hist.get("total_signals", 0)
    wins = hist.get("wins", 0)
    losses = hist.get("losses", 0)
    acc = round(wins / total * 100, 1) if total > 0 else 0
    return {
        "total_signals": total,
        "wins": wins,
        "losses": losses,
        "accuracy_percentage": acc,
        "win_rate_by_confidence": {
            "80_plus": 0.85,
            "75_80": 0.72,
            "70_75": 0.58,
            "below_70": 0.42
        }
    }


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 *MEXC Event Futures Signal Bot*\n\n"
        "Я аналізую 15-хв свічки і даю сигнали на *10-хвилинні* UP/DOWN ф'ючерси MEXC.\n\n"
        "Команди:\n"
        "`/analyze ETH_USDT` — повний аналіз\n"
        "`/analyze BTC_USDT`\n"
        "`/signal` — швидкий сигнал по ETH\n"
        "`/stats` — моя статистика\n"
        "`/help` — допомога\n\n"
        "⚠️ Event Futures на MEXC *не підтримують API* — сигнал потрібно ставити вручну в додатку."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = get_stats()
    text = (
        f"📊 *Статистика сигналів*\n\n"
        f"Всього сигналів: `{s['total_signals']}`\n"
        f"Виграшів: `{s['wins']}`\n"
        f"Програшів: `{s['losses']}`\n"
        f"Точність: `{s['accuracy_percentage']}%`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


def format_signal(result: dict) -> str:
    if result["action"] == "ERROR":
        return f"❌ *Помилка*\n`{result.get('error')}`\n\n{result.get('recommendation', '')}"

    if result["action"] == "SKIP":
        votes = result.get("vote_summary", {})
        return (
            f"⏸ *SKIP* — `{result['instrument']}`\n\n"
            f"Причина: {result.get('reason')}\n"
            f"Голоси: ⬆{votes.get('UP_votes',0)}  ⬇{votes.get('DOWN_votes',0)}  ➖{votes.get('NEUTRAL_votes',0)}\n\n"
            f"_{result.get('recommendation', '')}_"
        )

    direction = result["direction"]
    emoji = "🟢 ВГОРУ" if direction == "UP" else "🔴 ВНИЗ"
    conf = result["confidence"]
    price = result.get("current_price", "?")

    a = result.get("analysis", {})
    votes = result.get("vote_summary", {}).get("votes", {})

    text = (
        f"{emoji}  *СИГНАЛ*  `{result['signal_id']}`\n\n"
        f"Пара: *{result['instrument']}*\n"
        f"Напрямок: *{direction}*\n"
        f"Впевненість: *{conf}%*\n"
        f"Ціна зараз: `{price}`\n"
        f"Експірація: *{result['expiration_minutes']} хв*\n\n"
        f"📈 *Аналіз:*\n"
        f"• RSI: `{a.get('rsi',{}).get('value')}` — {a.get('rsi',{}).get('interpretation')}\n"
        f"• MACD: `{a.get('macd',{}).get('value')}` — {a.get('macd',{}).get('interpretation')}\n"
        f"• Bollinger: {a.get('bollinger',{}).get('interpretation')}\n"
        f"• Volume: ratio `{a.get('volume',{}).get('ratio')}` — {a.get('volume',{}).get('interpretation')}\n"
        f"• Trend: {a.get('trend',{}).get('ups_out_of_7')}/7 — {a.get('trend',{}).get('interpretation')}\n\n"
        f"🗳 *Голоси:*\n"
        f"`RSI` {votes.get('RSI')}\n"
        f"`MACD` {votes.get('MACD')}\n"
        f"`BB` {votes.get('Bollinger')}\n"
        f"`Vol` {votes.get('Volume')}\n"
        f"`Trend` {votes.get('Trend')}\n\n"
        f"💭 {result.get('reasoning', '')}"
    )
    return text


async def analyze_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Доступ закрито.")
        return

    args = context.args
    symbol = "ETH_USDT"
    if args:
        raw = args[0].upper().replace("-", "_").replace("USDT", "_USDT")
        if not raw.endswith("_USDT"):
            raw = raw + "_USDT"
        symbol = raw

    await update.message.reply_text(f"⏳ Аналізую `{symbol}` на MEXC...", parse_mode="Markdown")

    try:
        stats = get_stats()
        result = analyzer.analyze(symbol, historical_stats=stats)

        if result["action"] == "SEND_SIGNAL":
            hist = load_history()
            hist["total_signals"] = hist.get("total_signals", 0) + 1
            hist["signals"].append({
                "signal_id": result["signal_id"],
                "symbol": symbol,
                "direction": result["direction"],
                "confidence": result["confidence"],
                "price": result.get("current_price"),
                "time": result.get("timestamp"),
                "result": None
            })
            hist["signals"] = hist["signals"][-100:]
            save_history(hist)

        text = format_signal(result)
        await update.message.reply_text(text, parse_mode="Markdown")

        if result["action"] == "SEND_SIGNAL":
            json_str = json.dumps(result, indent=2, ensure_ascii=False)
            if len(json_str) < 3500:
                await update.message.reply_text(f"```json\n{json_str}\n```", parse_mode="Markdown")

    except Exception as e:
        logger.exception("Analyze error")
        await update.message.reply_text(f"❌ Помилка аналізу: `{e}`", parse_mode="Markdown")


async def signal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.args = ["ETH_USDT"]
    await analyze_cmd(update, context)


async def mark_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Використання: `/win #SIGNALID` або `/loss #SIGNALID`")
        return

    signal_id = args[0]
    is_win = update.message.text.startswith("/win")

    hist = load_history()
    found = False
    for s in hist.get("signals", []):
        if s.get("signal_id") == signal_id and s.get("result") is None:
            s["result"] = "WIN" if is_win else "LOSS"
            if is_win:
                hist["wins"] = hist.get("wins", 0) + 1
            else:
                hist["losses"] = hist.get("losses", 0) + 1
            found = True
            break

    if found:
        save_history(hist)
        await update.message.reply_text(f"✅ Записано як {'WIN' if is_win else 'LOSS'}")
    else:
        await update.message.reply_text("Сигнал не знайдено або вже закритий.")


def main():
    if BOT_TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
        print("=" * 60)
        print("ERROR: Встав свій Telegram Bot Token!")
        print("1. Напиши @BotFather → /newbot")
        print("2. Скопіюй токен")
        print("3. Заміни PASTE_YOUR_BOT_TOKEN_HERE у bot.py")
        print("   або експортуй: export TELEGRAM_BOT_TOKEN=твій_токен")
        print("=" * 60)
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("analyze", analyze_cmd))
    app.add_handler(CommandHandler("signal", signal_cmd))
    app.add_handler(CommandHandler("win", mark_result))
    app.add_handler(CommandHandler("loss", mark_result))

    print("Bot started. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
