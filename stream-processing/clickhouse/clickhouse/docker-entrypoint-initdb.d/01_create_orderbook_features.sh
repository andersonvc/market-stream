#!/bin/bash
set -e 
clickhouse client -n <<-EOSQL
CREATE TABLE IF NOT EXISTS feature_store.orderbook (symbol String, ts Datetime, spread Float64, midpoint Float64, highest_bid Float64, lowest_ask Float64, bid_vol_1pct Float64, ask_vol_1pct Float64, imbalance_1pct Float64, bid_vol_3pct Float64, ask_vol_3pct Float64, imbalance_3pct Float64, bid_vol_5pct Float64, ask_vol_5pct Float64, imbalance_5pct Float64, bid_vol_10pct Float64, ask_vol_10pct Float64, imbalance_10pct Float64, bid_vol_15pct Float64, ask_vol_15pct Float64, imbalance_15pct Float64, bid_vol_20pct Float64, ask_vol_20pct Float64, imbalance_20pct Float64, bid_vol_30pct Float64, ask_vol_30pct Float64, imbalance_30pct Float64) ENGINE = MergeTree ORDER BY (symbol, ts);
EOSQL