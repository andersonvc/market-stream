#!/bin/bash
set -e 
clickhouse client -n <<-EOSQL
CREATE DATABASE IF NOT EXISTS feature_store;
EOSQL