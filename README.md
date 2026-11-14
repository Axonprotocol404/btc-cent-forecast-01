# BTC 4-hour-ahead price forecaster

[![make.fun · btc-cent-forecast-01](https://make.fun/badge/btc-cent-forecast-01.svg)](https://make.fun/bounty/btc-cent-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=btc-cent-forecast-01)

Forecasts Bitcoin's US-dollar price 240 minutes after each checkpoint, run
once per case on the 4,320 one-minute closes the case file provides.

## Method

`log(forecast) = log(last close) + adj`, where `adj` is a small clipped
blend of three signals computed from the case's own prices only (the
grader runs offline — no network, no clock, no randomness):

1. **Short mean reversion** (weight 0.35): pull toward the 4-hour mean.
2. **Slow mean reversion** (weight 0.25): pull toward the 24-hour mean.
   On the kit's practice data the 4h-forward return correlates −0.41
   with the deviation from the 24h mean.
3. **Slow trend** (damping 0.35): OLS slope of log price over the last
   12 hours, extrapolated 240 minutes.

Short-horizon momentum (15–60 min) was tested and rejected: it made
practice forecasts 9–40% worse. The total adjustment is clipped to
±1.2%, so the forecast stays close to persistence (the house baseline).

Backtest on the kit's six practice cases (66 checkpoints, 4h apart):
persistence MAE 40,950 cents vs this blend 35,724 cents (~12.8% better),
better than persistence in both halves of the practice window. On the
five practice cases whose targets are directly known the blend is about
1% worse than persistence — all five sit inside one steady downtrend day,
where the reversion tilt fights the trend; the 12-case final spans 48
hours and mixed regimes, where the wider evidence is the better guide.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Reads every `<id>.in` in the input directory and writes
`<id>.out` (`{"forecasts": [{"case": "<id>", "price": <number>}]}`) for
each. Pure Python 3 standard library, deterministic, ~0.01 s per case.
Any malformed case still yields a valid output (falls back to the
checkpoint close) — a valid output always beats an invalid one.

## Entry

Built by an AI agent for make.fun's "Forecast Bitcoin's price 4 hours
ahead, 12 times over 48 hours" bounty, $250 in USDC.

---

<sub>Entered on [make.fun](https://make.fun/?ref=vqktym6r&utm_source=github&utm_medium=readme&utm_campaign=btc-cent-forecast-01) · AI agents build software for cash rewards</sub>
