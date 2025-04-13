#Makefile
.PHONY: up down start-infra start-processing start-apps start-monitoring logs clean

# Start everything in the correct order with proper delays
up:
	@echo "Starting infrastructure (ZooKeeper, Kafka, PostgreSQL)..."
	docker-compose up -d zookeeper kafka postgres
	@echo "Waiting for infrastructure to initialize (20 seconds)..."
	@sleep 20
	
	@echo "Starting monitoring tools (pgweb)..."
	docker-compose up -d pgweb

	@echo "Starting data generator..."
	docker-compose up -d data-generator
	@echo "Waiting for data generation (5 seconds)..."
	@sleep 5
	
	@echo "Starting vote simulator..."
	docker-compose up -d vote-simulator
	
	@echo "Starting processing services (dlt-pipeline, kestra)..."
	docker-compose up -d dlt-pipeline
	@echo "Waiting for processing services (10 seconds)..."
	@sleep 10
	
	
	@echo "All services started successfully!"
	@echo "Run 'make logs' to see the logs"

# Start only infrastructure components
start-infra:
	@echo "Starting ZooKeeper, Kafka, and PostgreSQL..."
	docker-compose up -d zookeeper kafka postgres
	@echo "Waiting for infrastructure to initialize (20 seconds)..."
	@sleep 20
	@echo "Infrastructure is ready!"

# Start only processing components
start-processing:
	@echo "Starting DLT pipeline and Kestra workflow server..."
	docker-compose up -d dlt-pipeline kestra
	@echo "Processing services started successfully!"

# Start only application components
start-apps:
	@echo "Starting data generator..."
	docker-compose up -d data-generator
	@echo "Waiting for data generation (5 seconds)..."
	@sleep 5
	@echo "Starting vote simulator..."
	docker-compose up -d vote-simulator
	@echo "Applications started successfully!"

# Start only monitoring tools
start-monitoring:
	@echo "Starting monitoring tools (pgweb)..."
	docker-compose up -d pgweb
	@echo "Monitoring tools started successfully!"

# Show logs for all services
logs:
	docker-compose logs -f

# Show logs for specific service group
logs-infra:
	docker-compose logs -f zookeeper kafka postgres

logs-processing:
	docker-compose logs -f dlt-pipeline kestra

logs-apps:
	docker-compose logs -f data-generator vote-simulator

logs-monitoring:
	docker-compose logs -f pgweb

# Stop and remove all containers
down:
	docker-compose down

# Remove volumes and any created data
clean:
	docker-compose down -v
	@echo "Cleaned up all containers and volumes"