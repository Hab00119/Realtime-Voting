# Realtime-Voting

# Optional: Override the default number of voters (1000)
docker-compose up -d
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092

export VOTERS_COUNT=5000

python -m data_generator.voter_generator or docker-compose run --rm data-generator python -m data_generator.voter_generator

# Optional: Override the default rate (100 votes/minute)
export VOTES_PER_MINUTE=300

python -m data_generator.vote_simulator or docker-compose run --rm data-generator python -m data_generator.vote_simulator


or
docker-compose logs kafka
docker-compose logs zookeeper
docker-compose logs data-generator

docker-compose up -d zookeeper kafka
# Wait a few seconds for services to initialize
docker-compose up data-generator
docker-compose up vote-simulator

sudo mkdir -p /home/codespace/.dlt/pipelines
sudo chown -R $(whoami) /home/codespace/.dlt

make up
docker rmi $(docker images)