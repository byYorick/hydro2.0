"""Tests for ML Phase 1 extensions to telemetry-aggregator.

See doc_ai/09_AI_AND_DIGITAL_TWIN/ML_FEATURE_PIPELINE.md §5.1 + Приложение C.
"""
from main import AGG_VERSION_CURRENT, _build_agg_1m_query, _build_agg_1h_query


def test_agg_version_current_is_2():
    """Текущая версия aggregation-формулы должна быть 2 (со std/slope/p10/p90/valid_count)."""
    assert AGG_VERSION_CURRENT == 2


def test_build_agg_1m_query_has_quality_filter_on_ml_fields():
    """ML-поля считаются только по quality='GOOD' через FILTER."""
    sql = _build_agg_1m_query(bucket_expr="time_bucket('1 minute', ts.ts)")

    # value_std, p10, p90, slope_per_min — с FILTER
    assert "STDDEV_SAMP(ts.value) FILTER (WHERE ts.quality = 'GOOD')" in sql
    assert "PERCENTILE_CONT(0.1) WITHIN GROUP (ORDER BY ts.value)\n            FILTER (WHERE ts.quality = 'GOOD')" in sql
    assert "PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY ts.value)\n            FILTER (WHERE ts.quality = 'GOOD')" in sql
    assert "REGR_SLOPE(ts.value, EXTRACT(EPOCH FROM ts.ts) / 60.0)\n            FILTER (WHERE ts.quality = 'GOOD')" in sql
    assert "COUNT(*) FILTER (WHERE ts.quality = 'GOOD')::int AS valid_count" in sql


def test_build_agg_1m_query_keeps_classic_fields_unfiltered():
    """value_avg/min/max/median и sample_count НЕ фильтруются по quality (backward compat)."""
    sql = _build_agg_1m_query(bucket_expr="time_bucket('1 minute', ts.ts)")

    # Нет FILTER у классических полей
    assert "AVG(ts.value)::float AS value_avg" in sql
    assert "COUNT(*)::int AS sample_count" in sql
    # И только ML-поля содержат FILTER
    filter_count = sql.count("FILTER (WHERE ts.quality = 'GOOD')")
    assert filter_count == 5, f"Expected 5 FILTER clauses (std, p10, p90, slope, valid_count), got {filter_count}"


def test_build_agg_1m_query_writes_agg_version_2():
    """В INSERT явно записывается agg_version = 2."""
    sql = _build_agg_1m_query(bucket_expr="time_bucket('1 minute', ts.ts)")
    assert f"{AGG_VERSION_CURRENT} AS agg_version" in sql


def test_build_agg_1m_query_on_conflict_updates_all_ml_fields():
    """ON CONFLICT должен обновлять все новые ML-поля."""
    sql = _build_agg_1m_query(bucket_expr="time_bucket('1 minute', ts.ts)")
    for field in ("value_std", "value_p10", "value_p90", "slope_per_min", "valid_count", "agg_version"):
        assert f"{field}" in sql
        assert f"{field}     = EXCLUDED.{field}" in sql or f"{field}   = EXCLUDED.{field}" in sql or f"{field} = EXCLUDED.{field}" in sql


def test_build_agg_1m_query_uses_bucket_expr():
    """bucket_expr подставляется как для group-by, так и для select."""
    sql_tb = _build_agg_1m_query(bucket_expr="time_bucket('1 minute', ts.ts)")
    sql_dt = _build_agg_1m_query(bucket_expr="date_trunc('minute', ts.ts)")

    assert "time_bucket('1 minute', ts.ts) AS ts" in sql_tb
    assert "date_trunc('minute', ts.ts) AS ts" in sql_dt
    # В оба варианта bucket попадает в GROUP BY
    assert sql_tb.count("time_bucket('1 minute', ts.ts)") >= 2
    assert sql_dt.count("date_trunc('minute', ts.ts)") >= 2


def test_build_agg_1h_query_aggregates_from_1m():
    """1h-запрос читает из telemetry_agg_1m, не из raw samples."""
    sql = _build_agg_1h_query(bucket_expr="time_bucket('1 hour', ts)")
    assert "FROM telemetry_agg_1m" in sql
    assert "FROM telemetry_samples" not in sql


def test_build_agg_1h_query_ml_fields_from_minute_avgs():
    """В 1h std/p10/p90 считаются от value_avg минутных бакетов, slope — как AVG(slope_per_min)."""
    sql = _build_agg_1h_query(bucket_expr="time_bucket('1 hour', ts)")
    assert "STDDEV_SAMP(value_avg)::float AS value_std" in sql
    assert "PERCENTILE_CONT(0.1) WITHIN GROUP (ORDER BY value_avg)::float AS value_p10" in sql
    assert "AVG(slope_per_min)::float AS slope_per_min" in sql
    # valid_count = SUM from 1m
    assert "COALESCE(SUM(valid_count), 0)::int AS valid_count" in sql


def test_build_agg_1h_query_writes_agg_version_2():
    sql = _build_agg_1h_query(bucket_expr="time_bucket('1 hour', ts)")
    assert f"{AGG_VERSION_CURRENT} AS agg_version" in sql
