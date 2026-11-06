# Chart Visualizer

A small Jupyter notebook project for exploring datasets and building charts with
Pandas, Matplotlib, Seaborn, and Plotly.

## Project Structure

```text
visualizer/
├── data/
│   ├── raw/                 # Source datasets
│   └── processed/           # Cleaned or transformed datasets
├── notebooks/
│   └── 01_chart_gallery.ipynb
├── outputs/
│   └── figures/             # Exported charts
├── src/
│   └── visualizer/          # Reusable helpers
├── requirements.txt
└── README.md
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Start Jupyter

```bash
jupyter lab
```

Open `notebooks/01_chart_gallery.ipynb` to try the sample charts.

## Strategy Report Analysis

Activate the existing environment and open the comparison notebook:

```bash
source /home/amit/anaconda3/etc/profile.d/conda.sh
conda deactivate
conda activate visualizer
jupyter lab notebooks/strategy/analysis.ipynb
```

Select the Python kernel from the activated `visualizer` environment and run all
cells. The notebooks use the `python3` kernel supplied by that environment.

The comparison covers net expectancy and acceptance, cumulative return versus
closed-trade count, original stop risk per trade, and configurable risk simulations.
Each strategy has a notebook under `notebooks/strategy/`, including
`timeseries_trend_v3.ipynb`, with daily returns, drawdown, monthly results and recovery
durations. Executed notebooks retain their charts and tables.

Place report folders or ZIP archives in `data/raw/strategy_report/`. Each strategy
needs `cumulative_report.json`, `order_log.csv`, `daily_pnl.csv` and
`order_event_log.json`. ZIPs are read directly. Keep one bundle per strategy; duplicate
strategy names raise an error. The notebooks reconcile reported totals and show
open rows and timestamp issues separately. All returns use realized net P&L after
recorded charges; open-position valuations are unavailable.

The screenshot's probability event is unspecified. Its values are labeled as a
reference. The computed matrices instead use editable example settings: reach a
10% return before a 10% peak drawdown within 100 trades, with 5,000 simulated paths.
These are research scenarios, not verified payout probabilities.

CSV tables are exported to `data/processed/strategy_analysis/`; PNG charts and an
offline interactive equity chart go to `outputs/figures/strategy/`. The shared
calculations live in `src/visualizer/strategy_analysis.py`. After adding a strategy,
regenerate notebook templates with the command below (this replaces notebook edits
and clears saved outputs), then run them again:

```bash
python scripts/create_strategy_notebooks.py --overwrite
python -m unittest discover -s tests -v
```

## Option Selling Research

Raw inputs live under `data/raw/option_selling/`:

```text
data/raw/option_selling/
├── nifty/     # weekly + futures expiry calendars, daily and hourly Nifty50 candles
└── stocks/    # nse_stock_expiry.csv (monthly calendar) + one daily candle JSON per symbol
```

Notebooks under `notebooks/option_selling/`:

| Notebook | Instrument | Candles | Expiry cycle |
|---|---|---|---|
| `nifty50/weekly_expiry_move_table.ipynb` | Nifty50 | daily | weekly |
| `nifty50/weekly_expiry_move_table_skip_first_candle.ipynb` | Nifty50 | daily | weekly, first candle skipped |
| `nifty50/weekly_expiry_hourly_move_table.ipynb` | Nifty50 | hourly | weekly |
| `nifty50/weekly_expiry_hourly_move_table_day2_1115_entry.ipynb` | Nifty50 | hourly | weekly, entry at 11:15 on the 2nd session after expiry |
| `nifty50/expiry_two_session_move_by_vix.ipynb` | Nifty50 | hourly | weekly, expiry_day−1 open to expiry_day close, bucketed by India VIX |
| `sensex/expiry_two_session_move_by_vix.ipynb` | Sensex | hourly | weekly, expiry_day−1 open to expiry_day close, bucketed by India VIX |
| `stocks/monthly_expiry_move_table.ipynb` | any F&O stock | daily | monthly |
| `stocks/last_two_weeks_expiry_move_table.ipynb` | any F&O stock | daily | final 14 calendar days before monthly expiry |
| `weekly_monday_friday_move.ipynb` | Nifty50 + Sensex | hourly | calendar Monday–Friday |

The expiry notebooks measure, from the previous expiry's close, the max upside and max downside
reached before the next expiry and the move actually settled at expiry. The hourly and
stock notebooks add a touch-vs-settle ladder: how often a strike was traded through
intra-cycle versus how often it was still breached at expiry. The daily Nifty50 notebooks
and the stock notebook also include a survivability (Abraham Wald-style) outlier view: a
slider sets the percentile band of settled moves, and cycles that settled outside it are
plotted and listed.

Every expiry date is snapped back to the last session that actually traded on or before
it, so a holiday-shifted expiry still anchors on a real closing print.

The `expiry_two_session_move_by_vix.ipynb` pair (Nifty50 and Sensex, identical code paths,
only the parameters cell differs) reduces each expiry to one number — the move from the open
of the session before expiry to the close of expiry — and buckets those moves by the India VIX
level quoted at entry, giving an average absolute move per VIX band alongside the VIX-implied
expectation for the same two sessions (`VIX / √252 × √2 × √(2/π)`). It also reports dispersion
per band, touch-vs-settle rates from the hourly candles inside the window, and the split of the
move across the entry session, the overnight gap and expiry day. Sessions are counted, not
calendar days, so `expiry_day−1` is always the session that actually traded. Buckets are
left-open, right-closed, and India VIX is a Nifty-based quote, so in the Sensex notebook it
stands in as a volatility-regime proxy rather than that index's own implied vol.

The Monday–Friday notebook measures Monday's first hourly open to Friday's last
hourly close, in points and percent, with weekly high/low excursions, summary
statistics and comparison charts for both indices. Missing endpoint candles and
incomplete observed sessions are excluded and listed in an audit; missing middle
weekdays are flagged, with an optional five-session requirement. It exports full
weekly tables to `data/processed/option_selling/weekly_monday_friday/`.

The stock notebook recalculates all daily stock files on Run All and exports combined
and per-stock monthly move CSVs to `data/processed/option_selling/stocks/`. Intraday
files are excluded. Use the **Stock Monthly Moves** dropdowns to select a stock,
expiry year and month. Only completed expiry cycles are shown. Set `SYMBOL` (plus
`SKIP_FIRST_CANDLES`, `STRIKE_DISTANCES`, `SCREEN_DISTANCE`) in the parameters cell
for the remaining analysis sections, or use the dropdown at the bottom for additional
per-stock views. The cross-symbol screen ranks stocks by how often the cycle settled
inside a chosen band.

The last-two-weeks stock notebook measures the final 14 calendar days before each
monthly expiry, using the close on or immediately before expiry minus 14 days as
the base. It keeps the same stock/year/month filters and analysis views, and exports
`last_two_weeks_expiry_moves.csv` and `<symbol>_last_two_weeks_expiry_moves.csv`
files in the same processed folder. Filters refer to the ending expiry; windows
without a base close or a completed expiry are excluded.

## Process Raw JSON Files

Run this after adding or replacing candle JSON files in `data/raw/`:

```bash
python src/visualizer/data.py
```

The command writes CSV files to `data/processed/`. For matching Nifty spot and
futures JSON files, it also writes a merged CSV with futures volume attached.

## Adding Your Own Data

Place CSV files in `data/raw/`, then load them from a notebook:

```python
from pathlib import Path
import pandas as pd

data_path = Path("../data/raw/your_file.csv")
df = pd.read_csv(data_path)
df.head()
```

For the Nifty spot JSON plus futures JSON, load spot OHLC with futures volume:

```python
from pathlib import Path
from visualizer import load_nifty_with_future_volume

data_dir = Path("../data/raw")
df = load_nifty_with_future_volume(
    data_dir / "nifty50_2026-01-01_2026-04-30.json",
    data_dir / "nifty50_future_2026-01-01_2026-04-30.json",
)

df[["timestamp", "open", "high", "low", "close", "volume", "future_volume"]].head()
```
