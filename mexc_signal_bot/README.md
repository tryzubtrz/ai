# MEXC Event Futures Signal Bot

Telegram-бот для сигналів на **10-хвилинні Event Futures (UP/DOWN)** на біржі MEXC.

Аналізує 15-хвилинні свічки за точною логікою з твого промпту:
- RSI (14)
- MACD
- Bollinger Bands
- Volume
- Trend (останні 7 свічок)
- Система голосування (мінімум 3 голоси)
- Мінімальна впевненість **65%**
- Консервативний підхід (краще SKIP, ніж поганий сигнал)

> ⚠️ **Важливо:** Event Futures на MEXC **не підтримують API-торгівлю**.  
> Бот тільки видає сигнал — ставити угоду потрібно вручну в додатку MEXC.

---

## Швидкий старт (локально)

### 1. Встанови залежності
```bash
cd mexc_signal_bot
pip install -r requirements.txt
```

### 2. Створи Telegram-бота
1. Відкрий Telegram → **@BotFather**
2. Напиши `/newbot`
3. Дай назву і username
4. Скопіюй **токен**

### 3. Встав токен
Відкрий файл `bot.py` і заміни рядок:
```python
BOT_TOKEN = "PASTE_YOUR_BOT_TOKEN_HERE"
```
або через змінну середовища:
```bash
export TELEGRAM_BOT_TOKEN="твій_токен_тут"
```

### 4. Запусти
```bash
python bot.py
```

Бот готовий. Пиши йому `/signal` або `/analyze ETH_USDT`.
