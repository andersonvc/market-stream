#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "postgres" --set=dbname="$DBNAME" --set=dbuser="$DBUSER" --set=dbpass="$DBPASS" <<-EOSQL
    CREATE USER :dbuser;
    ALTER USER :dbuser WITH PASSWORD :'dbpass';
    ALTER USER postgres WITH PASSWORD :'dbpass';
    CREATE DATABASE :dbname;
    GRANT ALL PRIVILEGES ON DATABASE :dbname TO :dbuser;
    ALTER DATABASE :dbname OWNER TO :dbuser;
EOSQL
