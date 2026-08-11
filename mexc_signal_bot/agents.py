#!/usr/bin/env python3
"""
4 Agents for MEXC Event Futures (10-min UP/DOWN)
Only ETH_USDT and BTC_USDT
"""

import statistics
from typing import List, Dict, Tuple
from datetime import datetime, timezone
import numpy as np
import requests

class BaseAgent:
    name = "Base"
    def analyze(self, candles: List[Dict], current_price: float) -> Dict:
        raise NotImplementedError

class TechnicalAgent(BaseAgent):
    name = "Technical"
    def calc_rsi(self, closes: List[float], period: int = 14) -> Tuple[float, str, int]:
        if len(closes) < period + 1:
            return 50.0, "NEUTRAL", 0
        gains, losses = [], []
        for i in range(-period, 0):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        if rsi > 70: return round(rsi, 1), "DOWN", 68
        if rsi < 30: return round(rsi, 1), "UP", 68
        return round(rsi, 1), "NEUTRAL", 0
    def calc_ema(self, data: List[float], period: int) -> List[float]:
        if len(data) < period: return [np.nan] * len(data)
        ema = [np.nan] * (period - 1)
        sma = sum(data[:period]) / period
        ema.append(sma)
        mult = 2 / (period + 1)
        for price in data[period:]:
            ema.append((price - ema[-1]) * mult + ema[-1])
        return ema
    def calc_macd(self, closes: List[float]) -> Tuple[str, int]:
        if len(closes) < 35: return "NEUTRAL", 0
        ema12 = self.calc_ema(closes, 12)
        ema26 = self.calc_ema(closes, 26)
        macd_line = [a - b if not (np.isnan(a) or np.isnan(b)) else np.nan for a, b in zip(ema12, ema26)]
        valid = [m for m in macd_line if not np.isnan(m)]
        if len(valid) < 10: return "NEUTRAL", 0
        signal = self.calc_ema(valid, 9)
        signal_full = [np.nan] * (len(macd_line) - len(signal)) + signal
        hist = [m - s if not (np.isnan(m) or np.isnan(s)) else np.nan for m, s in zip(macd_line, signal_full)]
        last_m, last_s, last_h = macd_line[-1], signal_full[-1], hist[-1]
        prev_h = hist[-2] if len(hist) > 1 and not np.isnan(hist[-2]) else last_h
        if np.isnan(last_m) or np.isnan(last_s): return "NEUTRAL", 0
        if last_m > last_s and last_h > prev_h: return "UP", 70
        if last_m < last_s and last_h < prev_h: return "DOWN", 70
        return "NEUTRAL", 0
    def calc_trend(self, candles: List[Dict]) -> Tuple[str, int]:
        if len(candles) < 7: return "NEUTRAL", 0
        last7 = candles[-7:]
        ups = sum(1 for c in last7 if c["close"] >= c["open"])
        if ups >= 5: return "UP", 72
        if ups <= 2: return "DOWN", 72
        return "NEUTRAL", 0
    def analyze(self, candles: List[Dict], current_price: float) -> Dict:
        closes = [c["close"] for c in candles]
        rsi_val, rsi_dir, rsi_conf = self.calc_rsi(closes)
        macd_dir, macd_conf = self.calc_macd(closes)
        trend_dir, trend_conf = self.calc_trend(candles)
        votes = []
        if rsi_dir != "NEUTRAL": votes.append((rsi_dir, rsi_conf))
        if macd_dir != "NEUTRAL": votes.append((macd_dir, macd_conf))
        if trend_dir != "NEUTRAL": votes.append((trend_dir, trend_conf))
        if not votes: return {"agent": self.name, "direction": "NEUTRAL", "confidence": 0, "reason": "No clear technical signal"}
        up = [c for d, c in votes if d == "UP"]
        down = [c for d, c in votes if d == "DOWN"]
        if len(up) > len(down):
            return {"agent": self.name, "direction": "UP", "confidence": int(sum(up)/len(up)), "reason": f"RSI={rsi_val}, MACD+Trend support UP"}
        if len(down) > len(up):
            return {"agent": self.name, "direction": "DOWN", "confidence": int(sum(down)/len(down)), "reason": f"RSI={rsi_val}, MACD+Trend support DOWN"}
        return {"agent": self.name, "direction": "NEUTRAL", "confidence": 0, "reason": "Mixed technical signals"}

class MomentumAgent(BaseAgent):
    name = "Momentum"
    def analyze(self, candles: List[Dict], current_price: float) -> Dict:
        if len(candles) < 10: return {"agent": self.name, "direction": "NEUTRAL", "confidence": 0, "reason": "Not enough data"}
        last = candles[-1]
        vol = last["volume"]
        avg_vol = statistics.mean([c["volume"] for c in candles[-8:-1]]) or 1
        body = abs(last["close"] - last["open"])
        range_ = last["high"] - last["low"] or 1
        body_ratio = body / range_
        direction = "UP" if last["close"] > last["open"] else "DOWN"
        vol_ratio = vol / avg_vol
        conf, reason = 0, ""
        if vol_ratio > 1.8 and body_ratio > 0.6: conf, reason = 75, f"Strong candle + volume spike ({vol_ratio:.1f}x)"
        elif vol_ratio > 1.3 and body_ratio > 0.45: conf, reason = 65, f"Good momentum + volume ({vol_ratio:.1f}x)"
        elif vol_ratio < 0.7: conf, reason, direction = 40, "Weak volume", "NEUTRAL"
        else: conf, reason = 55, "Average momentum"
        closes = [c["close"] for c in candles[-5:]]
        if len(closes) >= 3:
            if closes[-1] > closes[-2] > closes[-3] and direction == "UP": conf = min(85, conf+8); reason += " + accelerating up"
            elif closes[-1] < closes[-2] < closes[-3] and direction == "DOWN": conf = min(85, conf+8); reason += " + accelerating down"
        if conf < 55: direction, conf = "NEUTRAL", 0
        return {"agent": self.name, "direction": direction, "confidence": conf, "reason": reason}

class StructureAgent(BaseAgent):
    name = "Structure"
    def analyze(self, candles: List[Dict], current_price: float) -> Dict:
        if len(candles) < 20: return {"agent": self.name, "direction": "NEUTRAL", "confidence": 0, "reason": "Not enough structure data"}
        highs = [c["high"] for c in candles[-12:]]
        lows = [c["low"] for c in candles[-12:]]
        higher_highs = highs[-1] > max(highs[:-1]) * 0.998
        higher_lows = lows[-1] > min(lows[:-3])
        lower_highs = highs[-1] < max(highs[:-1]) * 1.002
        lower_lows = lows[-1] < min(lows[:-3])
        range_mid = (max(highs) + min(lows)) / 2
        direction, conf, reason = "NEUTRAL", 0, ""
        if higher_highs and higher_lows: direction, conf, reason = "UP", 70, "Higher highs + higher lows"
        elif lower_highs and lower_lows: direction, conf, reason = "DOWN", 70, "Lower highs + lower lows"
        elif current_price > range_mid * 1.005: direction, conf, reason = "UP", 58, "Price in upper half of range"
        elif current_price < range_mid * 0.995: direction, conf, reason = "DOWN", 58, "Price in lower half of range"
        last3_up = sum(1 for c in candles[-3:] if c["close"] > c["open"])
        if last3_up == 3 and direction == "UP": conf = min(80, conf+7)
        if last3_up == 0 and direction == "DOWN": conf = min(80, conf+7)
        if conf < 55: direction, conf = "NEUTRAL", 0
        return {"agent": self.name, "direction": direction, "confidence": conf, "reason": reason}

class PatternAgent(BaseAgent):
    """Price Action + класичні патерни (engulfing, pinbar, valley, support bounce)"""
    name = "Pattern"
    def analyze(self, candles: List[Dict], current_price: float) -> Dict:
        if len(candles) < 15: return {"agent": self.name, "direction": "NEUTRAL", "confidence": 0, "reason": "Not enough data"}
        c, last, prev = candles, candles[-1], candles[-2]
        direction, conf, reasons = "NEUTRAL", 0, []
        # Engulfing
        if (prev["close"] < prev["open"] and last["close"] > last["open"] and last["close"] > prev["open"] and last["open"] < prev["close"]):
            direction, conf = "UP", 73; reasons.append("Bullish Engulfing")
        if (prev["close"] > prev["open"] and last["close"] < last["open"] and last["close"] < prev["open"] and last["open"] > prev["close"]):
            direction, conf = "DOWN", 73; reasons.append("Bearish Engulfing")
        # Pinbar
        body = abs(last["close"] - last["open"])
        upper_wick = last["high"] - max(last["close"], last["open"])
        lower_wick = min(last["close"], last["open"]) - last["low"]
        full_range = last["high"] - last["low"] or 1
        if lower_wick > body * 2.1 and lower_wick > upper_wick * 1.7 and body / full_range < 0.35:
            direction, conf = "UP", max(conf, 75); reasons.append("Bullish Pinbar (долина)")
        if upper_wick > body * 2.1 and upper_wick > lower_wick * 1.7 and body / full_range < 0.35:
            direction, conf = "DOWN", max(conf, 75); reasons.append("Bearish Pinbar")
        # Higher Low / Lower High
        lows = [x["low"] for x in c[-8:]]
        highs = [x["high"] for x in c[-8:]]
        if lows[-1] > lows[-3] and lows[-3] < lows[-5] and last["close"] > last["open"]:
            if direction != "DOWN": direction, conf = "UP", max(conf, 69); reasons.append("Higher Low (долина)")
        if highs[-1] < highs[-3] and highs[-3] > highs[-5] and last["close"] < last["open"]:
            if direction != "UP": direction, conf = "DOWN", max(conf, 69); reasons.append("Lower High")
        # Support / Resistance
        recent_low = min(x["low"] for x in c[-12:-1])
        if last["low"] <= recent_low * 1.003 and last["close"] > last["open"] and last["close"] > recent_low * 1.003:
            direction, conf = "UP", max(conf, 71); reasons.append("Відбій від підтримки")
        recent_high = max(x["high"] for x in c[-12:-1])
        if last["high"] >= recent_high * 0.997 and last["close"] < last["open"] and last["close"] < recent_high * 0.997:
            direction, conf = "DOWN", max(conf, 71); reasons.append("Відбій від опору")
        # 3 candles
        if all(x["close"] > x["open"] for x in c[-3:]) and direction == "UP": conf = min(83, conf+6); reasons.append("3 зелені")
        if all(x["close"] < x["open"] for x in c[-3:]) and direction == "DOWN": conf = min(83, conf+6); reasons.append("3 червоні")
        if conf < 60: direction, conf, reason = "NEUTRAL", 0, "Немає чіткого прайс-екшен патерну"
        else: reason = " + ".join(reasons)
        return {"agent": self.name, "direction": direction, "confidence": conf, "reason": reason}

class MultiAgentSystem:
    def __init__(self):
        self.agents = [TechnicalAgent(), MomentumAgent(), StructureAgent(), PatternAgent()]
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "MEXC-MultiAgent/1.0"})
    def get_klines(self, symbol: str, interval: str = "Min5", limit: int = 50) -> List[Dict]:
        url = f"https://contract.mexc.com/api/v1/contract/kline/{symbol}"
        r = self.session.get(url, params={"interval": interval}, timeout=10)
        r.raise_for_status()
        data = r.json()
        if not data.get("success"): raise RuntimeError(data)
        d = data["data"]
        candles = [{"time": d["time"][i], "open": float(d["open"][i]), "high": float(d["high"][i]), "low": float(d["low"][i]), "close": float(d["close"][i]), "volume": float(d.get("vol", [0]*len(d["time"]))[i])} for i in range(len(d["time"]))]
        return candles[-limit:]
    def get_price(self, symbol: str) -> float:
        r = self.session.get("https://contract.mexc.com/api/v1/contract/ticker", params={"symbol": symbol}, timeout=8)
        r.raise_for_status()
        return float(r.json()["data"]["lastPrice"])
    def analyze_pair(self, symbol: str) -> Dict:
        try:
            candles = self.get_klines(symbol, interval="Min5", limit=40)
            price = self.get_price(symbol)
        except Exception as e:
            return {"symbol": symbol, "action": "ERROR", "error": str(e)}
        results = [agent.analyze(candles, price) for agent in self.agents]
        up_votes = [r for r in results if r["direction"] == "UP"]
        down_votes = [r for r in results if r["direction"] == "DOWN"]
        final_dir, conf, agreed = "NEUTRAL", 0, 0
        if len(up_votes) >= 3:
            final_dir, agreed = "UP", len(up_votes)
            conf = int(sum(r["confidence"] for r in up_votes) / len(up_votes))
        elif len(down_votes) >= 3:
            final_dir, agreed = "DOWN", len(down_votes)
            conf = int(sum(r["confidence"] for r in down_votes) / len(down_votes))
        if conf < 60: final_dir, conf = "NEUTRAL", 0
        return {"symbol": symbol, "action": "SIGNAL" if final_dir != "NEUTRAL" else "SKIP", "direction": final_dir, "confidence": conf, "agreed": agreed, "price": price, "agents": results, "timestamp": datetime.now(timezone.utc).isoformat()}
    def analyze_both(self) -> List[Dict]:
        return [self.analyze_pair("ETH_USDT"), self.analyze_pair("BTC_USDT")]

if __name__ == "__main__":
    system = MultiAgentSystem()
    for r in system.analyze_both():
        print(r["symbol"], r["action"], r.get("direction"), r.get("confidence"), "% agreed:", r.get("agreed"))
        for a in r.get("agents", []):
            print(f"  - {a['agent']}: {a['direction']} ({a['confidence']}%) | {a['reason']}")
        print()
