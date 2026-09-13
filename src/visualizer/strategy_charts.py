"""Notebook charts for the strategy analysis framework (no global style changes)."""

import math

import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .strategy_analysis import equity_curve


def expectancy_chart(summary):
    data = summary.sort_values("expectancy")
    fig, ax = plt.subplots(figsize=(12, 6), layout="constrained")
    colors = np.where(data.expectancy_positive, "#13866a", "#c94c4c")
    ax.barh(data.index, data.expectancy, color=colors, alpha=0.85)
    ax.hlines(np.arange(len(data)), data.expectancy_ci_low, data.expectancy_ci_high, color="#28344a", linewidth=2, label="95% day-bootstrap interval")
    ax.axvline(0, color="#28344a", linewidth=1)
    ax.set(title="Net expectancy per closed trade", xlabel="INR per trade, after recorded charges")
    ax.legend(loc="lower right")
    ax.grid(axis="x", alpha=0.2)
    return fig


def equity_comparison(strategies):
    fig = go.Figure()
    for name, data in strategies.items():
        curve = equity_curve(data.trades.net_pnl, data.initial_cash)
        fig.add_trace(go.Scatter(x=curve.trade_number, y=curve.cumulative_return, name=name,
                                 mode="lines", hovertemplate="Trade %{x}<br>Return %{y:.2%}<extra>%{fullData.name}</extra>"))
    fig.update_layout(template="plotly_white", title="Realized cumulative return vs number of closed trades",
                      xaxis_title="Number of closed trades (ordered by exit time)",
                      yaxis_title="Net P&L / initial capital", yaxis_tickformat=".0%", height=570,
                      legend=dict(orientation="h", y=-0.2), margin=dict(b=150))
    return fig


def equity_small_multiples(strategies):
    columns = 3
    rows = math.ceil(len(strategies) / columns)
    fig, axes = plt.subplots(rows, columns, figsize=(15, rows * 2.8), squeeze=False, layout="constrained")
    for ax, (name, data) in zip(axes.flat, strategies.items()):
        curve = equity_curve(data.trades.net_pnl, data.initial_cash)
        ax.plot(curve.trade_number, curve.cumulative_return, color="#2463aa", linewidth=1.6)
        ax.axhline(0, color="gray", linewidth=0.7)
        ax.set(title=name, xlabel="Closed trades", ylabel="Return")
        ax.yaxis.set_major_formatter(PercentFormatter(1))
        ax.grid(alpha=0.2)
    for ax in list(axes.flat)[len(strategies):]:
        ax.set_visible(False)
    fig.suptitle("Equity curves from trade zero • each panel uses its own scale", fontsize=15)
    return fig


def heatmap(table, title, xlabel="Win rate", ylabel="Risk per trade", fractions=True):
    values = table.to_numpy(dtype=float) * (100 if fractions else 1)
    fig, ax = plt.subplots(figsize=(9, 5.5), layout="constrained")
    im = ax.imshow(values, cmap="YlGnBu", vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(len(table.columns)), [f"{x * 100:g}%" if isinstance(x, (float, np.floating)) else str(x) for x in table.columns], rotation=0)
    ax.set_yticks(range(len(table.index)), [f"{x:.2%}" if isinstance(x, (float, np.floating)) else str(x) for x in table.index])
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            ax.text(j, i, f"{values[i, j]:.0f}%", ha="center", va="center", color="white" if values[i, j] > 55 else "#17243a")
    ax.set(title=title, xlabel=xlabel, ylabel=ylabel)
    fig.colorbar(im, ax=ax, label="Percent")
    return fig


def daily_chart(data):
    d = data.daily
    # Add starting capital before the first calendar day for a visible zero baseline.
    dates = d.index.insert(0, d.index.min() - pd.Timedelta(days=1))
    fig, axes = plt.subplots(3, 1, figsize=(13, 10), sharex=True, layout="constrained")
    axes[0].plot(dates, np.r_[0, d.cumulative_return], color="#2463aa", linewidth=1.8)
    axes[0].set(ylabel="Cumulative return", title=f"{data.name} • realized returns and drawdown by calendar day")
    axes[1].fill_between(dates, np.r_[0, d.drawdown_fraction], 0, color="#c94c4c", alpha=0.7)
    axes[1].set(ylabel="Drawdown from peak")
    axes[2].bar(d.index, d.daily_return, color=np.where(d.net_pnl >= 0, "#13866a", "#c94c4c"), width=1)
    axes[2].set(ylabel="Daily return", xlabel="Date (gaps have no realized closes in the supplied ledger)")
    for ax in axes:
        ax.yaxis.set_major_formatter(PercentFormatter(1))
        ax.axhline(0, color="gray", linewidth=0.6)
        ax.grid(alpha=0.2)
    return fig


def elapsed_day_chart(data):
    fig, ax = plt.subplots(figsize=(12, 3.8), layout="constrained")
    ax.plot(np.r_[0, data.daily.elapsed_days], np.r_[0, data.daily.cumulative_return], label="Cumulative return", color="#2463aa")
    ax.plot(np.r_[0, data.daily.elapsed_days], np.r_[0, data.daily.drawdown_fraction], label="Drawdown", color="#c94c4c")
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.set(title=f"{data.name} • return and drawdown vs days", xlabel="Calendar days since start (day 0 = initial capital)", ylabel="Fraction of capital / peak")
    ax.legend()
    ax.grid(alpha=0.2)
    return fig


def trade_diagnostics(data, rolling_trades=30):
    t = data.trades
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), layout="constrained")
    curve = equity_curve(t.net_pnl, data.initial_cash)
    axes[0, 0].plot(curve.trade_number, curve.cumulative_return, color="#2463aa")
    axes[0, 0].set(title="Cumulative return vs closed trades", xlabel="Closed trades", ylabel="Return")
    axes[0, 0].yaxis.set_major_formatter(PercentFormatter(1))
    axes[0, 1].hist(t.net_pnl, bins="auto", color="#2463aa", alpha=0.8)
    axes[0, 1].axvline(0, color="#c94c4c")
    axes[0, 1].set(title="Net trade outcome distribution", xlabel="Net P&L (INR)", ylabel="Trades")
    axes[1, 0].plot(t.trade_number, t.net_pnl.rolling(rolling_trades, min_periods=rolling_trades).mean(), color="#13866a")
    axes[1, 0].axhline(0, color="#c94c4c")
    axes[1, 0].set(title=f"Rolling {rolling_trades}-trade expectancy", xlabel="Closed trades", ylabel="Mean net P&L (INR)")
    by_entry = t.sort_values("timestamp")
    axes[1, 1].plot(by_entry.timestamp, by_entry.risk_fraction, color="#9863b8", marker=".", markersize=3)
    axes[1, 1].set(title="Original stop risk / realized equity before entry", xlabel="Entry date", ylabel="Risk per trade")
    axes[1, 1].yaxis.set_major_formatter(PercentFormatter(1))
    axes[1, 1].tick_params(axis="x", rotation=25)
    for ax in axes.flat:
        ax.grid(alpha=0.2)
    return fig


def monthly_chart(monthly, name):
    fig, ax = plt.subplots(figsize=(12, 3.8), layout="constrained")
    ax.bar(monthly.index, monthly.return_fraction, color=np.where(monthly.return_fraction >= 0, "#13866a", "#c94c4c"))
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.set(title=f"{name} • monthly return on beginning-of-month equity", ylabel="Monthly return", xlabel="Month (first and last may be partial)")
    ax.tick_params(axis="x", rotation=30)
    ax.grid(axis="y", alpha=0.2)
    return fig
