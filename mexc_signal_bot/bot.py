#!/usr/bin/env python3
"""
MEXC Event Futures Multi-Agent Signal Bot
- Only ETH_USDT + BTC_USDT
- 4 agents voting
- Session based (on/off by user)
- Auto win/loss detection after 10 minutes
- History tracking
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, JobQueue

from agents import MultiAgentSystem

def load_env():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

load_env()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN_HERE")
DATA_DIR = Path(__file__).parent
HISTORY_FILE = DATA_DIR / "history.json"
ACTIVE_SIGNALS_FILE = DATA_DIR / "active_signals.json"
SESSION_FILE = DATA_DIR / "session.json"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
system = MultiAgentSystem()

def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default

def save_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def get_session() -> Dict:
    return load_json(SESSION_FILE, {"active": False, "chat_id": None, "started_at": None})

def set_session(active: bool, chat_id: int = None):
    data = {"active": active, "chat_id": chat_id, "started_at": datetime.now(timezone.utc).isoformat() if active else None}
    save_json(SESSION_FILE, data)

def get_history() -> List[Dict]:
    return load_json(HISTORY_FILE, [])

def add_to_history(record: Dict):
    hist = get_history()
    hist.append(record)
    save_json(HISTORY_FILE, hist[-200:])

def get_active_signals() -> List[Dict]:
    return load_json(ACTIVE_SIGNALS_FILE, [])

def save_active_signals(signals: List[Dict]):
    save_json(ACTIVE_SIGNALS_FILE, signals)

def format_signal(res: Dict) -> str:
    if res["action"] != "SIGNAL":
        return None
    emoji = "🟢 ВГОРУ" if res["direction"] == "UP" else "🔴 ВНИЗ"
    agents_text = ""
    for a in res.get("agents", []):
        mark = "✅" if a["direction"] == res["direction"] else "➖"
        agents_text += f"{mark} {a['agent']}: {a['direction']} ({a['confidence']}%) — {a['reason']}\n"
    return (
        f"{emoji}  *СИГНАЛ*\n\n"
        f"Пара: *{res['symbol']}*\n"
        f"Напрямок: *{res['direction']}*\n"
        f"Впевненість: *{res['confidence']}%*\n"
        f"Згодилися: *{res['agreed']}/4* агентів\n"
        f"Ціна входу: `{res['price']}`\n"
        f"Експірація: *10 хвилин*\n\n"
        f"🤖 Голоси агентів:\n{agents_text}\n"
        f"_Після 10 хв система сама перевірить результат._"
    )

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 *MEXC Multi-Agent Signal Bot*\n\n"
        "Тільки *ETHUSDT* і *BTCUSDT*\n"
        "4 агенти + мін. 60% + 3 з 4 голосів\n\n"
        "Команди:\n"
        "`/session` — увімкнути сесію\n"
        "`/stop` — вимкнути сесію\n"
        "`/status` — стан\n"
        "`/history` — останні результати\n"
        "`/force` — перевірити ринок зараз\n\n"
        "Коли сесія увімкнена — бот сам шукає і пише сигнали."
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def session_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    set_session(True, chat_id)
    await update.message.reply_text("✅ *Сесія увімкнена*\n\nБот аналізує ETHUSDT і BTCUSDT.\nЩоб зупинити — /stop", parse_mode="Markdown")
    await run_scan(context, chat_id)

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_session(False)
    await update.message.reply_text("⏹ Сесію зупинено.")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sess = get_session()
    active_sigs = get_active_signals()
    hist = get_history()
    wins = sum(1 for h in hist if h.get("result") == "WIN")
    losses = sum(1 for h in hist if h.get("result") == "LOSS")
    total = wins + losses
    acc = round(wins / total * 100, 1) if total else 0
    text = (
        f"📊 *Статус*\n\n"
        f"Сесія: {'🟢 Увімкнена' if sess.get('active') else '🔴 Вимкнена'}\n"
        f"Активних сигналів: `{len(active_sigs)}`\n"
        f"Всього закритих: `{total}`\n"
        f"Виграшів: `{wins}` | Програшів: `{losses}`\n"
        f"Точність: `{acc}%`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hist = get_history()[-10:]
    if not hist:
        await update.message.reply_text("Історія порожня.")
        return
    lines = []
    for h in reversed(hist):
        res = h.get("result", "?")
        emoji = "✅" if res == "WIN" else "❌" if res == "LOSS" else "⏳"
        lines.append(f"{emoji} {h.get('symbol')} {h.get('direction')} | {h.get('confidence')}% | {res}")
    await update.message.reply_text("📜 *Останні 10:*\n\n" + "\n".join(lines), parse_mode="Markdown")

async def force_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Примусова перевірка...")
    await run_scan(context, update.effective_chat.id, force=True)

async def run_scan(context: ContextTypes.DEFAULT_TYPE, chat_id: int, force: bool = False):
    sess = get_session()
    if not sess.get("active") and not force:
        return
    try:
        results = system.analyze_both()
    except Exception as e:
        logger.error(f"Scan error: {e}")
        return
    active = get_active_signals()
    now = datetime.now(timezone.utc)
    for res in results:
        if res["action"] != "SIGNAL":
            continue
        if any(s["symbol"] == res["symbol"] and s.get("status") == "open" for s in active):
            continue
        text = format_signal(res)
        if not text:
            continue
        try:
            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Send error: {e}")
            continue
        signal_record = {
            "id": f"{res['symbol']}_{int(now.timestamp())}",
            "symbol": res["symbol"],
            "direction": res["direction"],
            "confidence": res["confidence"],
            "entry_price": res["price"],
            "agreed": res["agreed"],
            "opened_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=10)).isoformat(),
            "status": "open",
            "result": None
        }
        active.append(signal_record)
        save_active_signals(active)
        logger.info(f"Signal: {res['symbol']} {res['direction']} {res['confidence']}%")

async def check_results(context: ContextTypes.DEFAULT_TYPE):
    active = get_active_signals()
    if not active:
        return
    now = datetime.now(timezone.utc)
    still_open = []
    sess = get_session()
    chat_id = sess.get("chat_id")
    for sig in active:
        if sig.get("status") != "open":
            continue
        expires = datetime.fromisoformat(sig["expires_at"].replace("Z", "+00:00"))
        if now < expires + timedelta(seconds=45):
            still_open.append(sig)
            continue
        try:
            current_price = system.get_price(sig["symbol"])
        except Exception as e:
            logger.error(f"Price check failed: {e}")
            still_open.append(sig)
            continue
        entry = sig["entry_price"]
        direction = sig["direction"]
        won = (current_price > entry) if direction == "UP" else (current_price < entry)
        result = "WIN" if won else "LOSS"
        sig["status"] = "closed"
        sig["result"] = result
        sig["exit_price"] = current_price
        sig["closed_at"] = now.isoformat()
        add_to_history(sig)
        if chat_id:
            emoji = "✅ ВИГРАШ" if won else "❌ ПРОГРАШ"
            text = f"{emoji}\n\nПара: *{sig['symbol']}*\nНапрямок: {sig['direction']}\nВхід: `{entry}` → Вихід: `{current_price}`\nВпевненість була: {sig['confidence']}%"
            try:
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
            except Exception:
                pass
        logger.info(f"Result {result}: {sig['symbol']} {direction}")
    save_active_signals(still_open)

async def periodic_job(context: ContextTypes.DEFAULT_TYPE):
    sess = get_session()
    if not sess.get("active"):
        return
    chat_id = sess.get("chat_id")
    if not chat_id:
        return
    await check_results(context)
    await run_scan(context, chat_id)

def main():
    if BOT_TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
        print("=" * 50)
        print("Встав TELEGRAM_BOT_TOKEN в .env або змінну середовища!")
        print("=" * 50)
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("session", session_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("history", history_cmd))
    app.add_handler(CommandHandler("force", force_cmd))
    job_queue = app.job_queue
    job_queue.run_repeating(periodic_job, interval=45, first=10)
    print("Multi-Agent Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
