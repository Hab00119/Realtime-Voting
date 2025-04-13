import random
import uuid
import json
import time
import os
import datetime
import requests
from kafka import KafkaProducer
from kafka import KafkaConsumer
import threading

#real_voter_simulator
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

# Store voter IDs
available_voter_ids = []
voted_voter_ids = set()  # Track voters who have already voted
voter_count_lock = threading.Lock()  # Lock for thread-safe operations on voter lists

def collect_voters():
    """Collect voter IDs from Kafka stream"""
    global available_voter_ids
    print("Starting to collect voter IDs...")
    
    for message in consumer:
        voter = message.value
        voter_id = voter["voter_id"]
        
        with voter_count_lock:
            # Only add to available voters if they haven't voted yet
            if voter_id not in voted_voter_ids:
                available_voter_ids.append(voter_id)
                if len(available_voter_ids) % 100 == 0:
                    print(f"Collected {len(available_voter_ids)} available voter IDs")

# Start collecting voter IDs in a separate thread
voter_thread = threading.Thread(target=collect_voters)
voter_thread.daemon = True
voter_thread.start()

# Configuration
VOTES_PER_MINUTE = int(os.environ.get('VOTES_PER_MINUTE', 100))

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

# Get candidate images
candidate_images = fetch_candidate_images(4)

CANDIDATES = [
    {"name": "Candidate A", "image_url": candidate_images[0]},
    {"name": "Candidate B", "image_url": candidate_images[1]},
    {"name": "Candidate C", "image_url": candidate_images[2]},
    {"name": "Candidate D", "image_url": candidate_images[3]}
]
POLLING_STATIONS = ["Station-" + str(i) for i in range(1, 21)]

def generate_vote():
    """Generate a vote with a random voter who hasn't voted yet"""
    with voter_count_lock:
        if not available_voter_ids:
            print("No available voters left or waiting for more. Waiting...")
            return None
        
        # Select a random voter from the available voters
        voter_index = random.randrange(len(available_voter_ids))
        voter_id = available_voter_ids.pop(voter_index)
        
        # Add to voted set to keep track
        voted_voter_ids.add(voter_id)
    
    candidate = random.choice(CANDIDATES)
    
    return {
        "vote_id": str(uuid.uuid4()),
        "voter_id": voter_id,
        "candidate": candidate["name"],
        "candidate_image": candidate["image_url"],
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
            with voter_count_lock:
                voters_left = len(available_voter_ids)
                total_voted = len(voted_voter_ids)
            
            print(f"Vote cast for {vote['candidate']} by voter {vote['voter_id'][:8]}... "
                  f"({total_voted} voters have voted, {voters_left} voters remaining)")
        else:
            # If we're waiting for more voters, slow down the polling
            time.sleep(5)
            continue
        
        time.sleep(delay_between_votes)

if __name__ == "__main__":
    # Wait a bit for voters to be collected
    time.sleep(10)
    print(f"Starting vote simulation at {VOTES_PER_MINUTE} votes per minute...")
    
    # Print initial voter stats
    with voter_count_lock:
        print(f"Initial voter pool: {len(available_voter_ids)} available voters")
    
    simulate_voting()


#this works with: python data_generator/real_vote_simulator.py