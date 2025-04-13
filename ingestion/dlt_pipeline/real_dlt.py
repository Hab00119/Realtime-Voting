"""
Real-time DLT pipeline for continuous data ingestion from Kafka to Postgres/BigQuery
"""
import os
import sys
import time
import json
import logging
import signal
import traceback
from kafka import KafkaConsumer, TopicPartition
from dlt.destinations import postgres, bigquery
from datetime import datetime
from uuid import uuid4

#ingestion/dlt_pipeline/real_dlt.py
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('dlt-pipeline')

# Global flag for graceful shutdown
running = True

def signal_handler(sig, frame):
    """Handle shutdown signals"""
    global running
    logger.info("Shutdown signal received, stopping pipeline...")
    running = False

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

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
            logger.info("GCP credentials file not found, using application default credentials")
            return 'bigquery', None
    else:
        # PostgreSQL connection
        pg_host = os.environ.get('POSTGRES_HOST', 'localhost')
        pg_port = os.environ.get('POSTGRES_PORT', '5432')
        pg_db = os.environ.get('POSTGRES_DB', 'voting_db')
        pg_user = os.environ.get('POSTGRES_USER', 'postgres')
        pg_password = os.environ.get('POSTGRES_PASSWORD', 'postgres')
        
        connection_string = f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"
        return 'postgres', connection_string

def create_pipeline(pipeline_name, destination_type, destination_config):
    """Create and configure DLT pipeline"""
    import dlt
    
    # Set the appropriate destination
    if destination_type == 'bigquery':
        dest = bigquery(destination_config)
    else:
        dest = postgres(destination_config)
    
    # Create pipeline with incremental loading
    pipeline = dlt.pipeline(
        pipeline_name=pipeline_name,
        destination=dest,
        dataset_name='public',
    )
    
    return pipeline

def continuous_ingest(pipeline_name, table_name, group_id_prefix):
    """Continuously ingest data from Kafka to the destination"""
    global running
    
    # Get destination configuration
    destination_type, destination_config = get_destination_config()
    logger.info(f"Setting up continuous ingestion with destination: {destination_type}")
    
    # Create DLT pipeline
    import dlt
    pipeline = create_pipeline(pipeline_name, destination_type, destination_config)
    
    # Kafka configuration
    bootstrap_servers = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'localhost:29092')
    topic_type = "VOTES" if table_name.lower() == "votes" else "VOTERS"
    topic = os.environ.get(f'KAFKA_{topic_type}_TOPIC', topic_type.lower())
    #topic = os.environ.get(f'KAFKA_{"VOTES" if "vote" in table_name.lower() else "VOTERS"}_TOPIC', 
    #                      'votes' if 'vote' in table_name.lower() else 'voters')
    
    # Use a consistent group_id for offset tracking between restarts
    # But allow multiple instances with different IDs if needed
    instance_id = os.environ.get('INSTANCE_ID', '')
    group_id = f"{group_id_prefix}-{instance_id}" if instance_id else group_id_prefix
    
    logger.info(f"Starting Kafka consumer for topic '{topic}' with group '{group_id}'")
    
    # Create consumer without timeout to enable continuous processing
    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=[bootstrap_servers],
        auto_offset_reset='earliest',  # Start from earliest unprocessed message
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        group_id=group_id,
        enable_auto_commit=True,  # Automatically commit offsets
        auto_commit_interval_ms=15000,  # Commit every 15 seconds
    )
    
    # Batch size configuration
    batch_size = int(os.environ.get('BATCH_SIZE', '10')) #from 100
    max_batch_interval_seconds = int(os.environ.get('MAX_BATCH_INTERVAL_SECONDS', '100')) #30
    
    logger.info(f"Batch configuration: size={batch_size}, interval={max_batch_interval_seconds}s")
    
    batch_buffer = []
    last_flush_time = time.time()
    
    # Main ingestion loop
    try:
        while running:
            # Poll for messages with a timeout to avoid blocking indefinitely
            messages = consumer.poll(timeout_ms=1000, max_records=batch_size)
            
            current_time = time.time()
            time_since_last_flush = current_time - last_flush_time
            
            if messages:
                # Process received messages
                for tp, msgs in messages.items():
                    for msg in msgs:
                        # Add message to the batch buffer
                        batch_buffer.append(msg.value)
                        
                        # If batch is full, process it
                        if len(batch_buffer) >= batch_size:
                            process_batch(pipeline, batch_buffer, table_name)
                            batch_buffer = []
                            last_flush_time = time.time()
            
            # Also flush if max time has passed since last flush
            if batch_buffer and time_since_last_flush >= max_batch_interval_seconds:
                logger.info(f"Time-based flush after {time_since_last_flush:.1f}s with {len(batch_buffer)} records")
                process_batch(pipeline, batch_buffer, table_name)
                batch_buffer = []
                last_flush_time = time.time()
                
            # Small sleep to prevent CPU spinning when idle
            if not messages:
                time.sleep(0.1)
                
    except Exception as e:
        logger.error(f"Error in continuous ingestion: {str(e)}")
        logger.error(traceback.format_exc())
    finally:
        # Process any remaining records in the buffer
        if batch_buffer:
            logger.info(f"Processing {len(batch_buffer)} remaining records before shutdown")
            process_batch(pipeline, batch_buffer, table_name)
            
        # Clean up resources
        logger.info("Closing Kafka consumer")
        consumer.close()

def process_batch(pipeline, batch, table_name):
    """Process a batch of records with DLT"""
    if not batch:
        return
    
    logger.info(f"Processing batch of {len(batch)} records for table '{table_name}'")
    
    try:
        # Run the pipeline with the batch data
        info = pipeline.run(
            batch,
            table_name=table_name,
            write_disposition='append'
        )
        
        logger.info(f"Successfully loaded batch. Load info: {info}")
        
        # Check for errors
        if hasattr(info, 'load_packages') and info.load_packages:
            if hasattr(info.load_packages, 'failed_rows_count') and info.load_packages.failed_rows_count > 0:
                logger.warning(f"Failed to load {info.load_packages.failed_rows_count} rows")
    except Exception as e:
        logger.error(f"Error processing batch: {str(e)}")
        logger.error(traceback.format_exc())

def test_components():
    """Test basic components before starting continuous ingestion"""
    # Test Kafka connection
    bootstrap_servers = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'localhost:29092')
    logger.info(f"Testing Kafka connection to {bootstrap_servers}")
    
    try:
        consumer = KafkaConsumer(
            bootstrap_servers=[bootstrap_servers],
            group_id='test-group',
            consumer_timeout_ms=5000
        )
        
        topics = consumer.topics()
        logger.info(f"Available Kafka topics: {topics}")
        consumer.close()
        
        # Test database connection
        destination_type, destination_config = get_destination_config()
        if destination_type == 'postgres':
            import psycopg2
            pg_host = os.environ.get('POSTGRES_HOST', 'localhost')
            pg_port = os.environ.get('POSTGRES_PORT', '5432')
            pg_db = os.environ.get('POSTGRES_DB', 'voting_db')
            pg_user = os.environ.get('POSTGRES_USER', 'postgres')
            pg_password = os.environ.get('POSTGRES_PASSWORD', 'postgres')
            
            conn = psycopg2.connect(
                host=pg_host,
                port=pg_port,
                dbname=pg_db,
                user=pg_user,
                password=pg_password
            )
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            conn.close()
            logger.info("PostgreSQL connection test successful")
        
        # Test DLT installation
        import dlt
        logger.info(f"DLT version: {dlt.__version__}")
        
        return True
    except Exception as e:
        logger.error(f"Component tests failed: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def main():
    """Main entry point for the continuous ingestion service"""
    logger.info("Starting real-time DLT ingestion service")
    
    # Test components first
    if not test_components():
        logger.error("Component tests failed. Exiting.")
        return
    
    # Get configuration for which data to ingest
    pipeline_name = os.environ.get('PIPELINE_NAME', 'voting_data')
    ingest_voters = os.environ.get('INGEST_VOTERS', 'true').lower() == 'true'
    ingest_votes = os.environ.get('INGEST_VOTES', 'true').lower() == 'true'
    
    # Start ingestion processes
    if ingest_voters:
        import threading
        pipeline_name = 'voters'
        voters_thread = threading.Thread(
            target=continuous_ingest,
            args=('voters_pipeline', 'voters', 'dlt-voters-group'),
            daemon=True
        )
        voters_thread.start()
        logger.info("Started voters ingestion thread")
    
    if ingest_votes:
        import threading
        pipeline_name = 'votes'
        votes_thread = threading.Thread(
            target=continuous_ingest,
            args=('votes_pipeline', 'votes', 'dlt-votes-group'),
            daemon=True
        )
        votes_thread.start()
        logger.info("Started votes ingestion thread")
    
    # Keep main thread alive to allow the ingestion to continue
    logger.info("Ingestion service is running. Press Ctrl+C to stop.")
    try:
        while running:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, stopping service...")
    
    # Wait for a clean shutdown
    logger.info("Waiting for ingestion to complete (max 30 seconds)...")
    shutdown_start = time.time()
    while time.time() - shutdown_start < 30 and any(t.is_alive() for t in threading.enumerate() if t != threading.current_thread()):
        time.sleep(1)
    
    logger.info("DLT ingestion service stopped")

if __name__ == "__main__":
    main()