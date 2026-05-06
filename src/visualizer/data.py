import argparse
import json
from pathlib import Path

import pandas as pd


CANDLE_COLUMNS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "open_interest",
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def load_csv(path: str | Path, parse_dates: list[str] | None = None) -> pd.DataFrame:
    """Load a CSV file with a small amount of notebook-friendly validation."""
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    return pd.read_csv(csv_path, parse_dates=parse_dates)


def load_candle_json(path: str | Path) -> pd.DataFrame:
    """Load an OHLC candle JSON file into a normalized DataFrame."""
    json_path = Path(path)
    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")

    with json_path.open(encoding="utf-8") as file:
        payload = json.load(file)

    candles = payload.get("data", {}).get("candles")
    if candles is None:
        raise ValueError(f"JSON file does not contain data.candles: {json_path}")

    df = pd.DataFrame(candles, columns=CANDLE_COLUMNS)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def load_nifty_with_future_volume(
    nifty_path: str | Path,
    future_path: str | Path,
) -> pd.DataFrame:
    """Load Nifty candles and attach futures volume/open-interest by timestamp."""
    nifty = load_candle_json(nifty_path).rename(
        columns={"volume": "nifty_volume", "open_interest": "nifty_open_interest"}
    )
    future = load_candle_json(future_path)[["timestamp", "volume", "open_interest"]]
    future = future.rename(
        columns={"volume": "future_volume", "open_interest": "future_open_interest"}
    )

    merged = nifty.merge(future, on="timestamp", how="left", validate="one_to_one")
    merged["volume"] = merged["future_volume"]
    return merged


def process_nifty_pairs(
    raw_dir: str | Path = DEFAULT_RAW_DIR,
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR,
) -> list[Path]:
    """Merge matching Nifty spot/future JSON pairs and save processed CSV files."""
    raw_path = Path(raw_dir)
    processed_path = Path(processed_dir)
    processed_path.mkdir(parents=True, exist_ok=True)

    outputs: list[Path] = []
    for nifty_path in sorted(raw_path.glob("nifty50_*.json")):
        if nifty_path.name.startswith("nifty50_future_"):
            continue

        suffix = nifty_path.stem.removeprefix("nifty50_")
        future_path = raw_path / f"nifty50_future_{suffix}.json"
        if not future_path.exists():
            continue

        df = load_nifty_with_future_volume(nifty_path, future_path)
        output_path = processed_path / f"nifty50_with_future_volume_{suffix}.csv"
        df.to_csv(output_path, index=False)
        outputs.append(output_path)

    return outputs


def process_raw_jsons(
    raw_dir: str | Path = DEFAULT_RAW_DIR,
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR,
    include_nifty_merge: bool = True,
) -> list[Path]:
    """Convert raw candle JSON files into processed CSV files."""
    raw_path = Path(raw_dir)
    processed_path = Path(processed_dir)
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw data directory not found: {raw_path}")

    json_paths = sorted(raw_path.glob("*.json"))
    if not json_paths:
        raise FileNotFoundError(f"No JSON files found in: {raw_path}")

    processed_path.mkdir(parents=True, exist_ok=True)

    outputs: list[Path] = []
    for json_path in json_paths:
        df = load_candle_json(json_path)
        output_path = processed_path / f"{json_path.stem}.csv"
        df.to_csv(output_path, index=False)
        outputs.append(output_path)

    if include_nifty_merge:
        outputs.extend(process_nifty_pairs(raw_path, processed_path))

    return outputs


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point for processing raw JSON files."""
    parser = argparse.ArgumentParser(
        description="Convert candle JSON files in data/raw into CSV files in data/processed."
    )
    parser.add_argument(
        "--raw-dir",
        default=DEFAULT_RAW_DIR,
        help="Directory containing raw JSON files.",
    )
    parser.add_argument(
        "--processed-dir",
        default=DEFAULT_PROCESSED_DIR,
        help="Directory where processed CSV files should be written.",
    )
    parser.add_argument(
        "--skip-nifty-merge",
        action="store_true",
        help="Only convert each JSON to CSV; do not create the merged Nifty CSV.",
    )
    args = parser.parse_args(argv)

    outputs = process_raw_jsons(
        raw_dir=args.raw_dir,
        processed_dir=args.processed_dir,
        include_nifty_merge=not args.skip_nifty_merge,
    )

    print(f"Wrote {len(outputs)} processed file(s):")
    for output in outputs:
        print(f"  {output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
