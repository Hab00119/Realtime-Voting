#!/bin/bash

# This script creates multiple databases in PostgreSQL
#postgres-init.sh
set -e
set -u

function create_user_and_database() {
    local database=$1
    echo "Creating user and database '$database'"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
        CREATE USER $database WITH PASSWORD '$database';
        CREATE DATABASE $database;
        GRANT ALL PRIVILEGES ON DATABASE $database TO $database;
EOSQL
}

if [ -n "$POSTGRES_MULTIPLE_DATABASES" ]; then
    echo "Multiple database creation requested: $POSTGRES_MULTIPLE_DATABASES"
    for db in $(echo $POSTGRES_MULTIPLE_DATABASES | tr ',' ' '); do
        create_user_and_database $db
    done
    echo "Multiple databases created"
fi

# Create schema and tables for voting_db
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname voting_db <<-EOSQL
    CREATE TABLE IF NOT EXISTS voters (
        voter_id VARCHAR(50) PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        age INTEGER NOT NULL,
        gender VARCHAR(20) NOT NULL,
        state VARCHAR(50) NOT NULL,
        county VARCHAR(50) NOT NULL,
        registration_date TIMESTAMP NOT NULL
    );

    CREATE TABLE IF NOT EXISTS votes (
        vote_id VARCHAR(50) PRIMARY KEY,
        voter_id VARCHAR(50) NOT NULL,
        candidate VARCHAR(100) NOT NULL,
        candidate_image VARCHAR(255),
        timestamp TIMESTAMP NOT NULL,
        polling_station VARCHAR(50) NOT NULL,
        FOREIGN KEY (voter_id) REFERENCES voters(voter_id)
    );

    CREATE INDEX idx_votes_voter_id ON votes(voter_id);
    CREATE INDEX idx_votes_candidate ON votes(candidate);
    CREATE INDEX idx_voters_state ON voters(state);
EOSQL

# Create user for kestra if not using the default 'kestra' user
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname kestra <<-EOSQL
    CREATE USER IF NOT EXISTS kestra WITH PASSWORD 'kestra';
    GRANT ALL PRIVILEGES ON DATABASE kestra TO kestra;
EOSQL