"""Generate comparison and per-strategy notebooks from the available report names.

Run in the visualizer conda environment. Existing notebooks require --overwrite.
"""

import argparse
from pathlib import Path
import sys
import textwrap

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from visualizer.strategy_analysis import load_strategies


def md(source):
    return nbf.v4.new_markdown_cell(textwrap.dedent(source).strip())


def code(source):
    return nbf.v4.new_code_cell(textwrap.dedent(source).strip())


SETUP = '''
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display, Markdown

def find_project_root():
    for path in (Path.cwd(), *Path.cwd().parents):
        if (path / "src" / "visualizer" / "strategy_analysis.py").is_file():
            return path
    raise FileNotFoundError("Start Jupyter inside the visualizer repository")

PROJECT_ROOT = find_project_root()
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from visualizer.strategy_analysis import (
    load_strategies, comparison_table, strategy_summary, expectancy_stats,
    monthly_table, drawdown_episodes, SimulationConfig, strategy_risk_scenarios,
    risk_win_matrix, SCREENSHOT_REFERENCE, position_size,
)
from visualizer.strategy_charts import (
    expectancy_chart, equity_comparison, equity_small_multiples, heatmap,
    daily_chart, elapsed_day_chart, trade_diagnostics, monthly_chart,
)

get_ipython().run_line_magic("matplotlib", "inline")
pd.options.display.float_format = "{:,.4f}".format
plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False})

def show_table(frame):
    """Keep exported data numeric; format fractions only for notebook display."""
    percentage_columns = {
        "win_rate", "loss_rate", "total_return", "risk_coverage", "risk_fraction_coverage", "max_trade_drawdown",
        "max_daily_drawdown", "median_risk_fraction", "p95_risk_fraction", "max_risk_fraction",
        "return_fraction", "worst_daily_drawdown", "drawdown_fraction", "risk_fraction",
        "realized_loss_fraction", "success_probability", "drawdown_breach_probability",
        "timeout_probability", "monte_carlo_se",
    }
    fmt = {col: "{:.2%}" if col in percentage_columns else "{:,.2f}"
           for col in frame.select_dtypes(include="number").columns}
    display(frame.style.format(fmt, na_rep="N/A"))
'''

CONFIG = '''
# Editable scenario, not the unknown assumptions behind the screenshot.
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "strategy_report"
SIMULATION = SimulationConfig(
    target_return=0.10,     # reach +10% of starting simulated equity
    max_drawdown=0.10,     # stop at a 10% fall from the running equity peak
    horizon_trades=100,
    paths=5000,
    seed=42,
)
EXPORT = True
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "strategy_analysis"
FIGURE_DIR = PROJECT_ROOT / "outputs" / "figures" / "strategy"
if EXPORT:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

strategies = load_strategies(RAW_DIR)  # reads ZIP members directly; no extraction needed
summary = comparison_table(strategies)
print(f"Loaded {len(strategies)} strategies from {RAW_DIR}")
'''

METHOD = r'''
## Definitions and data contract

- **Expectancy (INR/trade)** = win rate × average net win − loss rate × absolute average net loss. Rates use **all closed trades**, including breakevens. A value strictly greater than zero passes the requested acceptance screen. Fees are already included in `net_pnl`; do not deduct them again.
- **Realized equity** = initial cash + cumulative closed-trade net P&L. **Cumulative return** = equity / initial cash − 1. Trade curves are ordered by exit timestamp and start at trade zero. Percentages are account returns, not the sum of individual instrument returns.
- **Drawdown** = equity / running peak − 1, with initial capital included in the peak. Daily return = day's realized net P&L / previous day's realized equity. Trade drawdown can be deeper than end-of-day drawdown.
- **Initial stop risk (INR)** = adverse distance from entry to the **first `PLACE_SL` trigger** × original quantity. **Risk per trade** = initial stop risk / realized equity strictly before entry. A later trailing stop in `order_log.csv` is unsuitable for this calculation. `net_r` = net P&L / initial stop risk. Risk excludes fees and slippage, so a realized loss can exceed 1R. It is not a maximum possible loss.
- Equity excludes unrealized P&L, margin requirements and risk from concurrent open positions. Same-timestamp exits are excluded from equity before entry because their within-second ordering is unknown. Missing, delayed or inconsistent original stops remain unknown instead of being guessed.
- Rows without complete closed outcomes are listed separately. Dates without realized closes are carried forward on the calendar; this does not prove those dates had complete market data. First and last months may be partial. Report periods and trade counts differ across strategies.
- Some source end-of-day exits precede their entry by seconds. These rows retain reported P&L and original-stop R for reconciliation/simulation, but holding time, pre-entry equity and percentage risk are unknown. `chronology_errors` counts these rows; repair the source before relying on intraday execution results. Initial-stop coverage and percentage-risk coverage are shown separately.

The supplied order IDs use `MOCK` and report metadata includes a backtest intrabar policy. Treat these as reported simulated outcomes. Positive historical expectancy is a screening result; independent forward/out-of-sample evidence is needed to assess future payouts.

The 95% expectancy interval resamples **whole active exit days** 5,000 times (seed 42), preserving within-day trade dependence. It assumes independent days and does not account for selecting the best strategy from many trials.

Formula references: [CME: mathematical expectation](https://www.cmegroup.com/education/courses/trading-psychology/the-mathematics-of-trading-success) and [CME: position size from stop distance and account risk](https://www.cmegroup.com/education/courses/trade-and-risk-management/proper-position-size).
'''

SIM_METHOD = r'''
## Risk per trade and the screenshot

The screenshot supplies risk rows **0.25%, 0.5%, 1%, 1.5%, 2.5%, 4%** and win-rate columns **40%–90%**, but no definition of the percentages inside it. Its numbers are retained below **only as a reference**, not attributed to these strategies.

Our separate, editable simulation measures **the probability of reaching the configured return target before breaching the configured peak-to-trough drawdown limit, within the configured number of trades**. These are example assumptions, not inferred screenshot settings or provider payout rules.

Each path starts at equity 1 and updates as `equity *= max(0, 1 + risk_fraction * sampled_net_R)`. Target and drawdown checks occur after every trade; hitting either barrier ends that path. A drawdown breach takes precedence; a path hitting neither barrier is a timeout.

The observed-win-rate table resamples the strategy's full empirical net-R distribution. The win-rate grid varies the probability of winning while sampling the strategy's observed winning and losing R sizes separately, retaining the observed breakeven rate. It therefore shows sensitivity to hypothetical win rates, not validated improvement in the strategy.

Trades are sampled independently with replacement; streak dependence and regime shifts can make real risk worse. Historical net-R includes recorded charges; scaling it assumes costs and fills scale proportionally, ignores lot sizes, and is a research approximation. `monte_carlo_se` measures simulation noise only, not uncertainty in the historical sample. No risk level is automatically recommended.
'''

AUDIT = '''
audit = pd.concat([d.checks.assign(strategy=name) for name, d in strategies.items()], ignore_index=True)
show_table(summary[["trades", "excluded_rows", "chronology_errors", "initial_cash", "start_date", "end_date", "active_days", "reconciled", "risk_coverage", "risk_fraction_coverage"]])
assert audit.passed.all(), audit.loc[~audit.passed].to_string(index=False)
excluded = pd.concat([d.excluded.assign(strategy=name) for name, d in strategies.items()], ignore_index=True)
if not excluded.empty:
    display(Markdown("**Rows excluded from realized performance:**"))
    display(excluded[["strategy", "id", "timestamp", "status", "exclusion_reason"]])
display(Markdown(f"**All {len(audit)} reconciliation checks passed.**"))
chronology_issues = pd.concat([d.trades.loc[~d.trades.chronology_valid].assign(strategy=name) for name, d in strategies.items()], ignore_index=True)
if not chronology_issues.empty:
    display(Markdown("**Source chronology errors (reported P&L retained):**"))
    display(chronology_issues[["strategy", "id", "timestamp", "exit_time", "status", "net_pnl"]])
'''


def overview_cells():
    return [
        md("""# Strategy analysis: expectancy, edge and risk

        Compare every strategy in `data/raw/strategy_report`, then open its linked notebook for return and drawdown by day. Run all cells with the **Python from the visualizer conda environment** kernel. All money amounts are INR; exported fractions use `0.01 = 1%`.
        """),
        code(SETUP), code(CONFIG), md(METHOD),
        md("## Report inventory and reconciliation\nThe closed-trade ledger must agree with daily P&L, daily equity, charges and summary totals before comparison."),
        code(AUDIT),
        md("## 1. Risk matrix: expectancy acceptance\nAccept when **net expectancy > 0**. The confidence interval, drawdown and recent expectancy provide context alongside this rule."),
        code('''
        screen = summary[["trades", "win_rate", "loss_rate", "avg_win", "avg_loss", "expectancy", "expectancy_ci_low", "expectancy_ci_high", "profit_factor", "recent_30_expectancy"]].copy()
        screen["decision"] = np.where(summary.expectancy_positive, "ACCEPT: positive expectancy", "REJECT: non-positive expectancy")
        show_table(screen)
        fig = expectancy_chart(summary)
        if EXPORT:
            fig.savefig(FIGURE_DIR / "expectancy.png", dpi=160, bbox_inches="tight")
        plt.show()
        '''),
        md("## 2. Edge: cumulative return vs number of trades\nClick legend names to hide/show strategies; double-click to isolate one. All curves use net P&L and their own reported initial capital. Different trade counts and exposure mean this is not a like-for-like forward test."),
        code('''
        interactive_equity = equity_comparison(strategies)
        interactive_equity.show(renderer="plotly_mimetype")
        fig = equity_small_multiples(strategies)
        if EXPORT:
            interactive_equity.write_html(FIGURE_DIR / "equity_comparison.html", include_plotlyjs=True)
            fig.savefig(FIGURE_DIR / "equity_by_trade.png", dpi=160, bbox_inches="tight")
        plt.show()
        show_table(summary[["net_pnl", "gross_pnl", "charges", "total_return", "max_trade_drawdown", "max_daily_drawdown", "max_loss_streak"]])
        '''),
        md(SIM_METHOD),
        code('''
        fig = heatmap(SCREENSHOT_REFERENCE, "Screenshot reference • percentage event unspecified", fractions=False)
        plt.show()
        show_table(summary[["trades", "win_rate", "median_risk_fraction", "p95_risk_fraction", "max_risk_fraction", "risk_coverage", "risk_fraction_coverage", "mean_net_r"]])
        print("Simulation settings:", SIMULATION)
        '''),
        code('''
        risk_tables = {name: strategy_risk_scenarios(d, SIMULATION) for name, d in strategies.items()}
        risk_results = pd.concat(risk_tables, names=["strategy", "risk_fraction"]).reset_index()
        probability = risk_results.pivot(index="strategy", columns="risk_fraction", values="success_probability")
        fig = heatmap(probability, "Simulated target-before-drawdown probability at observed win rate", xlabel="Risk per trade", ylabel="Strategy")
        if EXPORT:
            fig.savefig(FIGURE_DIR / "risk_probability.png", dpi=160, bbox_inches="tight")
        plt.show()
        show_table(risk_results)
        '''),
        code('''
        # Change this to inspect another strategy's win-rate sensitivity grid.
        SELECTED_STRATEGY = "timeseries_trend_v3"
        matrix = risk_win_matrix(strategies[SELECTED_STRATEGY], SIMULATION)
        fig = heatmap(matrix, f"{SELECTED_STRATEGY} • simulated target-before-drawdown probability")
        plt.show()
        '''),
        md("## 4. Return and drawdown vs days\nEach notebook below contains the same definitions, its full daily history, monthly returns, drawdown episodes, trade diagnostics and risk scenarios."),
        code('''
        display(Markdown("\\n".join(f"- [{name}]({name}.ipynb)" for name in strategies)))
        '''),
        md("## Export results\nCSV outputs retain full numeric precision. Re-run this notebook after replacing reports. Keep one bundle per strategy in `RAW_DIR`; ambiguous duplicates raise an error."),
        code('''
        if EXPORT:
            summary.to_csv(OUTPUT_DIR / "strategy_summary.csv")
            screen.to_csv(OUTPUT_DIR / "expectancy_screen.csv")
            audit.to_csv(OUTPUT_DIR / "reconciliation.csv", index=False)
            risk_results.to_csv(OUTPUT_DIR / "risk_scenarios.csv", index=False)
            excluded.to_csv(OUTPUT_DIR / "excluded_orders.csv", index=False)
            chronology_issues.to_csv(OUTPUT_DIR / "chronology_issues.csv", index=False)
            print(f"Saved tables to {OUTPUT_DIR} and charts to {FIGURE_DIR}")
        '''),
    ]


def detail_cells(name):
    return [
        md(f"# {name}: return, drawdown and trade risk\n\n[Back to strategy comparison](analysis.ipynb). Run all cells with **Python from the visualizer conda environment**. Money amounts are INR. This notebook recomputes all results from the raw reports."),
        code(SETUP), code(CONFIG), code(f'STRATEGY = {name!r}\ndata = strategies[STRATEGY]\ntrades = data.trades\ndaily = data.daily\nprint("Source:", data.source)'),
        md(METHOD),
        md("## Data quality and expectancy\nAcceptance follows the requested rule: net expectancy strictly greater than zero."),
        code('''
        display(data.checks)
        assert data.checks.passed.all(), "Reconciliation failed: inspect the table above"
        row = summary.loc[[STRATEGY]]
        show_table(row[["trades", "wins", "losses", "breakevens", "excluded_rows", "win_rate", "avg_win", "avg_loss", "expectancy", "expectancy_ci_low", "expectancy_ci_high", "profit_factor"]])
        decision = "ACCEPT: positive net expectancy" if row.expectancy_positive.iloc[0] else "REJECT: non-positive net expectancy"
        display(Markdown(f"**{decision}**"))
        if not data.excluded.empty:
            display(data.excluded[["id", "timestamp", "status", "exclusion_reason"]])
        chronology_issues = trades.loc[~trades.chronology_valid]
        if not chronology_issues.empty:
            display(Markdown("**Source chronology errors (holding time and percentage risk unknown):**"))
            display(chronology_issues[["id", "timestamp", "exit_time", "status", "net_pnl"]])
        show_table(row[["initial_cash", "start_date", "end_date", "active_days", "net_pnl", "charges", "total_return", "max_daily_drawdown", "max_trade_drawdown", "max_loss_streak"]])
        '''),
        md("## Return and drawdown vs days\nCalendar dates include days without a realized close. Daily drawdown uses end-of-day realized equity and a running peak that starts at initial capital."),
        code('''
        fig = daily_chart(data)
        if EXPORT:
            fig.savefig(FIGURE_DIR / f"{STRATEGY}_daily.png", dpi=160, bbox_inches="tight")
        plt.show()
        fig = elapsed_day_chart(data)
        plt.show()
        display(daily.tail(15))
        '''),
        md("## Monthly returns and drawdown recovery\nMonthly return uses beginning-of-month equity. The worst daily drawdown column measures the fall from the full-history peak. Episode duration counts calendar days from peak to recovery, or to the end of the sample if unrecovered."),
        code('''
        monthly = monthly_table(data)
        show_table(monthly)
        fig = monthly_chart(monthly, STRATEGY)
        plt.show()
        episodes = drawdown_episodes(data)
        show_table(episodes.head(10))
        '''),
        md("## Trade-level edge and stability\nThe rolling mean uses the last 30 completed trades. Outcome signs come from net P&L: a `STOPLOSS HIT` may still be a winner after a trailing stop."),
        code('''
        fig = trade_diagnostics(data)
        if EXPORT:
            fig.savefig(FIGURE_DIR / f"{STRATEGY}_trades.png", dpi=160, bbox_inches="tight")
        plt.show()
        '''),
        md(SIM_METHOD),
        code('''
        show_table(row[["median_risk_fraction", "p95_risk_fraction", "max_risk_fraction", "risk_coverage", "risk_fraction_coverage", "mean_net_r"]])
        show_table(trades[["id", "timestamp", "entry_price", "initial_stop", "initial_qty", "initial_risk", "equity_before_entry", "risk_fraction", "net_pnl", "net_r", "realized_loss_fraction"]].head(12))
        print("Simulation settings:", SIMULATION)
        risk_scenarios = strategy_risk_scenarios(data, SIMULATION)
        show_table(risk_scenarios.reset_index())
        matrix = risk_win_matrix(data, SIMULATION)
        fig = heatmap(matrix, f"{STRATEGY} • simulated target-before-drawdown probability")
        if EXPORT:
            fig.savefig(FIGURE_DIR / f"{STRATEGY}_risk_matrix.png", dpi=160, bbox_inches="tight")
        plt.show()
        '''),
        md("## Position-size calculation\nBudget = account equity × selected risk fraction. Quantity = floor(budget / risk per unit), rounded down to the configured lot size. The example uses the first trade's original stop and starting account equity. Edit the inputs for your intended trade; `LOT_SIZE = 1` shows unconstrained units and does not assert an exchange lot size. Estimated costs are an input, and margin/premium affordability needs separate evaluation."),
        code('''
        EXAMPLE_RISK_FRACTION = 0.01  # illustration, not a recommendation
        LOT_SIZE = 1                # replace with the applicable contract lot size
        ESTIMATED_COST_PER_UNIT = 0.0
        example = trades.sort_values("timestamp").iloc[0]
        sizing = position_size(
            account_equity=data.initial_cash,
            risk_fraction=EXAMPLE_RISK_FRACTION,
            entry_price=example.entry_price,
            stop_price=example.initial_stop,
            lot_size=LOT_SIZE,
            cost_per_unit=ESTIMATED_COST_PER_UNIT,
        )
        display(pd.Series(sizing, name="Illustrative position size").to_frame())
        '''),
        md("## Export full analysis\nNormalized trades include the original stop, pre-entry equity, initial risk, net R, realized equity and drawdown. Calendar-day CSVs retain decimal fractions (`0.01 = 1%`)."),
        code('''
        if EXPORT:
            dest = OUTPUT_DIR / STRATEGY
            dest.mkdir(parents=True, exist_ok=True)
            trades.to_csv(dest / "trades.csv", index=False)
            daily.to_csv(dest / "daily.csv")
            monthly.to_csv(dest / "monthly.csv")
            episodes.to_csv(dest / "drawdown_episodes.csv", index=False)
            risk_scenarios.to_csv(dest / "risk_scenarios.csv")
            matrix.to_csv(dest / "risk_win_matrix.csv")
            data.excluded.to_csv(dest / "excluded_orders.csv", index=False)
            print(f"Saved full analysis to {dest}")
        '''),
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    strategies = load_strategies(ROOT / "data" / "raw" / "strategy_report")
    target = ROOT / "notebooks" / "strategy"
    target.mkdir(parents=True, exist_ok=True)
    notebooks = {"analysis": overview_cells(), **{name: detail_cells(name) for name in strategies}}
    if not args.overwrite and any((target / f"{name}.ipynb").exists() for name in notebooks):
        raise FileExistsError("Notebooks already exist; pass --overwrite to regenerate them")
    for name, cells in notebooks.items():
        notebook = nbf.v4.new_notebook(cells=cells, metadata={
            "kernelspec": {"display_name": "Python (visualizer)", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"},
        })
        nbf.validate(notebook)
        nbf.write(notebook, target / f"{name}.ipynb")
    print(f"Created {len(notebooks)} notebooks in {target}")


if __name__ == "__main__":
    main()
