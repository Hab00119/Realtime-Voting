#!/usr/bin/env python
"""
DLT Pipeline for processing Kafka voter and vote data
"""
import dlt
from kafka import KafkaConsumer
import json
import time
import os
import sys
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('dlt_pipeline')

def kafka_voters_source():
    """Source function that reads voters from Kafka"""
    logger.info("Starting voter source function")
    bootstrap_servers = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
    logger.info(f"Connecting to Kafka at {bootstrap_servers}")
    
    try:
        consumer = KafkaConsumer(
            'voters',
            bootstrap_servers=[bootstrap_servers],
            auto_offset_reset='earliest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            group_id='dlt-voter-group',
            request_timeout_ms=30000,  # 30 seconds timeout
            session_timeout_ms=10000   # 10 seconds timeout
        )
        logger.info("Successfully connected to Kafka consumers")
        
        for message in consumer:
            logger.info(f"Processing voter message: {message.value.get('voter_id', 'unknown')}")
            yield message.value
    except Exception as e:
        logger.error(f"Error in voter source: {str(e)}")
        # Don't raise, just log and continue
        time.sleep(5)  # Wait before retrying
        return

def kafka_votes_source():
    """Source function that reads votes from Kafka"""
    logger.info("Starting votes source function")
    bootstrap_servers = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
    
    try:
        consumer = KafkaConsumer(
            'votes',
            bootstrap_servers=[bootstrap_servers],
            auto_offset_reset='earliest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            group_id='dlt-votes-group',
            request_timeout_ms=30000,  # 30 seconds timeout
            session_timeout_ms=10000   # 10 seconds timeout
        )
        
        for message in consumer:
            logger.info(f"Processing vote message: {message.value.get('vote_id', 'unknown')}")
            yield message.value
    except Exception as e:
        logger.error(f"Error in votes source: {str(e)}")
        # Don't raise, just log and continue
        time.sleep(5)  # Wait before retrying
        return

def get_destination_config():
    """Get destination configuration based on storage preference"""
    storage_preference = os.environ.get('STORAGE_PREFERENCE', 'postgres').upper()
    logger.info(f"Setting up destination with storage preference: {storage_preference}")
    
    if storage_preference == 'GCP':
        # Check if GCP credentials file path is provided
        gcp_creds_path = os.environ.get('GCP_CREDENTIALS_PATH')
        
        if gcp_creds_path and os.path.exists(gcp_creds_path):
            # Load GCP credentials from file
            with open(gcp_creds_path, 'r') as f:
                gcp_creds = json.load(f)
            return 'bigquery', gcp_creds
        else:
            # If credentials file is not provided, try to use application default credentials
            logger.warning("GCP credentials file not found, using application default credentials")
            return 'bigquery', None
    else:
        # PostgreSQL connection
        pg_host = os.environ.get('POSTGRES_HOST', 'postgres')
        pg_port = os.environ.get('POSTGRES_PORT', '5432')
        pg_db = os.environ.get('POSTGRES_DB', 'voting_db')
        pg_user = os.environ.get('POSTGRES_USER', 'postgres')
        pg_password = os.environ.get('POSTGRES_PASSWORD', 'postgres')
        
        connection_string = f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"
        logger.info(f"Using PostgreSQL connection to {pg_host}:{pg_port}/{pg_db}")
        return 'postgres', connection_string

def run_pipeline(pipeline_name, source_function, table_name):
    """Generic function to run a pipeline with the configured destination"""
    logger.info(f"Starting pipeline: {pipeline_name} for table: {table_name}")
    destination_type, destination_config = get_destination_config()
    
    try:
        if destination_type == 'bigquery':
            if destination_config:
                # Using provided GCP credentials
                from dlt.destinations import bigquery
                pipeline = dlt.pipeline(
                    pipeline_name=pipeline_name,
                    destination=bigquery(credentials=destination_config),
                    dataset_name='voting_system',
                    dev_mode=True
                )
            else:
                # Using application default credentials
                pipeline = dlt.pipeline(
                    pipeline_name=pipeline_name,
                    destination='bigquery',
                    dataset_name='voting_system',
                    dev_mode=True
                )
        else:
            # PostgreSQL destination with connection string
            from dlt.destinations import postgres
            pipeline = dlt.pipeline(
                pipeline_name=pipeline_name,
                destination=postgres(destination_config),
                dataset_name='public',
                dev_mode=True
            )
        
        logger.info(f"Pipeline {pipeline_name} initialized successfully")
        
        # Run the pipeline with existing table configuration
        info = pipeline.run(
            source_function(),
            table_name=table_name,
            write_disposition='append',
        )
        
        logger.info(f"Loaded {info.load_package.count} records to {table_name}")
        return info
    
    except Exception as e:
        logger.error(f"Error running pipeline {pipeline_name}: {str(e)}")
        # Continue with other pipelines
        return None

def run_voter_pipeline():
    """Run the DLT pipeline for voters"""
    logger.info("Starting voter pipeline")
    while True:
        try:
            info = run_pipeline('voters', kafka_voters_source, 'voters')
            if info and info.load_package.count > 0:
                logger.info(f"Successfully loaded {info.load_package.count} voters")
            else:
                logger.warning("No voters loaded, waiting before retry")
                time.sleep(10)  # Wait before retry
        except Exception as e:
            logger.error(f"Error in voter pipeline: {str(e)}")
            time.sleep(10)  # Wait before retry

def run_votes_pipeline():
    """Run the DLT pipeline for votes"""
    logger.info("Starting votes pipeline")
    while True:
        try:
            info = run_pipeline('votes', kafka_votes_source, 'votes')
            if info and info.load_package.count > 0:
                logger.info(f"Successfully loaded {info.load_package.count} votes")
            else:
                logger.warning("No votes loaded, waiting before retry")
                time.sleep(10)  # Wait before retry
        except Exception as e:
            logger.error(f"Error in votes pipeline: {str(e)}")
            time.sleep(10)  # Wait before retry

if __name__ == "__main__":
    logger.info("DLT pipeline starting...")
    
    # Try to make sure Kafka is ready
    for i in range(5):
        try:
            bootstrap_servers = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
            test_consumer = KafkaConsumer(
                bootstrap_servers=[bootstrap_servers],
                request_timeout_ms=5000
            )
            test_consumer.close()
            logger.info("Kafka connection successful")
            break
        except Exception as e:
            logger.warning(f"Kafka not ready yet (attempt {i+1}/5): {str(e)}")
            time.sleep(10)
    
    # Import threading here to avoid issues if the module can't be loaded
    import threading
    
    # Start voter pipeline
    voter_thread = threading.Thread(target=run_voter_pipeline)
    voter_thread.daemon = True
    voter_thread.start()
    logger.info("Voter pipeline thread started")
    
    # Start votes pipeline
    votes_thread = threading.Thread(target=run_votes_pipeline)
    votes_thread.daemon = True
    votes_thread.start()
    logger.info("Votes pipeline thread started")
    
    # Keep the main thread running
    try:
        while True:
            logger.info("DLT pipelines running...")
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Shutting down DLT pipelines...")
        sys.exit(0)