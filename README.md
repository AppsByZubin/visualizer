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
