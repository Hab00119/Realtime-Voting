terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.0"
    }
    postgresql = {
      source  = "cyrilgdn/postgresql"
      version = "~> 1.15.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.10.0"
    }
  }
  
  backend "gcs" {
    bucket = "voting-system-terraform-state"
    prefix = "state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

provider "postgresql" {
  host     = google_sql_database_instance.voting_db.private_ip_address
  port     = 5432
  username = var.db_username
  password = var.db_password
  sslmode  = "require"
}

provider "kubernetes" {
  config_path = "~/.kube/config"
}

# GCP Resources
resource "google_project_service" "services" {
  for_each = toset([
    "compute.googleapis.com",
    "bigquery.googleapis.com",
    "dataflow.googleapis.com",
    "pubsub.googleapis.com",
    "cloudsql.googleapis.com",
    "container.googleapis.com",
    "iam.googleapis.com",
    "storage.googleapis.com"
  ])
  
  project = var.project_id
  service = each.value
  
  disable_on_destroy = false
}

# VPC Network
resource "google_compute_network" "vpc" {
  name                    = "voting-system-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.services["compute.googleapis.com"]]
}

resource "google_compute_subnetwork" "subnet" {
  name          = "voting-subnet"
  ip_cidr_range = "10.0.0.0/16"
  region        = var.region
  network       = google_compute_network.vpc.id
  
  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.1.0.0/16"
  }
  
  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.2.0.0/20"
  }
}

# GKE Cluster
resource "google_container_cluster" "primary" {
  name     = "voting-system-cluster"
  location = var.zone
  
  network    = google_compute_network.vpc.name
  subnetwork = google_compute_subnetwork.subnet.name
  
  remove_default_node_pool = true
  initial_node_count       = 1
  
  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }
  
  depends_on = [google_project_service.services["container.googleapis.com"]]
}

resource "google_container_node_pool" "primary_nodes" {
  name       = "voting-system-node-pool"
  location   = var.zone
  cluster    = google_container_cluster.primary.name
  node_count = var.gke_num_nodes
  
  node_config {
    machine_type = "e2-standard-4"
    disk_size_gb = 100
    disk_type    = "pd-standard"
    
    # Google recommends custom service accounts with least privilege
    service_account = google_service_account.gke_sa.email
    
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
    
    labels = {
      app = "voting-system"
    }
    
    tags = ["voting-system", "gke-node"]
  }
}

# Service Account for GKE
resource "google_service_account" "gke_sa" {
  account_id   = "voting-system-gke-sa"
  display_name = "GKE Service Account"
  depends_on   = [google_project_service.services["iam.googleapis.com"]]
}

# Grant necessary roles
resource "google_project_iam_member" "gke_sa_roles" {
  for_each = toset([
    "roles/storage.admin",
    "roles/bigquery.admin",
    "roles/dataflow.admin",
    "roles/pubsub.admin"
  ])
  
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.gke_sa.email}"
}

# Cloud Storage Buckets
resource "google_storage_bucket" "data_lake" {
  name          = "${var.project_id}-data-lake"
  location      = var.region
  force_destroy = true
  
  uniform_bucket_level_access = true
  
  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }
  
  depends_on = [google_project_service.services["storage.googleapis.com"]]
}

# BigQuery Dataset
resource "google_bigquery_dataset" "voting_dataset" {
  dataset_id                  = "voting_data"
  friendly_name               = "Voting System Dataset"
  description                 = "Dataset for storing voting system data"
  location                    = var.region
  delete_contents_on_destroy  = true
  
  depends_on = [google_project_service.services["bigquery.googleapis.com"]]
}

# BigQuery Tables
resource "google_bigquery_table" "voters" {
  dataset_id = google_bigquery_dataset.voting_dataset.dataset_id
  table_id   = "voters"
  
  schema = <<EOF
[
  {
    "name": "voter_id",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Unique identifier for the voter"
  },
  {
    "name": "name",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Voter's name"
  },
  {
    "name": "age",
    "type": "INTEGER",
    "mode": "REQUIRED",
    "description": "Voter's age"
  },
  {
    "name": "district",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Voter's district"
  },
  {
    "name": "registration_date",
    "type": "TIMESTAMP",
    "mode": "REQUIRED",
    "description": "When the voter registered"
  }
]
EOF
}

resource "google_bigquery_table" "votes" {
  dataset_id = google_bigquery_dataset.voting_dataset.dataset_id
  table_id   = "votes"
  
  schema = <<EOF
[
  {
    "name": "vote_id",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Unique identifier for the vote"
  },
  {
    "name": "voter_id",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Reference to the voter"
  },
  {
    "name": "candidate",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Candidate voted for"
  },
  {
    "name": "timestamp",
    "type": "TIMESTAMP",
    "mode": "REQUIRED",
    "description": "When the vote was cast"
  },
  {
    "name": "district",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "District where the vote was cast"
  }
]
EOF
}

# Cloud SQL (PostgreSQL)
resource "google_sql_database_instance" "voting_db" {
  name             = "voting-system-db"
  database_version = "POSTGRES_13"
  region           = var.region
  deletion_protection = false
  
  settings {
    tier = "db-g1-small"
    
    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
    }
    
    backup_configuration {
      enabled            = true
      start_time         = "02:00"
      binary_log_enabled = false
    }
  }
  
  depends_on = [
    google_project_service.services["cloudsql.googleapis.com"],
    google_compute_network.vpc
  ]
}

resource "google_sql_database" "voting_database" {
  name     = "voting_system"
  instance = google_sql_database_instance.voting_db.name
}

resource "google_sql_user" "db_user" {
  name     = var.db_username
  instance = google_sql_database_instance.voting_db.name
  password = var.db_password
}

# Pub/Sub for streaming
resource "google_pubsub_topic" "votes_topic" {
  name = "votes-topic"
  
  depends_on = [google_project_service.services["pubsub.googleapis.com"]]
}

resource "google_pubsub_subscription" "votes_subscription" {
  name  = "votes-subscription"
  topic = google_pubsub_topic.votes_topic.name
  
  ack_deadline_seconds = 20
  
  # Configure retry policy
  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"  # 10 minutes
  }
  
  # Expire after 7 days
  message_retention_duration = "604800s"
  
  # Configure dead-letter topic if needed
  # dead_letter_policy {
  #   dead_letter_topic     = google_pubsub_topic.votes_dlq.id
  #   max_delivery_attempts = 5
  # }
}

# Dataflow related service account
resource "google_service_account" "dataflow_sa" {
  account_id   = "dataflow-service-account"
  display_name = "Dataflow Service Account"
}

resource "google_project_iam_member" "dataflow_roles" {
  for_each = toset([
    "roles/dataflow.worker",
    "roles/bigquery.dataEditor",
    "roles/storage.objectAdmin"
  ])
  
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.dataflow_sa.email}"
}

# IAM bindings for Kestra workflow engine
resource "google_service_account" "kestra_sa" {
  account_id   = "kestra-service-account"
  display_name = "Kestra Workflow Service Account"
}

resource "google_project_iam_member" "kestra_roles" {
  for_each = toset([
    "roles/bigquery.jobUser",
    "roles/bigquery.dataEditor",
    "roles/dataflow.admin",
    "roles/storage.objectAdmin"
  ])
  
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.kestra_sa.email}"
}

# Outputs
output "gke_cluster_name" {
  value = google_container_cluster.primary.name
}

output "kubernetes_endpoint" {
  value     = google_container_cluster.primary.endpoint
  sensitive = true
}

output "bigquery_dataset" {
  value = google_bigquery_dataset.voting_dataset.dataset_id
}

output "postgres_connection_name" {
  value = google_sql_database_instance.voting_db.connection_name
}

output "data_lake_bucket" {
  value = google_storage_bucket.data_lake.name
}

output "votes_pubsub_topic" {
  value = google_pubsub_topic.votes_topic.name
}