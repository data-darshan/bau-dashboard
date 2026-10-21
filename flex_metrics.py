"""Pure helpers for the Flex dashboard visualisations.

The report stores one official working-hours percentage (8 Hrs+ Adherence)
and count buckets for the remaining working-hours categories. The dashboard
presents the same four percentage metrics as Attendance, deriving the three
missing percentages from Total Punched for the same site/date.
"""
from __future__ import annotations

import re

import polars as pl

FLEX_WORKING_OPTIONS = [
    "8 Hrs + Adherence",
    "5 to 8 Hrs Adherence",
    "<5 Hrs Adherence",
    "Single Punch %",
]

_SOURCE_PERCENT_METRIC = "8 Hrs+ Adherence"
_DERIVED_COUNT_METRICS = {
    "5 to 8 Hrs Adherence": "5 to 8 Hours",
    "<5 Hrs Adherence": "Less than 5 Hours",
    "Single Punch %": "Single Punch",
}


def flex_source_metrics(display_metric: str) -> list[str]:
    """Return the stored summary metrics needed for one displayed Flex metric."""
    if display_metric == "8 Hrs + Adherence":
        return [_SOURCE_PERCENT_METRIC]
    if display_metric in _DERIVED_COUNT_METRICS:
        return [_DERIVED_COUNT_METRICS[display_metric], "Total Punched"]
    raise ValueError(f"Unsupported Flex working-hours metric: {display_metric}")


def derive_flex_working_metric(frame: pl.DataFrame, display_metric: str) -> pl.DataFrame:
    """Return Attendance-style Flex percentages from a queried summary frame.

    * 8 Hrs + Adherence uses the report's official percentage.
    * The other three are count / Total Punched * 100 for the same site/date.
    * A missing/zero denominator is treated as unknown and omitted, never 0%.
    """
    if display_metric not in FLEX_WORKING_OPTIONS:
        raise ValueError(f"Unsupported Flex working-hours metric: {display_metric}")
    if frame.is_empty():
        return frame

    if display_metric == "8 Hrs + Adherence":
        return (
            frame.filter(pl.col("metric") == _SOURCE_PERCENT_METRIC)
            .with_columns(pl.lit(display_metric).alias("metric"))
        )

    count_metric = _DERIVED_COUNT_METRICS[display_metric]
    index_cols = [
        "section", "data_date", "site_key", "site", "facility_type", "region"
    ]
    subset = frame.filter(pl.col("metric").is_in([count_metric, "Total Punched"]))
    if subset.is_empty():
        return subset

    pivoted = subset.pivot(
        on="metric", index=index_cols, values="value", aggregate_function="first"
    )
    for column in (count_metric, "Total Punched"):
        if column not in pivoted.columns:
            pivoted = pivoted.with_columns(pl.lit(None, dtype=pl.Float64).alias(column))

    return (
        pivoted.with_columns(
            pl.when(pl.col("Total Punched").fill_null(0) > 0)
            .then(
                (pl.col(count_metric).fill_null(0) / pl.col("Total Punched") * 100.0)
                .clip(upper_bound=100.0)
            )
            .otherwise(None)
            .alias("value")
        )
        .filter(pl.col("value").is_not_null())
        .with_columns(
            pl.lit(display_metric).alias("metric"),
            pl.lit("percent").alias("unit"),
        )
        .select(index_cols + ["metric", "value", "unit"])
        .sort(["data_date", "site"])
    )


def flex_working_on_used_days(working: pl.DataFrame, flex_usage: pl.DataFrame) -> pl.DataFrame:
    """Keep only observed working-hours percentages with Flex actually used.

    Match on both normalized site_key and report date. A positive "Total Flex
    Used" at a *different* site on the same date cannot make this site's
    100% compliance point valid. Dates with zero, null or missing usage are
    dropped entirely; the trend connects the remaining observations in date
    order. No percentages or denominators are changed.
    """
    if working.is_empty() or flex_usage.is_empty():
        return working.head(0)
    active_pairs = (
        flex_usage.filter(
            (pl.col("metric") == "Total Flex Used") &
            (pl.col("value").is_not_null()) &
            (pl.col("value") > 0)
        )
        .select(["data_date", "site_key"])
        .unique()
    )
    return (
        working.join(active_pairs, on=["data_date", "site_key"], how="inner")
        .sort(["site", "data_date"])
    )


def _normalize_hex(value: str) -> str:
    text = str(value or "").strip().upper()
    if not re.fullmatch(r"#[0-9A-F]{6}", text):
        raise ValueError(f"Invalid site colour: {value!r}")
    return text


def blend_with_white(base_hex: str, white_fraction: float) -> str:
    """Blend a site colour towards white while preserving its hue identity."""
    base = _normalize_hex(base_hex)
    amount = min(1.0, max(0.0, float(white_fraction)))
    rgb = [int(base[i:i + 2], 16) for i in (1, 3, 5)]
    mixed = [round(channel * (1.0 - amount) + 255 * amount) for channel in rgb]
    return "#" + "".join(f"{channel:02X}" for channel in mixed)


def flex_site_shades(base_hex: str) -> tuple[str, str, str]:
    """Light/medium/dark shades for the three Flex-used states of one site."""
    base = _normalize_hex(base_hex)
    return blend_with_white(base, 0.66), blend_with_white(base, 0.36), base
