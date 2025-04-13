# Vote simulator
# data_generator/vote_simulator.py
import random
import uuid
import json
import time
import os
import datetime
from kafka import KafkaProducer
from kafka import KafkaConsumer
import threading

# Connect to Kafka
KAFKA_BOOTSTRAP_SERVERS = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
producer = KafkaProducer(
    bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)


consumer = KafkaConsumer(
    'voters',
    bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
    auto_offset_reset='earliest',
    value_deserializer=lambda x: json.loads(x.decode('utf-8'))
)

# Store voter IDs
voter_ids = []

def collect_voters():
    """Collect voter IDs from Kafka stream"""
    global voter_ids
    print("Starting to collect voter IDs...")
    
    for message in consumer:
        voter = message.value
        voter_ids.append(voter["voter_id"])
        if len(voter_ids) % 100 == 0:
            print(f"Collected {len(voter_ids)} voter IDs")

# Start collecting voter IDs in a separate thread
voter_thread = threading.Thread(target=collect_voters)
voter_thread.daemon = True
voter_thread.start()

# Configuration
VOTES_PER_MINUTE = int(os.environ.get('VOTES_PER_MINUTE', 100))
CANDIDATES = ["Candidate A", "Candidate B", "Candidate C", "Candidate D"]
POLLING_STATIONS = ["Station-" + str(i) for i in range(1, 21)]

def generate_vote():
    """Generate a vote with a random voter"""
    if not voter_ids:
        print("No voters available yet. Waiting...")
        time.sleep(5)
        return None
    
    voter_id = random.choice(voter_ids)
    
    return {
        "vote_id": str(uuid.uuid4()),
        "voter_id": voter_id,
        "candidate": random.choice(CANDIDATES),
        "timestamp": datetime.datetime.now().isoformat(),
        "polling_station": random.choice(POLLING_STATIONS)
    }

def simulate_voting():
    """Continuously generate votes at the specified rate"""
    delay_between_votes = 60.0 / VOTES_PER_MINUTE
    
    while True:
        vote = generate_vote()
        if vote:
            producer.send('votes', vote)
            print(f"Vote cast for {vote['candidate']} by voter {vote['voter_id'][:8]}...")
        
        time.sleep(delay_between_votes)

if __name__ == "__main__":
    # Wait a bit for voters to be collected
    time.sleep(10)
    print(f"Starting vote simulation at {VOTES_PER_MINUTE} votes per minute...")
    simulate_voting()