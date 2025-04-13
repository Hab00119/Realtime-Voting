import os
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.table import StreamTableEnvironment, EnvironmentSettings
from pyflink.table.descriptors import Schema, Kafka, Json
from pyflink.table.window import Tumble

# Environment setup
env = StreamExecutionEnvironment.get_execution_environment()
env.set_parallelism(4)  # Adjust based on your cluster size
settings = EnvironmentSettings.new_instance().in_streaming_mode().use_blink_planner().build()
t_env = StreamTableEnvironment.create(env, environment_settings=settings)

# Add required JAR files
kafka_jar = os.path.join(os.path.abspath('.'), 'lib', 'flink-sql-connector-kafka_2.11-1.13.0.jar')
json_jar = os.path.join(os.path.abspath('.'), 'lib', 'flink-json-1.13.0.jar')
t_env.get_config().get_configuration().set_string("pipeline.jars", f"file://{kafka_jar};file://{json_jar}")

# Define source table (Kafka)
t_env.execute_sql("""
    CREATE TABLE vote_stream (
        vote_id STRING,
        candidate_id STRING,
        voter_id STRING,
        polling_station STRING,
        timestamp TIMESTAMP(3),
        WATERMARK FOR timestamp AS timestamp - INTERVAL '5' SECOND
    ) WITH (
        'connector' = 'kafka',
        'topic' = 'votes',
        'properties.bootstrap.servers' = 'kafka:9092',
        'properties.group.id' = 'vote-processor',
        'format' = 'json',
        'scan.startup.mode' = 'latest-offset'
    )
""")

# Define sink table (BigQuery)
t_env.execute_sql("""
    CREATE TABLE vote_counts (
        candidate_id STRING,
        polling_station STRING,
        window_start TIMESTAMP(3),
        window_end TIMESTAMP(3),
        vote_count BIGINT
    ) WITH (
        'connector' = 'bigquery',
        'project' = 'your-gcp-project',
        'dataset' = 'voting_data',
        'table' = 'real_time_vote_counts',
        'authentication.type' = 'service_account',
        'authentication.service_account_file' = '/path/to/service_account.json'
    )
""")

# Real-time vote counting with 5-minute tumbling windows
t_env.execute_sql("""
    INSERT INTO vote_counts
    SELECT
        candidate_id,
        polling_station,
        window_start,
        window_end,
        COUNT(*) AS vote_count
    FROM TABLE(
        TUMBLE(TABLE vote_stream, DESCRIPTOR(timestamp), INTERVAL '5' MINUTES)
    )
    GROUP BY candidate_id, polling_station, window_start, window_end
""")

# Execute the job
t_env.execute("Real-time Vote Counter")