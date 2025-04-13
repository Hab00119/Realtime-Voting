import random
import uuid
import json
import time
import os
import datetime
import requests
from kafka import KafkaProducer
from faker import Faker
import atexit
#vote_gen2
# Initialize Faker
fake = Faker()

KAFKA_BOOTSTRAP_SERVERS = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'localhost:29092')
producer = KafkaProducer(
    bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

# Register cleanup to gracefully flush and close the producer
atexit.register(lambda: shutdown_producer(producer))

# Configuration
VOTERS_COUNT = int(os.environ.get('VOTERS_COUNT', 1000))
US_STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming"
]

COUNTIES_BY_STATE = {
    state: [fake.city() for _ in range(5)] for state in US_STATES
}

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

def generate_voter():
    """Generate a simulated voter with demographic information"""
    voter_id = str(uuid.uuid4())
    state = random.choice(US_STATES)
    gender = random.choice(["Male", "Female", "Non-binary", "Other"])
    
    return {
        "voter_id": voter_id,
        "name": fake.name(),
        "age": random.randint(18, 95),
        "gender": gender,
        "state": state,
        "county": random.choice(COUNTIES_BY_STATE[state]),
        "registration_date": fake.date_time_between(
            start_date="-5y", end_date="now"
        ).isoformat()
    }

def generate_voters_batch():
    """Generate a batch of voters"""
    print(f"Generating {VOTERS_COUNT} voters...")
    voters = []
    
    for _ in range(VOTERS_COUNT):
        voter = generate_voter()
        voters.append(voter)
        # Send to Kafka
        producer.send('voters', voter)
    
    print(f"Generated {len(voters)} voters")
    return voters

def shutdown_producer(producer):
    """Flush and close the Kafka producer gracefully"""
    print("Flushing Kafka producer before exit...")
    producer.flush(timeout=10)
    producer.close(timeout=10)

# Main function to run when script is executed directly
if __name__ == "__main__":
    # Run once to generate initial voters
    voters = generate_voters_batch()