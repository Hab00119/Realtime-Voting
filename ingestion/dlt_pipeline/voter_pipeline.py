import dlt
from kafka import KafkaConsumer
import json
import time
import os

def kafka_voters_source():
    """Source function that reads voters from Kafka"""
    consumer = KafkaConsumer(
        'voters',
        bootstrap_servers=['kafka:9092'],
        auto_offset_reset='earliest',
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        group_id='dlt-voter-group'
    )
    
    for message in consumer:
        yield message.value

def kafka_votes_source():
    """Source function that reads votes from Kafka"""
    consumer = KafkaConsumer(
        'votes',
        bootstrap_servers=['kafka:9092'],
        auto_offset_reset='earliest',
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        group_id='dlt-votes-group'
    )
    
    for message in consumer:
        yield message.value

def get_destination_config():
    """Get destination configuration based on storage preference"""
    storage_preference = os.environ.get('STORAGE_PREFERENCE', 'postgres').upper()
    
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
            print("GCP credentials file not found, using application default credentials")
            return 'bigquery', None
    else:
        # PostgreSQL connection
        pg_host = os.environ.get('POSTGRES_HOST', 'postgres')
        pg_port = os.environ.get('POSTGRES_PORT', '5432')
        pg_db = os.environ.get('POSTGRES_DB', 'voting_db')
        pg_user = os.environ.get('POSTGRES_USER', 'postgres')
        pg_password = os.environ.get('POSTGRES_PASSWORD', 'postgres')
        
        connection_string = f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"
        return 'postgres', connection_string

def run_pipeline(pipeline_name, source_function, table_name):
    """Generic function to run a pipeline with the configured destination"""
    destination_type, destination_config = get_destination_config()
    
    if destination_type == 'bigquery':
        if destination_config:
            # Using provided GCP credentials
            from dlt.destinations import bigquery
            pipeline = dlt.pipeline(
                pipeline_name=pipeline_name,
                destination=bigquery(credentials=destination_config),
                dataset_name='voting_system',
                dev_mode=True  # This forces DLT to recreate all internal state tables
            )
        else:
            # Using application default credentials
            pipeline = dlt.pipeline(
                pipeline_name=pipeline_name,
                destination='bigquery',
                dataset_name='voting_system',
                dev_mode=True  # This forces DLT to recreate all internal state tables
            )
    else:
        # PostgreSQL destination with connection string
        from dlt.destinations import postgres
        pipeline = dlt.pipeline(
            pipeline_name=pipeline_name,
            destination=postgres(destination_config),
            dataset_name='public',  # Use 'public' schema or whatever schema your tables are in
            dev_mode=True  # This forces DLT to recreate all internal state tables
        )
    
    # Run the pipeline with existing table configuration
    info = pipeline.run(
        source_function(),
        table_name=table_name,
        write_disposition='append',
        #merge_key=None,  # Set this to your primary key if you want upsert behavior
        #if_exists='append'  # 'append' will add to existing tables, 'replace' would drop and recreate
    )
    
    print(f"Loaded {info.load_package.count} records to {table_name}")
    return info

def run_voter_pipeline():
    """Run the DLT pipeline for voters"""
    return run_pipeline('voters', kafka_voters_source, 'voters')

def run_votes_pipeline():
    """Run the DLT pipeline for votes"""
    return run_pipeline('votes', kafka_votes_source, 'votes')

# Run both pipelines in separate threads
import threading

if __name__ == "__main__":
    # Start voter pipeline
    voter_thread = threading.Thread(target=run_voter_pipeline)
    voter_thread.daemon = True
    voter_thread.start()
    
    # Start votes pipeline
    votes_thread = threading.Thread(target=run_votes_pipeline)
    votes_thread.daemon = True
    votes_thread.start()
    
    # Keep the main thread running
    try:
        while True:
            time.sleep(60)
            print("DLT pipelines running...")
    except KeyboardInterrupt:
        print("Shutting down DLT pipelines...")