# data/fetcher.py — Récupération des données de marché

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TECHNICAL, VIX


def fetch_ohlcv(ticker: str, period: str = "1y", interval: str = "1d") -> Optional[pd.DataFrame]:
    """
    Récupère les données OHLCV (Open/High/Low/Close/Volume) pour un ticker.
    Retourne None si les données sont insuffisantes.
    """
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period, interval=interval, auto_adjust=True)

        if df.empty or len(df) < 50:
            return None

        df.index = pd.to_datetime(df.index)
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.columns = ["open", "high", "low", "close", "volume"]
        df = df.dropna()

        return df

    except Exception:
        return None


def fetch_vix() -> dict:
    """
    Fetch VIX level and determine market regime.
    Returns dict with vix_level, regime label, and regime color.
    """
    try:
        vix = yf.Ticker(VIX["ticker"])
        hist = vix.history(period="5d")
        if hist.empty:
            return {"vix_level": None, "regime": "UNKNOWN", "color": "gray"}

        level = float(hist["Close"].iloc[-1])

        if level < VIX["calm_max"]:
            regime, color = "CALM", "green"
        elif level < VIX["elevated_max"]:
            regime, color = "ELEVATED", "orange"
        else:
            regime, color = "PANIC", "red"

        return {"vix_level": round(level, 1), "regime": regime, "color": color}

    except Exception:
        return {"vix_level": None, "regime": "UNKNOWN", "color": "gray"}


def fetch_benchmark(ticker: str = "SPY", period: str = "1y") -> pd.DataFrame | None:
    """Fetch benchmark (SPY) OHLCV for relative strength calculation."""
    return fetch_ohlcv(ticker, period=period)


def fetch_earnings_date(ticker: str) -> str | None:
    """
    Return the next earnings date as ISO string, or None if unavailable.
    """
    try:
        stock = yf.Ticker(ticker)
        cal = stock.calendar
        if cal is None:
            return None
        # yfinance returns calendar as a dict or DataFrame depending on version
        if isinstance(cal, dict):
            date = cal.get("Earnings Date")
            if isinstance(date, list) and date:
                return str(date[0].date()) if hasattr(date[0], "date") else str(date[0])
            return str(date) if date else None
        if isinstance(cal, pd.DataFrame) and "Earnings Date" in cal.columns:
            val = cal["Earnings Date"].iloc[0]
            return str(val.date()) if hasattr(val, "date") else str(val)
        return None
    except Exception:
        return None


def _to_float(val):
    """Safely coerce a value to float (Yahoo sometimes returns strings)."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def fetch_fundamentals(ticker: str) -> dict:
    """
    Récupère les données fondamentales via yfinance.
    Retourne un dict avec les métriques clés.
    """
    result = {
        "market_cap": None,
        "pe_ratio": None,
        "forward_pe": None,
        "peg_ratio": None,
        "price_to_book": None,
        "debt_to_equity": None,
        "ebitda": None,
        "ebitda_margin": None,
        "gross_margin": None,
        "operating_margin": None,
        "revenue_growth": None,
        "earnings_growth": None,
        "return_on_equity": None,
        "return_on_assets": None,
        "current_ratio": None,
        "quick_ratio": None,
        "free_cashflow": None,
        "dividend_yield": None,
        "sector": None,
        "industry": None,
        "name": ticker,
        "currency": "USD",
    }

    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        if not info or "symbol" not in info:
            return result

        # Identité
        result["name"] = info.get("longName", ticker)
        result["sector"] = info.get("sector", "Unknown")
        result["industry"] = info.get("industry", "Unknown")
        result["currency"] = info.get("currency", "USD")

        # Valorisation
        result["market_cap"] = _to_float(info.get("marketCap"))
        result["pe_ratio"] = _to_float(info.get("trailingPE"))
        result["forward_pe"] = _to_float(info.get("forwardPE"))
        result["peg_ratio"] = _to_float(info.get("pegRatio"))
        result["price_to_book"] = _to_float(info.get("priceToBook"))

        # Bilan
        result["debt_to_equity"] = _to_float(info.get("debtToEquity"))
        result["current_ratio"] = _to_float(info.get("currentRatio"))
        result["quick_ratio"] = _to_float(info.get("quickRatio"))
        result["free_cashflow"] = _to_float(info.get("freeCashflow"))

        # Rentabilité
        result["gross_margin"] = _to_float(info.get("grossMargins"))
        result["operating_margin"] = _to_float(info.get("operatingMargins"))
        result["ebitda_margin"] = _to_float(info.get("ebitdaMargins"))
        result["ebitda"] = _to_float(info.get("ebitda"))
        result["return_on_equity"] = _to_float(info.get("returnOnEquity"))
        result["return_on_assets"] = _to_float(info.get("returnOnAssets"))

        # Croissance
        result["revenue_growth"] = _to_float(info.get("revenueGrowth"))
        result["earnings_growth"] = _to_float(info.get("earningsGrowth"))

        # Dividendes
        result["dividend_yield"] = _to_float(info.get("dividendYield"))

    except Exception:
        pass

    return result


def fetch_batch(tickers: list[str], period: str = "1y", verbose: bool = True) -> dict:
    """
    Fetch OHLCV pour une liste de tickers.
    Retourne un dict {ticker: DataFrame}.
    """
    results = {}
    total = len(tickers)

    for i, ticker in enumerate(tickers):
        if verbose:
            print(f"\r  [{i+1}/{total}] Fetching {ticker:<12}", end="", flush=True)

        df = fetch_ohlcv(ticker, period=period)
        if df is not None:
            results[ticker] = df

    if verbose:
        print(f"\r  ✓ {len(results)}/{total} tickers chargés avec succès          ")

    return results


def get_price_change(df: pd.DataFrame, days: int) -> float:
    """Calcule la variation de prix sur N jours."""
    if len(df) < days:
        return 0.0
    return (df["close"].iloc[-1] / df["close"].iloc[-days] - 1) * 100


def get_52w_stats(df: pd.DataFrame) -> dict:
    """Retourne les stats 52 semaines."""
    if len(df) < 2:
        return {"high": None, "low": None, "pct_from_high": None, "pct_from_low": None}

    high = df["close"].max()
    low = df["close"].min()
    current = df["close"].iloc[-1]

    return {
        "high_52w": high,
        "low_52w": low,
        "pct_from_high": (current / high - 1) * 100,
        "pct_from_low": (current / low - 1) * 100,
    }
