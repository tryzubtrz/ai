# MEXC Multi-Agent Signal Bot

Система з **4 агентів** для 10-хвилинних Event Futures на MEXC.

### Тільки дві пари
- ETHUSDT
- BTCUSDT

### Правила
- Мінімум **3 з 4** агентів згодні
- Впевненість **≥ 60%**
- Сесія: `/session` увімкнути, `/stop` вимкнути
- Автоматична перевірка WIN/LOSS через 10 хв по ціні
- Історія угод

### 4 Агенти
1. Technical (RSI+MACD+Trend)
2. Momentum (свічка + обсяг)
3. Structure (higher highs/lows)
4. Context (SMA + волатильність)

### Ключі
Скопіюй `.env.example` → `.env` і встав токен.

### Запуск
```bash
python bot.py
```
