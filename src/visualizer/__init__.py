"""Helpers for the chart visualizer notebooks."""

from .data import (
    load_candle_json,
    load_csv,
    load_nifty_with_future_volume,
    process_nifty_pairs,
    process_raw_jsons,
)

__all__ = [
    "load_candle_json",
    "load_csv",
    "load_nifty_with_future_volume",
    "process_nifty_pairs",
    "process_raw_jsons",
    "save_figure",
    "set_chart_style",
]


def __getattr__(name: str):
    if name in {"save_figure", "set_chart_style"}:
        from .charts import save_figure, set_chart_style

        globals()["save_figure"] = save_figure
        globals()["set_chart_style"] = set_chart_style
        return globals()[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
