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
