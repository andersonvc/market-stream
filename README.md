# Market-Stream

This is a proof-of-concept for building a low-latency stream processing service on Raspberry-Pi with Docker. The project is deployed via docker-compose and builds a TimescaleDB record store, Grafana dashboard, and async websocket client that pulls market/crypto data from Alpaca. Feed latency is approximately 100ms, but could be massively improved with some simple code improvements.

![Dashboard](https://raw.githubusercontent.com/andersonvc/market-stream/main/docs/grafana_snapshot2.png)

#### Deployment
1) Replace the keys values in the secrets/*.env.placeholder files with your environment secrets/configs/tokens. The Alpaca API token will require you to set up a free account with Alpaca
2) Install Docker and docker-compose on your Raspberry Pi
3) Create a docker volume to match the docker-compose file (e.g. market-data)
4) From the project directory, run ```docker-compose build && docker-compose up -d```
    - The first time I ran the docker-compose script, I changed the ```alpaca-client``` entrypoint to ```"poetry run python /app/main.py reset-database"``` to initialize the database tables. Once the tables are built, change the entrypoint back to ```python /app/main.py start_crypto_client```
5) Once deployed, grafana will start a service on ```<machine_ip>:3000```.