import random
import uuid
import json
import time
import os
import datetime
import requests
from kafka import KafkaProducer, KafkaConsumer
import threading

# Connect to Kafka
KAFKA_BOOTSTRAP_SERVERS = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'localhost:29092')
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

voted_voter_ids = set()
voter_count_lock = threading.Lock()

# Configuration
VOTES_PER_MINUTE = int(os.environ.get('VOTES_PER_MINUTE', 100))
delay_between_votes = 60.0 / VOTES_PER_MINUTE

# Fetch candidate images from RandomUser API
def fetch_candidate_images(count=4):
    try:
        response = requests.get(f"https://randomuser.me/api/?results={count}")
        data = response.json()
        return [user['picture']['large'] for user in data['results']]
    except Exception as e:
        print(f"Error fetching candidate images: {e}")
        return ["https://randomuser.me/api/portraits/men/1.jpg",
                "https://randomuser.me/api/portraits/women/1.jpg",
                "https://randomuser.me/api/portraits/men/2.jpg",
                "https://randomuser.me/api/portraits/women/2.jpg"]

candidate_images = fetch_candidate_images(4)

CANDIDATES = [
    {"name": "Candidate A", "image_url": candidate_images[0]},
    {"name": "Candidate B", "image_url": candidate_images[1]},
    {"name": "Candidate C", "image_url": candidate_images[2]},
    {"name": "Candidate D", "image_url": candidate_images[3]}
]
POLLING_STATIONS = ["Station-" + str(i) for i in range(1, 21)]

def cast_vote(voter_id):
    candidate = random.choice(CANDIDATES)
    vote = {
        "vote_id": str(uuid.uuid4()),
        "voter_id": voter_id,
        "candidate": candidate["name"],
        "candidate_image": candidate["image_url"],
        "timestamp": datetime.datetime.now().isoformat(),
        "polling_station": random.choice(POLLING_STATIONS)
    }
    producer.send('votes', vote)
    print(f"Vote cast for {vote['candidate']} by voter {voter_id[:8]}")

def collect_and_vote():
    """Consume voters and cast votes immediately (only once per voter)"""
    print("Starting to collect voters and cast votes...")
    for message in consumer:
        voter = message.value
        voter_id = voter["voter_id"]

        with voter_count_lock:
            if voter_id in voted_voter_ids:
                print(f"Voter {voter_id[:8]} has already voted. Skipping...")
                continue
            voted_voter_ids.add(voter_id)

        cast_vote(voter_id)
        time.sleep(delay_between_votes)

if __name__ == "__main__":
    print(f"Starting vote simulation at {VOTES_PER_MINUTE} votes per minute...")
    collect_and_vote()
