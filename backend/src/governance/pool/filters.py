"""Structural filter application logic for the pool builder.

This module implements the apply_structural_filters function that takes a universe
of symbol data and a StructuralFilters configuration, returning symbols that pass
all active filters along with exclusion reasons for rejected symbols.

Functions:
    apply_structural_filters: Apply structural filters to a symbol universe.
"""

from __future__ import annotations

from typing import Any

from src.governance.pool.models import StructuralFilters


def apply_structural_filters(
    universe: list[Any],
    filters: StructuralFilters,
) -> tuple[list[Any], list[tuple[Any, str]]]:
    """Apply structural filters to a universe of symbol data.

    Each symbol is checked against ALL active filters using AND logic.
    A symbol must pass every active filter to be included. For symbols that
    fail, only the FIRST failed filter is recorded as the exclusion reason.

    Args:
        universe: List of symbol data objects with attributes: symbol, sector,
            state_owned_ratio, dividend_yield, avg_dollar_volume, market_cap, price.
        filters: StructuralFilters configuration specifying active filter thresholds.

    Returns:
        A tuple of (passed_symbols, excluded_symbols) where:
            - passed_symbols: List of symbol data objects that passed all filters.
            - excluded_symbols: List of (symbol_data, reason_string) tuples for
              symbols that failed at least one filter.
    """
    if not universe:
        return [], []

    passed: list[Any] = []
    excluded: list[tuple[Any, str]] = []

    for symbol_data in universe:
        reason = _check_filters(symbol_data, filters)
        if reason is None:
            passed.append(symbol_data)
        else:
            excluded.append((symbol_data, reason))

    return passed, excluded


def _check_filters(symbol_data: Any, filters: StructuralFilters) -> str | None:
    """Check a single symbol against all active filters.

    Returns the reason string for the FIRST failed filter, or None if the
    symbol passes all filters.

    Args:
        symbol_data: Symbol data object with filter-relevant attributes.
        filters: StructuralFilters configuration.

    Returns:
        A reason string if the symbol fails a filter, None if it passes all.
    """
    # Check state-owned ratio (exclude if >= threshold, boundary included)
    if filters.exclude_state_owned_ratio_gte is not None:
        if symbol_data.state_owned_ratio >= filters.exclude_state_owned_ratio_gte:
            return (
                f"structural_filter:exclude_state_owned_ratio_gte "
                f"(ratio {symbol_data.state_owned_ratio} >= "
                f"{filters.exclude_state_owned_ratio_gte})"
            )

    # Check dividend yield (exclude if >= threshold, boundary included)
    if filters.exclude_dividend_yield_gte is not None:
        if symbol_data.dividend_yield >= filters.exclude_dividend_yield_gte:
            return (
                f"structural_filter:exclude_dividend_yield_gte "
                f"(yield {symbol_data.dividend_yield} >= "
                f"{filters.exclude_dividend_yield_gte})"
            )

    # Check minimum average dollar volume (exclude if < threshold, boundary passes)
    if filters.min_avg_dollar_volume is not None:
        if symbol_data.avg_dollar_volume < filters.min_avg_dollar_volume:
            return (
                f"structural_filter:min_avg_dollar_volume "
                f"(volume {symbol_data.avg_dollar_volume} < "
                f"{filters.min_avg_dollar_volume})"
            )

    # Check sector exclusion
    if filters.exclude_sectors:
        if symbol_data.sector in filters.exclude_sectors:
            return (
                f"structural_filter:exclude_sectors "
                f"(sector '{symbol_data.sector}' in exclusion list)"
            )

    # Check minimum market cap
    if filters.min_market_cap is not None:
        if symbol_data.market_cap < filters.min_market_cap:
            return (
                f"structural_filter:min_market_cap "
                f"(market_cap {symbol_data.market_cap} < "
                f"{filters.min_market_cap})"
            )

    # Check minimum price
    if filters.min_price is not None:
        if symbol_data.price < filters.min_price:
            return f"structural_filter:min_price (price {symbol_data.price} < {filters.min_price})"

    # Check maximum price
    if filters.max_price is not None:
        if symbol_data.price > filters.max_price:
            return f"structural_filter:max_price (price {symbol_data.price} > {filters.max_price})"

    return None


__all__ = [
    "apply_structural_filters",
]
