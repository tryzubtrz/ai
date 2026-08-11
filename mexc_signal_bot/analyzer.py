#!/usr/bin/env python3
"""
MEXC Event Futures Signal Analyzer
Implements the exact logic from the AI Trader Analyst prompt.
"""

import math
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
import statistics

import requests
import numpy as np


class MEXCAnalyzer:
    BASE_URL = "https://contract.mexc.com/api/v1/contract"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "MEXC-Signal-Bot/1.0",
            "Accept": "application/json"
        })

    def get_klines(self, symbol: str = "ETH_USDT", interval: str = "Min15", limit: int = 50) -> List[Dict]:
        """Fetch recent klines. Returns list of dicts sorted oldest -> newest."""
        url = f"{self.BASE_URL}/kline/{symbol}"
        params = {"interval": interval}
        try:
            r = self.session.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            if not data.get("success"):
                raise ValueError(f"API error: {data}")

            d = data["data"]
            times = d["time"]
            opens = d["open"]
            highs = d["high"]
            lows = d["low"]
            closes = d["close"]
            vols = d.get("vol", [0] * len(times))

            candles = []
            for i in range(len(times)):
                candles.append({
                    "time": datetime.fromtimestamp(times[i], tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                    "timestamp": times[i],
                    "open": float(opens[i]),
                    "high": float(highs[i]),
                    "low": float(lows[i]),
                    "close": float(closes[i]),
                    "volume": float(vols[i])
                })
            return candles[-limit:]
        except Exception as e:
            raise RuntimeError(f"Failed to fetch klines: {e}")

    def get_ticker(self, symbol: str = "ETH_USDT") -> Dict:
        url = f"{self.BASE_URL}/ticker"
        params = {"symbol": symbol}
        r = self.session.get(url, params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
        if not data.get("success"):
            raise ValueError(data)
        return data["data"]

    def calc_rsi(self, closes: List[float], period: int = 14) -> Tuple[float, str, int]:
        if len(closes) < period + 1:
            return 50.0, "NEUTRAL", 0

        gains = []
        losses = []
        for i in range(-period, 0):
            diff = closes[i] - closes[i - 1]
            if diff > 0:
                gains.append(diff)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(abs(diff))

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        if rsi > 70:
            return round(rsi, 2), "DOWN", 65
        elif rsi < 30:
            return round(rsi, 2), "UP", 65
        else:
            return round(rsi, 2), "NEUTRAL", 0

    def calc_ema(self, data: List[float], period: int) -> List[float]:
        if len(data) < period:
            return [np.nan] * len(data)
        ema = [np.nan] * (period - 1)
        sma = sum(data[:period]) / period
        ema.append(sma)
        multiplier = 2 / (period + 1)
        for price in data[period:]:
            ema.append((price - ema[-1]) * multiplier + ema[-1])
        return ema

    def calc_macd(self, closes: List[float]) -> Tuple[float, float, float, str, int]:
        if len(closes) < 35:
            return 0.0, 0.0, 0.0, "NEUTRAL", 0

        ema12 = self.calc_ema(closes, 12)
        ema26 = self.calc_ema(closes, 26)

        macd_line = []
        for i in range(len(closes)):
            if np.isnan(ema12[i]) or np.isnan(ema26[i]):
                macd_line.append(np.nan)
            else:
                macd_line.append(ema12[i] - ema26[i])

        valid_macd = [m for m in macd_line if not np.isnan(m)]
        if len(valid_macd) < 10:
            return 0.0, 0.0, 0.0, "NEUTRAL", 0

        signal = self.calc_ema(valid_macd, 9)
        signal_full = [np.nan] * (len(macd_line) - len(signal)) + signal

        hist = []
        for m, s in zip(macd_line, signal_full):
            if np.isnan(m) or np.isnan(s):
                hist.append(np.nan)
            else:
                hist.append(m - s)

        last_macd = macd_line[-1]
        last_signal = signal_full[-1]
        last_hist = hist[-1]
        prev_hist = hist[-2] if len(hist) > 1 and not np.isnan(hist[-2]) else last_hist

        if np.isnan(last_macd) or np.isnan(last_signal):
            return 0.0, 0.0, 0.0, "NEUTRAL", 0

        prev_macd = macd_line[-2] if len(macd_line) > 1 else last_macd
        prev_signal = signal_full[-2] if len(signal_full) > 1 else last_signal

        cross_up = prev_macd <= prev_signal and last_macd > last_signal
        cross_down = prev_macd >= prev_signal and last_macd < last_signal

        if cross_up:
            return round(last_macd, 4), round(last_signal, 4), round(last_hist, 4), "UP", 75
        if cross_down:
            return round(last_macd, 4), round(last_signal, 4), round(last_hist, 4), "DOWN", 75

        if last_macd > last_signal and last_hist > prev_hist:
            return round(last_macd, 4), round(last_signal, 4), round(last_hist, 4), "UP", 65
        if last_macd < last_signal and last_hist < prev_hist:
            return round(last_macd, 4), round(last_signal, 4), round(last_hist, 4), "DOWN", 65

        return round(last_macd, 4), round(last_signal, 4), round(last_hist, 4), "NEUTRAL", 0

    def calc_bollinger(self, closes: List[float], price: float, period: int = 20) -> Tuple[str, str, int]:
        if len(closes) < period:
            return "middle", "NEUTRAL", 0

        window = closes[-period:]
        middle = statistics.mean(window)
        std = statistics.stdev(window)
        upper = middle + 2 * std
        lower = middle - 2 * std

        if price >= upper * 0.98:
            return "upper", "DOWN", 62
        if price <= lower * 1.02:
            return "lower", "UP", 62
        return "middle", "NEUTRAL", 0

    def calc_volume(self, candles: List[Dict]) -> Tuple[float, str, int]:
        if len(candles) < 8:
            return 1.0, "NEUTRAL", 0

        current_vol = candles[-1]["volume"]
        avg_vol = statistics.mean([c["volume"] for c in candles[-8:-1]])
        if avg_vol == 0:
            ratio = 1.0
        else:
            ratio = current_vol / avg_vol

        last = candles[-1]
        direction = "UP" if last["close"] >= last["open"] else "DOWN"

        if direction == "UP" and ratio > 1.5:
            return round(ratio, 2), "UP", 68
        if direction == "DOWN" and ratio > 1.5:
            return round(ratio, 2), "DOWN", 68
        if direction == "UP" and ratio < 1.0:
            return round(ratio, 2), "UP", 40
        if direction == "DOWN" and ratio < 1.0:
            return round(ratio, 2), "DOWN", 40
        return round(ratio, 2), "NEUTRAL", 0

    def calc_trend(self, candles: List[Dict]) -> Tuple[int, str, int]:
        if len(candles) < 7:
            return 0, "NEUTRAL", 0

        last7 = candles[-7:]
        ups = sum(1 for c in last7 if c["close"] >= c["open"])
        downs = 7 - ups

        higher_highs = all(last7[i]["high"] > last7[i-1]["high"] for i in range(1, 7))
        higher_lows = all(last7[i]["low"] > last7[i-1]["low"] for i in range(1, 7))
        lower_highs = all(last7[i]["high"] < last7[i-1]["high"] for i in range(1, 7))
        lower_lows = all(last7[i]["low"] < last7[i-1]["low"] for i in range(1, 7))

        if ups >= 5:
            conf = 75 if (higher_highs and higher_lows) else 70
            return ups, "UP", conf
        if downs >= 5:
            conf = 75 if (lower_highs and lower_lows) else 70
            return ups, "DOWN", conf
        return ups, "NEUTRAL", 0

    def analyze(self, symbol: str = "ETH_USDT", historical_stats: Optional[Dict] = None,
                recent_trades: Optional[List] = None) -> Dict[str, Any]:
        try:
            candles = self.get_klines(symbol, interval="Min15", limit=50)
            ticker = self.get_ticker(symbol)
        except Exception as e:
            return {
                "action": "ERROR",
                "instrument": symbol,
                "error": str(e),
                "recommendation": "Check symbol or try again later"
            }

        if len(candles) < 26:
            return {
                "action": "ERROR",
                "instrument": symbol,
                "error": f"Not enough candlestick data (need ~30, got {len(candles)})",
                "recommendation": "Request with more historical candles"
            }

        closes = [c["close"] for c in candles]
        current_price = float(ticker["lastPrice"])
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        rsi_val, rsi_vote, rsi_conf = self.calc_rsi(closes)
        macd_val, signal_val, hist_val, macd_vote, macd_conf = self.calc_macd(closes)
        bb_pos, bb_vote, bb_conf = self.calc_bollinger(closes, current_price)
        vol_ratio, vol_vote, vol_conf = self.calc_volume(candles)
        ups, trend_vote, trend_conf = self.calc_trend(candles)

        votes = {
            "RSI": (rsi_vote, rsi_conf),
            "MACD": (macd_vote, macd_conf),
            "Bollinger": (bb_vote, bb_conf),
            "Volume": (vol_vote, vol_conf),
            "Trend": (trend_vote, trend_conf)
        }

        up_votes = []
        down_votes = []
        neutral_count = 0

        for name, (direction, conf) in votes.items():
            if direction == "UP":
                up_votes.append((name, conf))
            elif direction == "DOWN":
                down_votes.append((name, conf))
            else:
                neutral_count += 1

        up_count = len(up_votes)
        down_count = len(down_votes)

        if up_count >= 3:
            final_direction = "UP"
            confidences = [c for _, c in up_votes]
        elif down_count >= 3:
            final_direction = "DOWN"
            confidences = [c for _, c in down_votes]
        else:
            final_direction = "NEUTRAL"
            confidences = []

        if not confidences:
            avg_conf = 0
        else:
            avg_conf = sum(confidences) / len(confidences)

        if historical_stats:
            acc = historical_stats.get("accuracy_percentage", 50) / 100
            if acc < 0.60:
                avg_conf -= 3
            wr80 = historical_stats.get("win_rate_by_confidence", {}).get("80_plus", 0.7)
            if wr80 > 0.85 and avg_conf >= 75:
                avg_conf += 2

        avg_conf = max(0, min(99, round(avg_conf)))

        if final_direction == "NEUTRAL" or avg_conf < 65:
            return {
                "action": "SKIP",
                "instrument": symbol,
                "reason": f"Confidence too low ({avg_conf}%)" if avg_conf < 65 else "Votes split / no clear majority",
                "vote_summary": {
                    "UP_votes": up_count,
                    "DOWN_votes": down_count,
                    "NEUTRAL_votes": neutral_count
                },
                "recommendation": "Monitor for clearer signal or check other pairs",
                "current_price": current_price,
                "analysis_time": now
            }

        if rsi_val > 80 or rsi_val < 20:
            return {
                "action": "SKIP",
                "instrument": symbol,
                "reason": f"Extreme RSI ({rsi_val}) - possible trap",
                "vote_summary": {
                    "UP_votes": up_count,
                    "DOWN_votes": down_count,
                    "NEUTRAL_votes": neutral_count
                },
                "recommendation": "Wait for RSI to normalize"
            }

        signal_id = f"#{symbol.replace('_', '')}{datetime.now().strftime('%H%M')}"

        analysis = {
            "rsi": {
                "value": rsi_val,
                "interpretation": "Overbought" if rsi_val > 70 else ("Oversold" if rsi_val < 30 else "Neutral zone")
            },
            "macd": {
                "value": macd_val,
                "signal": signal_val,
                "histogram": hist_val,
                "interpretation": "Bullish momentum" if macd_vote == "UP" else ("Bearish momentum" if macd_vote == "DOWN" else "No clear momentum")
            },
            "bollinger": {
                "value": bb_pos,
                "interpretation": "Near upper band" if bb_pos == "upper" else ("Near lower band" if bb_pos == "lower" else "Price in middle of bands")
            },
            "volume": {
                "ratio": vol_ratio,
                "interpretation": f"{'Strong' if vol_conf >= 68 else 'Weak'} volume confirmation"
            },
            "trend": {
                "ups_out_of_7": ups,
                "interpretation": "Uptrend" if trend_vote == "UP" else ("Downtrend" if trend_vote == "DOWN" else "Sideways")
            }
        }

        vote_detail = {
            "RSI": f"{rsi_vote} ({rsi_conf}%)" if rsi_conf else "NEUTRAL",
            "MACD": f"{macd_vote} ({macd_conf}%)" if macd_conf else "NEUTRAL",
            "Bollinger": f"{bb_vote} ({bb_conf}%)" if bb_conf else "NEUTRAL",
            "Volume": f"{vol_vote} ({vol_conf}%)" if vol_conf else "NEUTRAL",
            "Trend": f"{trend_vote} ({trend_conf}%)" if trend_conf else "NEUTRAL"
        }

        reasoning_parts = []
        if trend_vote != "NEUTRAL":
            reasoning_parts.append(f"Trend shows {trend_vote.lower()} with {ups}/7 green candles")
        if macd_vote != "NEUTRAL":
            reasoning_parts.append(f"MACD {macd_vote.lower()} momentum")
        if vol_conf >= 68:
            reasoning_parts.append("Strong volume confirmation")
        if not reasoning_parts:
            reasoning_parts.append("Multiple indicators aligned")

        return {
            "action": "SEND_SIGNAL",
            "instrument": symbol,
            "direction": final_direction,
            "confidence": avg_conf,
            "expiration_minutes": 10,
            "signal_id": signal_id,
            "current_price": current_price,
            "analysis": analysis,
            "vote_summary": {
                "UP_votes": up_count,
                "DOWN_votes": down_count,
                "NEUTRAL_votes": neutral_count,
                "votes": vote_detail
            },
            "reasoning": ". ".join(reasoning_parts) + ".",
            "timestamp": now
        }


if __name__ == "__main__":
    analyzer = MEXCAnalyzer()
    result = analyzer.analyze("ETH_USDT")
    print(json.dumps(result, indent=2, ensure_ascii=False))
