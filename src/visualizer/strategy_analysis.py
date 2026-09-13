"""Reproducible analysis of strategy report folders or ZIP archives.

The closed-trade ledger is authoritative. All amounts are INR; fraction columns
are decimal fractions (0.01 = 1%). Equity is realized, without open-position MTM.
"""

from dataclasses import dataclass
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import zipfile

import numpy as np
import pandas as pd


RISK_LEVELS = (0.0025, 0.005, 0.01, 0.015, 0.025, 0.04)
WIN_RATES = (0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
# Transcribed reference only: the screenshot does not define its probability event.
SCREENSHOT_REFERENCE = pd.DataFrame(
    [[28, 46, 65, 81, 90, 95], [24, 41, 61, 78, 89, 95],
     [18, 33, 52, 71, 84, 92], [13, 25, 43, 62, 79, 89],
     [7, 14, 26, 44, 63, 79], [3, 5, 10, 20, 36, 56]],
    index=pd.Index(RISK_LEVELS, name="risk_fraction"),
    columns=pd.Index(WIN_RATES, name="win_rate"),
)


@dataclass
class StrategyData:
    name: str
    source: str
    report: dict
    trades: pd.DataFrame
    excluded: pd.DataFrame
    daily: pd.DataFrame
    checks: pd.DataFrame

    @property
    def initial_cash(self):
        return float(self.report["meta"]["initial_cash"])


@dataclass(frozen=True)
class SimulationConfig:
    target_return: float = 0.10
    max_drawdown: float = 0.10
    horizon_trades: int = 100
    paths: int = 5000
    seed: int = 42

    def __post_init__(self):
        if not np.isfinite(self.target_return) or self.target_return <= 0:
            raise ValueError("target_return must be positive and finite")
        if not 0 < self.max_drawdown < 1:
            raise ValueError("max_drawdown must be between 0 and 1")
        for field in ("horizon_trades", "paths"):
            value = getattr(self, field)
            if not isinstance(value, int) or value < 1:
                raise ValueError(f"{field} must be a positive integer")


def _sources(raw_dir):
    """Discover bundles without extraction; ambiguous strategy versions fail loudly."""
    raw_dir = Path(raw_dir)
    if not raw_dir.is_dir():
        raise FileNotFoundError(raw_dir)
    bundles = []
    required = ("cumulative_report.json", "order_log.csv", "daily_pnl.csv", "order_event_log.json")
    for report_path in sorted(raw_dir.rglob("cumulative_report.json")):
        folder = report_path.parent
        bundles.append((str(folder), {name: (folder / name).read_bytes() for name in required}))
    for archive in sorted(raw_dir.rglob("*.zip")):
        with zipfile.ZipFile(archive) as z:
            for member in sorted(z.namelist()):
                if PurePosixPath(member).name != "cumulative_report.json":
                    continue
                parent = PurePosixPath(member).parent
                bundles.append((f"{archive}!{parent}", {
                    name: z.read(str(parent / name)) for name in required
                }))
    if not bundles:
        raise FileNotFoundError(f"No strategy report bundles in {raw_dir}")
    return bundles


def equity_curve(pnl, initial_cash):
    """Include trade zero so the first loss counts toward drawdown."""
    pnl = np.asarray(pnl, dtype=float)
    if not np.isfinite(initial_cash) or initial_cash <= 0 or not np.isfinite(pnl).all():
        raise ValueError("Equity requires positive initial cash and finite P&L")
    equity = np.r_[initial_cash, initial_cash + pnl.cumsum()]
    peak = np.maximum.accumulate(equity)
    return pd.DataFrame({
        "trade_number": np.arange(len(equity)), "equity": equity,
        "cumulative_pnl": equity - initial_cash,
        "cumulative_return": equity / initial_cash - 1,
        "drawdown": equity - peak, "drawdown_fraction": equity / peak - 1,
    })


def _prepare(source, files):
    report = json.loads(files["cumulative_report.json"])
    name = report["meta"]["strategy"]
    initial_cash = float(report["meta"]["initial_cash"])
    if not np.isfinite(initial_cash) or initial_cash <= 0:
        raise ValueError(f"{name}: initial_cash must be positive")
    orders = pd.read_csv(BytesIO(files["order_log.csv"]))
    needed = {"id", "timestamp", "exit_time", "status", "net_pnl", "gross_pnl",
              "total_charges", "entry_price", "exit_price", "qty", "side"}
    if missing := needed - set(orders):
        raise ValueError(f"{name}: missing order columns {sorted(missing)}")
    if orders.id.isna().any() or orders.id.duplicated().any():
        raise ValueError(f"{name}: missing or duplicate trade IDs")
    for col in ("timestamp", "exit_time"):
        orders[col] = pd.to_datetime(orders[col], errors="raise")
    if orders.timestamp.isna().any():
        raise ValueError(f"{name}: missing entry timestamps")
    closed_status = ~orders.status.str.upper().isin(["OPEN", "WAITING", "CANCELLED", "REJECTED"])
    closed = closed_status & orders.exit_time.notna() & orders.net_pnl.notna()
    excluded = orders.loc[~closed].copy()
    excluded["exclusion_reason"] = np.where(
        excluded.status.str.upper().eq("OPEN"), "Open position; no realized outcome",
        "Not a complete closed trade (check status, exit time and net P&L)",
    )
    trades = orders.loc[closed].sort_values(["exit_time", "timestamp", "id"], kind="stable").reset_index(drop=True)
    if trades.empty:
        raise ValueError(f"{name}: no completed trades")
    numeric = ["entry_price", "exit_price", "qty", "net_pnl", "gross_pnl", "total_charges"]
    if not np.isfinite(trades[numeric].to_numpy(dtype=float)).all():
        raise ValueError(f"{name}: non-finite trade data")
    if (trades.qty <= 0).any():
        raise ValueError(f"{name}: invalid quantity")
    # Preserve reported P&L for reconciliation, but do not invent valid chronology.
    trades["chronology_valid"] = trades.exit_time.ge(trades.timestamp)
    if not trades.side.isin(["BUY", "SELL"]).all():
        raise ValueError(f"{name}: unsupported trade side")

    # Read the FIRST stop placement; the order-log stoploss can already be trailed.
    events = pd.DataFrame(json.loads(files["order_event_log.json"])["events"])
    events["ts"] = pd.to_datetime(events.ts, errors="raise")
    first_sl = events.loc[events.event_type.eq("PLACE_SL")].sort_values("ts", kind="stable").drop_duplicates("trade_id").set_index("trade_id")
    first_entry = events.loc[events.event_type.eq("PLACE_ENTRY")].sort_values("ts", kind="stable").drop_duplicates("trade_id").set_index("trade_id")
    trades["initial_stop"] = trades.id.map(first_sl.trigger_price)
    trades["initial_stop_time"] = trades.id.map(first_sl.ts)
    trades["initial_qty"] = trades.id.map(first_entry.qty)
    event_entry_price = trades.id.map(first_entry.entry_price)
    direction = trades.side.map({"BUY": 1.0, "SELL": -1.0})
    distance = direction * (trades.entry_price - trades.initial_stop)
    # Only treat a contemporaneous protective stop and unchanged quantity as known risk.
    known_risk = (
        distance.gt(0) & np.isfinite(distance) & trades.initial_qty.eq(trades.qty)
        & np.isclose(event_entry_price, trades.entry_price, atol=1e-6, rtol=0)
        & trades.initial_stop_time.eq(trades.timestamp)
    )
    trades["initial_risk"] = (distance * trades.initial_qty).where(known_risk)

    # Realized account equity strictly BEFORE entry, even when trades overlap.
    # Same-timestamp exits are excluded because their intrasecond order is unknown.
    exit_ns = trades.exit_time.to_numpy(dtype="datetime64[ns]")
    entry_ns = trades.timestamp.to_numpy(dtype="datetime64[ns]")
    prior_count = np.searchsorted(exit_ns, entry_ns, side="left")
    cumulative = np.r_[0.0, trades.net_pnl.to_numpy().cumsum()]
    trades["equity_before_entry"] = initial_cash + cumulative[prior_count]
    trades.loc[~trades.chronology_valid, "equity_before_entry"] = np.nan
    trades["risk_fraction"] = trades.initial_risk / trades.equity_before_entry.where(trades.equity_before_entry.gt(0))
    trades["net_r"] = trades.net_pnl / trades.initial_risk
    trades["realized_loss_fraction"] = (-trades.net_pnl).clip(lower=0) / trades.equity_before_entry.where(trades.equity_before_entry.gt(0))
    trades["exit_date"] = trades.exit_time.dt.normalize()
    trades["holding_minutes"] = ((trades.exit_time - trades.timestamp).dt.total_seconds() / 60).where(trades.chronology_valid)
    trades["trade_number"] = np.arange(1, len(trades) + 1)
    curve = equity_curve(trades.net_pnl, initial_cash)
    for col in ("equity", "cumulative_pnl", "cumulative_return", "drawdown", "drawdown_fraction"):
        trades[col] = curve[col].iloc[1:].to_numpy()

    observed = pd.read_csv(BytesIO(files["daily_pnl.csv"]), parse_dates=["date"]).set_index("date").sort_index()
    if observed.index.has_duplicates or observed.index.hasnans:
        raise ValueError(f"{name}: duplicate or missing daily dates")
    grouped = trades.groupby("exit_date").agg(net_pnl=("net_pnl", "sum"), num_trades=("id", "size"))
    dates = grouped.index.union(observed.index)
    expected = grouped.reindex(dates, fill_value=0)
    reported = observed.reindex(dates)
    daily_pnl_error = (expected.net_pnl - reported.daily_pnl).abs().max()
    daily_count_error = (expected.num_trades - reported.num_trades).abs().max()
    # Calendar gaps mean no realized closes in this ledger, not verified market coverage.
    calendar = pd.date_range(min(orders.timestamp.min().normalize(), dates.min()), dates.max(), freq="D")
    daily = grouped.reindex(calendar, fill_value=0)
    daily.index.name = "date"
    daily["reported_day"] = daily.index.isin(observed.index)
    daily["equity"] = initial_cash + daily.net_pnl.cumsum()
    daily["equity_before_day"] = daily.equity.shift(1, fill_value=initial_cash)
    daily["daily_return"] = daily.net_pnl / daily.equity_before_day.where(daily.equity_before_day.gt(0))
    daily["cumulative_return"] = daily.equity / initial_cash - 1
    daily["peak_equity"] = daily.equity.cummax().clip(lower=initial_cash)
    daily["drawdown"] = daily.equity - daily.peak_equity
    daily["drawdown_fraction"] = daily.equity / daily.peak_equity - 1
    daily["elapsed_days"] = (daily.index - daily.index.min()).days + 1

    checks = []
    def check(label, error, tolerance=0.01):
        checks.append({"check": label, "absolute_error": error,
                       "passed": bool(np.isfinite(error) and abs(error) <= tolerance)})
    check("Gross P&L minus charges equals net P&L (max row error)", (trades.gross_pnl - trades.total_charges - trades.net_pnl).abs().max())
    check("Daily dates cover every realized exit date", len(grouped.index.difference(observed.index)), 0)
    check("Daily net P&L (max day error)", daily_pnl_error)
    check("Daily closed trade counts (max day error)", daily_count_error, 0)
    check("Daily equity (max day error)", (daily.equity.reindex(observed.index) - observed.equity).abs().max())
    summary = report["summary"]
    check("Report net P&L", trades.net_pnl.sum() - summary["total_net_pnl"])
    check("Report gross P&L", trades.gross_pnl.sum() - summary["total_gross_pnl"])
    check("Report charges", trades.total_charges.sum() - summary["total_charges"])
    check("Report closed trade count", len(trades) - summary["total_trades"], 0)
    check("Report current cash", daily.equity.iloc[-1] - report["meta"]["current_cash"])
    return StrategyData(name, source, report, trades, excluded, daily, pd.DataFrame(checks))


def load_strategies(raw_dir):
    result = {}
    for source, files in _sources(raw_dir):
        data = _prepare(source, files)
        if data.name in result:
            raise ValueError(f"Duplicate strategy {data.name!r}: keep one report bundle per strategy in RAW_DIR")
        result[data.name] = data
    return dict(sorted(result.items()))


def expectancy_stats(pnl):
    """Breakeven trades stay in the denominator; average loss is an absolute amount."""
    pnl = np.asarray(pnl, dtype=float)
    if not len(pnl) or not np.isfinite(pnl).all():
        raise ValueError("Expectancy requires a non-empty finite P&L sample")
    wins, losses = pnl[pnl > 0], -pnl[pnl < 0]
    win_rate, loss_rate = len(wins) / len(pnl), len(losses) / len(pnl)
    avg_win = wins.mean() if len(wins) else 0.0
    avg_loss = losses.mean() if len(losses) else 0.0
    expectancy = win_rate * avg_win - loss_rate * avg_loss
    return {
        "trades": len(pnl), "wins": len(wins), "losses": len(losses),
        "breakevens": int((pnl == 0).sum()), "win_rate": win_rate, "loss_rate": loss_rate,
        "avg_win": avg_win, "avg_loss": avg_loss, "expectancy": expectancy,
        "expectancy_positive": bool(expectancy > 0),
        "payoff_ratio": avg_win / avg_loss if avg_loss else np.nan,
        "profit_factor": wins.sum() / losses.sum() if len(losses) else (np.inf if len(wins) else np.nan),
        "net_pnl": pnl.sum(),
    }


def expectancy_interval(trades, paths=5000, seed=42):
    """95% percentile interval: resample whole active exit days, weighted by trades.

    Preserves within-day dependence, assumes independent days and a stable process.
    """
    grouped = trades.groupby("exit_date").net_pnl.agg(["sum", "count"])
    if len(grouped) < 2:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    indices = rng.integers(len(grouped), size=(paths, len(grouped)))
    means = grouped["sum"].to_numpy()[indices].sum(axis=1) / grouped["count"].to_numpy()[indices].sum(axis=1)
    return tuple(np.quantile(means, [0.025, 0.975]))


def max_loss_streak(pnl):
    longest = current = 0
    for value in pnl:
        current = current + 1 if value < 0 else 0
        longest = max(longest, current)
    return longest


def strategy_summary(data):
    t = data.trades
    stats = expectancy_stats(t.net_pnl)
    low, high = expectancy_interval(t)
    stats.update({
        "strategy": data.name, "initial_cash": data.initial_cash,
        "start_date": data.daily.index.min(), "end_date": data.daily.index.max(),
        "active_days": int(data.daily.num_trades.gt(0).sum()),
        "excluded_rows": len(data.excluded), "reconciled": bool(data.checks.passed.all()),
        "chronology_errors": int((~t.chronology_valid).sum()),
        "expectancy_ci_low": low, "expectancy_ci_high": high,
        "gross_pnl": t.gross_pnl.sum(), "charges": t.total_charges.sum(),
        "total_return": t.net_pnl.sum() / data.initial_cash,
        "max_trade_drawdown": t.drawdown_fraction.min(),
        "max_daily_drawdown": data.daily.drawdown_fraction.min(),
        "max_loss_streak": max_loss_streak(t.net_pnl),
        "median_risk_fraction": t.risk_fraction.median(),
        "p95_risk_fraction": t.risk_fraction.quantile(0.95),
        "max_risk_fraction": t.risk_fraction.max(),
        "risk_coverage": t.initial_risk.notna().mean(), "mean_net_r": t.net_r.mean(),
        "risk_fraction_coverage": t.risk_fraction.notna().mean(),
        "recent_30_expectancy": t.net_pnl.tail(30).mean(),
    })
    return stats


def comparison_table(strategies):
    return pd.DataFrame([strategy_summary(d) for d in strategies.values()]).set_index("strategy").sort_values("expectancy", ascending=False)


def monthly_table(data):
    d = data.daily
    result = d.groupby(d.index.to_period("M")).agg(
        net_pnl=("net_pnl", "sum"), trades=("num_trades", "sum"),
        beginning_equity=("equity_before_day", "first"), ending_equity=("equity", "last"),
        worst_daily_drawdown=("drawdown_fraction", "min"),
        reported_days=("reported_day", "sum"),
    )
    result["return_fraction"] = result.net_pnl / result.beginning_equity.where(result.beginning_equity.gt(0))
    result.index = result.index.astype(str)
    return result


def drawdown_episodes(data):
    """Calendar-day peak-to-recovery durations, including unrecovered drawdowns."""
    base_date = data.daily.index.min() - pd.Timedelta(days=1)
    equity = pd.concat([pd.Series([data.initial_cash], index=[base_date]), data.daily.equity])
    peak, peak_date, trough, trough_date = data.initial_cash, base_date, data.initial_cash, base_date
    active, rows = False, []
    for date, value in equity.items():
        if value >= peak:
            if active:
                rows.append((peak_date, trough_date, date, trough / peak - 1, (date - peak_date).days, True))
            peak, peak_date, active = value, date, False
        else:
            if not active or value < trough:
                trough, trough_date = value, date
            active = True
    if active:
        rows.append((peak_date, trough_date, pd.NaT, trough / peak - 1, (equity.index[-1] - peak_date).days, False))
    return pd.DataFrame(rows, columns=["peak_date", "trough_date", "recovery_date", "drawdown_fraction", "duration_days", "recovered"]).sort_values("drawdown_fraction")


def simulate_risk(net_r, risk_fraction, config=SimulationConfig(), win_rate=None):
    """P(target before peak drawdown breach), with absorbing barriers and timeout.

    Observed case resamples all empirical net R outcomes. A specified win_rate
    resamples conditional win/loss sizes while retaining the observed flat rate.
    The same seed gives common random draws across risk/accuracy scenarios.
    """
    values = np.asarray(net_r, dtype=float)
    if not len(values) or not np.isfinite(values).all():
        raise ValueError("Simulation requires complete finite initial-risk R multiples")
    if not np.isfinite(risk_fraction) or not 0 < risk_fraction < 1:
        raise ValueError("risk_fraction must be between 0 and 1")
    positive, negative = values[values > 0], values[values < 0]
    flat_rate = float(np.mean(values == 0))
    if win_rate is not None:
        if not np.isfinite(win_rate) or not 0 <= win_rate <= 1 - flat_rate:
            raise ValueError("win_rate plus observed breakeven rate must be <= 1")
        if win_rate > 0 and not len(positive) or win_rate + flat_rate < 1 and not len(negative):
            raise ValueError("Requested scenario requires missing win/loss samples")
    rng = np.random.default_rng(config.seed)
    equity, peak = np.ones(config.paths), np.ones(config.paths)
    active = np.ones(config.paths, dtype=bool)
    success = np.zeros(config.paths, dtype=bool)
    breached = np.zeros(config.paths, dtype=bool)
    for _ in range(config.horizon_trades):
        if win_rate is None:
            outcomes = rng.choice(values, config.paths)
        else:
            u = rng.random(config.paths)
            win_sizes = rng.choice(positive, config.paths) if len(positive) else np.zeros(config.paths)
            loss_sizes = rng.choice(negative, config.paths) if len(negative) else np.zeros(config.paths)
            outcomes = np.where(u < win_rate, win_sizes, np.where(u < win_rate + flat_rate, 0, loss_sizes))
        equity[active] *= np.maximum(0, 1 + risk_fraction * outcomes[active])
        peak = np.maximum(peak, equity)
        failed_now = active & ((1 - equity / peak) >= config.max_drawdown - 1e-12)
        won_now = active & ~failed_now & (equity >= 1 + config.target_return - 1e-12)
        success |= won_now
        breached |= failed_now
        active &= ~(failed_now | won_now)
    p = success.mean()
    return {
        "risk_fraction": risk_fraction, "success_probability": p,
        "drawdown_breach_probability": breached.mean(), "timeout_probability": active.mean(),
        "monte_carlo_se": np.sqrt(p * (1 - p) / config.paths),
    }


def strategy_risk_scenarios(data, config=SimulationConfig(), risks=RISK_LEVELS):
    if data.trades.net_r.isna().any():
        raise ValueError(f"{data.name}: incomplete original stops; cannot simulate all trades")
    return pd.DataFrame([simulate_risk(data.trades.net_r, f, config) for f in risks]).set_index("risk_fraction")


def risk_win_matrix(data, config=SimulationConfig(), risks=RISK_LEVELS, win_rates=WIN_RATES):
    return pd.DataFrame(
        [[simulate_risk(data.trades.net_r, f, config, p)["success_probability"] for p in win_rates] for f in risks],
        index=pd.Index(risks, name="risk_fraction"), columns=pd.Index(win_rates, name="win_rate"),
    )


def position_size(account_equity, risk_fraction, entry_price, stop_price, lot_size=1, cost_per_unit=0.0):
    """Budget-based illustration; round down to whole lots. No margin model."""
    inputs = [account_equity, risk_fraction, entry_price, stop_price, cost_per_unit]
    if not np.isfinite(inputs).all() or account_equity <= 0 or not 0 < risk_fraction < 1:
        raise ValueError("Invalid equity, prices, costs or risk fraction")
    if not isinstance(lot_size, int) or lot_size < 1 or cost_per_unit < 0:
        raise ValueError("lot_size must be a positive integer and costs nonnegative")
    distance = abs(entry_price - stop_price)
    if distance <= 0:
        raise ValueError("Entry and stop must differ")
    budget = account_equity * risk_fraction
    units = int(np.floor(budget / ((distance + cost_per_unit) * lot_size))) * lot_size
    return {"risk_budget": budget, "units": units, "lots": units // lot_size,
            "estimated_risk": units * (distance + cost_per_unit)}
