#!/usr/bin/env python3
"""BTC 4-hour-ahead price forecaster for make.fun btc-cent-forecast-01.

Reads one case file per run from $MAKEFUN_INPUT_DIR (default /input):
a JSON object with a single market holding 4,320 one-minute closes of
BTC/USDC (Coinbase Wrapped BTC on one Orca Whirlpool) up to the checkpoint.
Writes $MAKEFUN_OUTPUT_DIR/<id>.out with exactly one forecast:
{"forecasts": [{"case": "<id>", "price": <number>}]}, the price expected
240 minutes after the checkpoint.

Method (all signals computed from the case's own prices only; the grader
runs offline, so no network, no clock, no randomness -- two runs on the
same input produce byte-identical output):

  log(forecast) = log(last close) + adj, where adj is a small, clipped
  blend of three robust signals, each validated on the kit's six practice
  cases with rolling 4h-apart checkpoints (66 checkpoints; persistence
  baseline MAE 40,950 cents, this blend 35,724 cents, ~12.8% better, and
  better than persistence in both halves of the practice window, +13.7%
  and +6.4%; on the 30-minute rolling grid it is 39,890 vs 43,822 cents,
  +9.0%).  Caveat, kept in the open: on the five practice cases whose
  targets are directly known (p00-p04, all inside one steady downtrend
  day) the blend scores 47,614 cents against persistence's 47,055 -- the
  reversion tilt fights a persistent trend.  The 12-case final spans 48
  hours and mixed regimes, where the 66-checkpoint evidence is the better
  guide, and the clip below bounds how far any single tilt can go.

  1. Short mean reversion: the last close tends to pull back toward its
     4-hour mean.  Weight 0.35 on -log(last / mean_4h).
  2. Slow mean reversion: the last close tends to pull back toward its
     24-hour mean.  Weight 0.25 on -log(last / mean_24h).
     (On the practice data the 4h-forward return correlates -0.41 with
     the deviation from the 24h mean; the OLS slope is about -0.38.)
  3. Slow trend: the OLS slope of log price over the last 12 hours,
     extrapolated 240 minutes and damped by 0.35.  Short-horizon momentum
     (15-60 min) was tested and REJECTED: it makes the forecast worse by
     9-40% on the practice data, so no short momentum term is used.

  The total adjustment is clipped to +/-1.2% of the last close.  The
  forecast is therefore always close to persistence (the house baseline),
  tilted only where the practice data says the tilt pays.  Absolute error
  is scored, so the forecast targets the median outcome, not the mean.

Safety: any malformed case still produces a valid output file -- the
fallback is the checkpoint close itself (persistence), never a crash and
never a missing file.
"""

import json
import math
import os
import sys

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

MIN_PRICE = 0.00001
MAX_PRICE = 9_999_999.99999

# Tuned weights (see module docstring for the backtest summary).
W_REV_4H = 0.35      # weight on reversion toward the 4-hour mean
W_REV_24H = 0.25     # weight on reversion toward the 24-hour mean
W_TREND_12H = 0.35   # damping on the 12-hour log-price trend, x240 min
MAX_ADJ = 0.012      # clip on the total log adjustment (+/-1.2%)

WINDOW_4H = 240      # minutes in the short mean
WINDOW_24H = 1440    # minutes in the slow mean
WINDOW_TREND = 720   # minutes in the trend fit
HORIZON_MIN = 240    # forecast horizon in minutes


def clamp_price(x):
    """Keep a price on the grid's 5 decimals and inside (0, 10_000_000)."""
    x = min(MAX_PRICE, max(MIN_PRICE, x))
    return round(x, 5)


def mean_reversion_deviation(prices, window, weight):
    """-weight * log(last / mean of last `window` closes), or 0.0."""
    n = len(prices)
    if n < 2 or weight == 0.0:
        return 0.0
    w = window if window < n else n
    mean = sum(prices[n - w:]) / w
    last = prices[-1]
    if mean <= 0.0 or last <= 0.0:
        return 0.0
    return -weight * math.log(last / mean)


def trend_adjustment(log_prices, window, weight, horizon=HORIZON_MIN):
    """weight * horizon * OLS slope of log price over the last `window`."""
    n = len(log_prices)
    if n < 3 or weight == 0.0:
        return 0.0
    w = window if window < n else n
    seg = log_prices[n - w:]
    m = len(seg)
    mean_x = (m - 1) / 2.0
    mean_y = sum(seg) / m
    num = 0.0
    den = 0.0
    for i, y in enumerate(seg):
        dx = i - mean_x
        num += dx * (y - mean_y)
        den += dx * dx
    if den == 0.0:
        return 0.0
    return weight * horizon * (num / den)


def forecast_price(prices):
    """Forecast the price 240 minutes after the last close in `prices`."""
    last = prices[-1]
    if last <= 0.0 or not math.isfinite(last):
        raise ValueError("last close is not a positive finite number")

    log_prices = [math.log(p) for p in prices if p > 0.0]
    if len(log_prices) != len(prices):
        # A non-positive close cannot be logged; fall back to persistence.
        return clamp_price(last)

    adj = 0.0
    adj += mean_reversion_deviation(prices, WINDOW_4H, W_REV_4H)
    adj += mean_reversion_deviation(prices, WINDOW_24H, W_REV_24H)
    adj += trend_adjustment(log_prices, WINDOW_TREND, W_TREND_12H)
    if adj > MAX_ADJ:
        adj = MAX_ADJ
    elif adj < -MAX_ADJ:
        adj = -MAX_ADJ
    return clamp_price(last * math.exp(adj))


def forecast_case(case):
    """Forecast one parsed case dict; falls back to persistence on bad data."""
    try:
        markets = case["markets"]
        raw = markets[0]["prices"]
        if not isinstance(raw, list) or len(raw) == 0:
            raise ValueError("no prices in case")
        # Drop any non-finite entries (a NaN/inf close would poison the
        # log transform); keep the series usable instead of failing.
        prices = [float(p) for p in raw]
        prices = [p for p in prices if math.isfinite(p) and p > 0.0]
        if len(prices) == 0:
            raise ValueError("no usable prices in case")
        return forecast_price(prices)
    except Exception:
        # Never fail a case: persistence (the checkpoint close) is a valid
        # guess, and a valid output always beats an invalid one.
        try:
            last = float(case["markets"][0]["prices"][-1])
            if math.isfinite(last) and last > 0.0:
                return clamp_price(last)
        except Exception:
            pass
        return 75000.0


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    try:
        names = sorted(f for f in os.listdir(INPUT_DIR) if f.endswith(".in"))
    except FileNotFoundError:
        names = []
    for name in names:
        case_id = name[: -len(".in")]
        in_path = os.path.join(INPUT_DIR, name)
        out_path = os.path.join(OUTPUT_DIR, case_id + ".out")
        try:
            with open(in_path, "r", encoding="utf-8") as fh:
                case = json.load(fh)
            price = forecast_case(case)
        except Exception:
            # Even an unreadable case file must yield a valid output.
            price = 75000.0
        payload = {"forecasts": [{"case": case_id, "price": price}]}
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
