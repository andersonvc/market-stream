#!/bin/bash
schemaregistry="http://schema-registry:8084"
tmpfile=$(mktemp)

echo "Waiting for Schema Registry to be ready"
until $(curl --output /dev/null --silent --head --fail ${schemaregistry}/subjects); do
    printf '.'
    sleep 5
done

echo "Registering schemas"
topic=cryptoQuote
export SCHEMA=$(cat /avro-store/cryptoQuote.avsc)
echo '{"schemaType":"AVRO", "schema":""}' | jq --arg schema "$SCHEMA" '.schema = $schema' > $tmpfile
curl --retry 10 -X POST -H "Content-Type: application/vnd.schemaregistry.v1+json" \
    --data @$tmpfile ${schemaregistry}/subjects/${topic}-value/versions

topic=cryptoTrade
export SCHEMA=$(cat /avro-store/cryptoTrade.avsc)
echo '{"schemaType":"AVRO", "schema":""}' | jq --arg schema "$SCHEMA" '.schema = $schema' > $tmpfile
curl --retry 10 -X POST -H "Content-Type: application/vnd.schemaregistry.v1+json" \
    --data @$tmpfile ${schemaregistry}/subjects/${topic}-value/versions

topic=cryptoOrderbook
export SCHEMA=$(cat /avro-store/cryptoOrderbook.avsc)
echo '{"schemaType":"AVRO", "schema":""}' | jq --arg schema "$SCHEMA" '.schema = $schema' > $tmpfile
curl --retry 10 -X POST -H "Content-Type: application/vnd.schemaregistry.v1+json" \
    --data @$tmpfile ${schemaregistry}/subjects/${topic}-value/versions


topic=orderbookChange
export SCHEMA=$(cat /avro-store/orderbookChange.avsc)
echo '{"schemaType":"AVRO", "schema":""}' | jq --arg schema "$SCHEMA" '.schema = $schema' > $tmpfile
curl --retry 10 -X POST -H "Content-Type: application/vnd.schemaregistry.v1+json" \
    --data @$tmpfile ${schemaregistry}/subjects/${topic}-value/versions
