# Fixtures das CQs (CQFIX) no provider google — gerado por bo.cqfix.build; não editar.
# Cada seção é uma fixture (FX-...) e só ela; o conjunto de endereços de cada uma está em
# expected_answers.json. Valores reais (conta, região, projeto) nunca entram: vêm das variáveis
# de contexto, ligadas pelo runner do DEP. Variáveis fx_* sem valor são entradas simbólicas de
# fixtures incompletas, de propósito.

terraform {
  required_version = "= 1.15.8"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "= 8.9.0"
    }
  }
}

provider "google" {
  project = var.project
  region  = var.location_1
  default_labels = {
    bo_run    = var.run_id
    bo_module = "cqfix"
  }
}

variable "run_id" {
  type        = string
  description = "identificador curto da execução (prefixo de nomes e rótulo bo_run); ligado pelo runner"
  validation {
    condition     = can(regex("^[a-z][a-z0-9]{2,11}$", var.run_id))
    error_message = "run_id: 3 a 12 caracteres, minúsculas e dígitos."
  }
}

variable "location_1" {
  type        = string
  description = "localização l1 das fixtures (região); ligada pelo runner"
}

variable "location_2" {
  type        = string
  description = "localização l2, distinta de l1; ligada pelo runner"
}

variable "project" {
  type        = string
  description = "projeto sandbox (nunca um id real gravado aqui); ligado pelo runner"
}

# ==== FX-CIS-01-C (CQ-CIS-01, conforming): NOT_APPLICABLE — o provider google não configura o segundo fator das contas humanas (verificação em duas etapas fica no console do Workspace/Cloud Identity, fora do Terraform)

# ==== FX-CIS-01-N (CQ-CIS-01, nonconforming): NOT_APPLICABLE — o provider google não configura o segundo fator das contas humanas (verificação em duas etapas fica no console do Workspace/Cloud Identity, fora do Terraform)

# ==== FX-CIS-01-I (CQ-CIS-01, incomplete): NOT_APPLICABLE — o provider google não configura o segundo fator das contas humanas (verificação em duas etapas fica no console do Workspace/Cloud Identity, fora do Terraform)

# ==== FX-CIS-02-C (CQ-CIS-02, conforming)

resource "google_service_account" "fx_cis_02_c_p1" {
  account_id   = "${var.run_id}-fx-cis-02-c-p1"
  display_name = "${var.run_id} FX-CIS-02-C"
}

resource "google_service_account_key" "fx_cis_02_c_k1" {
  service_account_id = google_service_account.fx_cis_02_c_p1.name
}

# ==== FX-CIS-02-N (CQ-CIS-02, nonconforming)

resource "google_service_account" "fx_cis_02_n_p1" {
  account_id   = "${var.run_id}-fx-cis-02-n-p1"
  display_name = "${var.run_id} FX-CIS-02-N"
}

resource "google_service_account_key" "fx_cis_02_n_k1" {
  service_account_id = google_service_account.fx_cis_02_n_p1.name
}

# ==== FX-CIS-02-I (CQ-CIS-02, incomplete)

resource "google_service_account" "fx_cis_02_i_p1" {
  account_id   = "${var.run_id}-fx-cis-02-i-p1"
  display_name = "${var.run_id} FX-CIS-02-I"
}

resource "google_service_account_key" "fx_cis_02_i_k1" {
  service_account_id = google_service_account.fx_cis_02_i_p1.name
}

# ==== FX-CIS-03-C (CQ-CIS-03, conforming)

resource "google_kms_key_ring" "fx_cis_03_c_x_ring" {
  name     = "${var.run_id}-fx-cis-03-c-ring"
  location = var.location_1
}

resource "google_kms_crypto_key" "fx_cis_03_c_k1" {
  name                       = "${var.run_id}-fx-cis-03-c-k1"
  key_ring                   = google_kms_key_ring.fx_cis_03_c_x_ring.id
  destroy_scheduled_duration = "86400s"
  rotation_period            = "7776000s"
}

# ==== FX-CIS-03-N (CQ-CIS-03, nonconforming)

resource "google_kms_key_ring" "fx_cis_03_n_x_ring" {
  name     = "${var.run_id}-fx-cis-03-n-ring"
  location = var.location_1
}

resource "google_kms_crypto_key" "fx_cis_03_n_k1" {
  name                       = "${var.run_id}-fx-cis-03-n-k1"
  key_ring                   = google_kms_key_ring.fx_cis_03_n_x_ring.id
  destroy_scheduled_duration = "86400s"
}

# ==== FX-CIS-03-I (CQ-CIS-03, incomplete)

variable "fx_cis_03_i_rotation_period" {
  type        = string
  description = "entrada simbólica da fixture FX-CIS-03-I; sem valor de propósito"
}

resource "google_kms_key_ring" "fx_cis_03_i_x_ring" {
  name     = "${var.run_id}-fx-cis-03-i-ring"
  location = var.location_1
}

resource "google_kms_crypto_key" "fx_cis_03_i_k1" {
  name                       = "${var.run_id}-fx-cis-03-i-k1"
  key_ring                   = google_kms_key_ring.fx_cis_03_i_x_ring.id
  destroy_scheduled_duration = "86400s"
  rotation_period            = var.fx_cis_03_i_rotation_period
}

# ==== FX-CIS-04-C (CQ-CIS-04, conforming)

resource "google_compute_network" "fx_cis_04_c_x_net" {
  name                    = "${var.run_id}-fx-cis-04-c-x-net"
  auto_create_subnetworks = false
}

resource "google_compute_firewall" "fx_cis_04_c_r1" {
  name          = "${var.run_id}-fx-cis-04-c-r1"
  network       = google_compute_network.fx_cis_04_c_x_net.id
  direction     = "INGRESS"
  priority      = 1000
  source_ranges = ["203.0.113.0/24"]
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# ==== FX-CIS-04-N (CQ-CIS-04, nonconforming)

resource "google_compute_network" "fx_cis_04_n_x_net" {
  name                    = "${var.run_id}-fx-cis-04-n-x-net"
  auto_create_subnetworks = false
}

resource "google_compute_firewall" "fx_cis_04_n_r1" {
  name          = "${var.run_id}-fx-cis-04-n-r1"
  network       = google_compute_network.fx_cis_04_n_x_net.id
  direction     = "INGRESS"
  priority      = 1000
  source_ranges = ["0.0.0.0/0"]
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# ==== FX-CIS-04-I (CQ-CIS-04, incomplete)

variable "fx_cis_04_i_source_cidr" {
  type        = string
  description = "entrada simbólica da fixture FX-CIS-04-I; sem valor de propósito"
}

resource "google_compute_network" "fx_cis_04_i_x_net" {
  name                    = "${var.run_id}-fx-cis-04-i-x-net"
  auto_create_subnetworks = false
}

resource "google_compute_firewall" "fx_cis_04_i_r1" {
  name          = "${var.run_id}-fx-cis-04-i-r1"
  network       = google_compute_network.fx_cis_04_i_x_net.id
  direction     = "INGRESS"
  priority      = 1000
  source_ranges = [var.fx_cis_04_i_source_cidr]
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# ==== FX-CIS-05-C (CQ-CIS-05, conforming)

resource "google_compute_network" "fx_cis_05_c_x_net" {
  name                    = "${var.run_id}-fx-cis-05-c-x-net"
  auto_create_subnetworks = false
}

resource "google_compute_firewall" "fx_cis_05_c_r1" {
  name          = "${var.run_id}-fx-cis-05-c-r1"
  network       = google_compute_network.fx_cis_05_c_x_net.id
  direction     = "INGRESS"
  priority      = 1000
  source_ranges = ["203.0.113.0/24"]
  allow {
    protocol = "tcp"
    ports    = ["3389"]
  }
}

# ==== FX-CIS-05-N (CQ-CIS-05, nonconforming)

resource "google_compute_network" "fx_cis_05_n_x_net" {
  name                    = "${var.run_id}-fx-cis-05-n-x-net"
  auto_create_subnetworks = false
}

resource "google_compute_firewall" "fx_cis_05_n_r1" {
  name          = "${var.run_id}-fx-cis-05-n-r1"
  network       = google_compute_network.fx_cis_05_n_x_net.id
  direction     = "INGRESS"
  priority      = 1000
  source_ranges = ["0.0.0.0/0"]
  allow {
    protocol = "tcp"
    ports    = ["3389"]
  }
}

# ==== FX-CIS-05-I (CQ-CIS-05, incomplete)

variable "fx_cis_05_i_source_cidr" {
  type        = string
  description = "entrada simbólica da fixture FX-CIS-05-I; sem valor de propósito"
}

resource "google_compute_network" "fx_cis_05_i_x_net" {
  name                    = "${var.run_id}-fx-cis-05-i-x-net"
  auto_create_subnetworks = false
}

resource "google_compute_firewall" "fx_cis_05_i_r1" {
  name          = "${var.run_id}-fx-cis-05-i-r1"
  network       = google_compute_network.fx_cis_05_i_x_net.id
  direction     = "INGRESS"
  priority      = 1000
  source_ranges = [var.fx_cis_05_i_source_cidr]
  allow {
    protocol = "tcp"
    ports    = ["3389"]
  }
}

# ==== FX-CIS-06-C (CQ-CIS-06, conforming)

resource "google_compute_network" "fx_cis_06_c_vn1" {
  name                    = "${var.run_id}-fx-cis-06-c-vn1"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "fx_cis_06_c_sa" {
  name          = "${var.run_id}-fx-cis-06-c-sa"
  network       = google_compute_network.fx_cis_06_c_vn1.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
  log_config {
    aggregation_interval = "INTERVAL_10_MIN"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

# ==== FX-CIS-06-N (CQ-CIS-06, nonconforming)

resource "google_compute_network" "fx_cis_06_n_vn1" {
  name                    = "${var.run_id}-fx-cis-06-n-vn1"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "fx_cis_06_n_sa" {
  name          = "${var.run_id}-fx-cis-06-n-sa"
  network       = google_compute_network.fx_cis_06_n_vn1.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

# ==== FX-CIS-06-I (CQ-CIS-06, incomplete)

variable "fx_cis_06_i_flow_log_enabled" {
  type        = bool
  description = "entrada simbólica da fixture FX-CIS-06-I; sem valor de propósito"
}

resource "google_compute_network" "fx_cis_06_i_vn1" {
  name                    = "${var.run_id}-fx-cis-06-i-vn1"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "fx_cis_06_i_sa" {
  name          = "${var.run_id}-fx-cis-06-i-sa"
  network       = google_compute_network.fx_cis_06_i_vn1.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
  dynamic "log_config" {
    for_each = var.fx_cis_06_i_flow_log_enabled ? [1] : []
    content {
      aggregation_interval = "INTERVAL_10_MIN"
      flow_sampling        = 0.5
      metadata             = "INCLUDE_ALL_METADATA"
    }
  }
}

# ==== FX-CIS-07-C (CQ-CIS-07, conforming)

resource "google_pubsub_topic" "fx_cis_07_c_t1" {
  name = "${var.run_id}-fx-cis-07-c-t1"
}

resource "google_monitoring_notification_channel" "fx_cis_07_c_x_channel" {
  display_name = "${var.run_id} FX-CIS-07-C"
  type         = "pubsub"
  labels = {
    topic = google_pubsub_topic.fx_cis_07_c_t1.id
  }
}

resource "google_logging_metric" "fx_cis_07_c_x_metric" {
  name   = "${var.run_id}-fx-cis-07-c-metric"
  filter = "resource.type=\"gce_firewall_rule\" AND (protoPayload.methodName:\"compute.firewalls.patch\" OR protoPayload.methodName:\"compute.firewalls.insert\" OR protoPayload.methodName:\"compute.firewalls.delete\")"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "fx_cis_07_c_al1" {
  display_name          = "${var.run_id} FX-CIS-07-C"
  combiner              = "OR"
  notification_channels = [google_monitoring_notification_channel.fx_cis_07_c_x_channel.id]
  conditions {
    display_name = "evento"
    condition_threshold {
      filter          = "resource.type = \"global\" AND metric.type = \"logging.googleapis.com/user/${google_logging_metric.fx_cis_07_c_x_metric.name}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_COUNT"
      }
    }
  }
}

# ==== FX-CIS-07-N (CQ-CIS-07, nonconforming)

resource "google_pubsub_topic" "fx_cis_07_n_t1" {
  name = "${var.run_id}-fx-cis-07-n-t1"
}

resource "google_monitoring_notification_channel" "fx_cis_07_n_x_channel" {
  display_name = "${var.run_id} FX-CIS-07-N"
  type         = "pubsub"
  labels = {
    topic = google_pubsub_topic.fx_cis_07_n_t1.id
  }
}

resource "google_logging_metric" "fx_cis_07_n_x_metric" {
  name   = "${var.run_id}-fx-cis-07-n-metric"
  filter = "resource.type=\"gce_route\" AND (protoPayload.methodName:\"compute.routes.delete\" OR protoPayload.methodName:\"compute.routes.insert\")"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "fx_cis_07_n_al1" {
  display_name          = "${var.run_id} FX-CIS-07-N"
  combiner              = "OR"
  notification_channels = [google_monitoring_notification_channel.fx_cis_07_n_x_channel.id]
  conditions {
    display_name = "evento"
    condition_threshold {
      filter          = "resource.type = \"global\" AND metric.type = \"logging.googleapis.com/user/${google_logging_metric.fx_cis_07_n_x_metric.name}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_COUNT"
      }
    }
  }
}

# ==== FX-CIS-07-I (CQ-CIS-07, incomplete)

variable "fx_cis_07_i_log_filter" {
  type        = string
  description = "entrada simbólica da fixture FX-CIS-07-I; sem valor de propósito"
}

resource "google_pubsub_topic" "fx_cis_07_i_t1" {
  name = "${var.run_id}-fx-cis-07-i-t1"
}

resource "google_monitoring_notification_channel" "fx_cis_07_i_x_channel" {
  display_name = "${var.run_id} FX-CIS-07-I"
  type         = "pubsub"
  labels = {
    topic = google_pubsub_topic.fx_cis_07_i_t1.id
  }
}

resource "google_logging_metric" "fx_cis_07_i_x_metric" {
  name   = "${var.run_id}-fx-cis-07-i-metric"
  filter = var.fx_cis_07_i_log_filter
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "fx_cis_07_i_al1" {
  display_name          = "${var.run_id} FX-CIS-07-I"
  combiner              = "OR"
  notification_channels = [google_monitoring_notification_channel.fx_cis_07_i_x_channel.id]
  conditions {
    display_name = "evento"
    condition_threshold {
      filter          = "resource.type = \"global\" AND metric.type = \"logging.googleapis.com/user/${google_logging_metric.fx_cis_07_i_x_metric.name}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_COUNT"
      }
    }
  }
}

# ==== FX-CIS-08-C (CQ-CIS-08, conforming)

resource "google_storage_bucket" "fx_cis_08_c_c1" {
  name                        = "${var.run_id}-fx-cis-08-c-c1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
}

# ==== FX-CIS-08-N (CQ-CIS-08, nonconforming)

resource "google_storage_bucket" "fx_cis_08_n_c1" {
  name                        = "${var.run_id}-fx-cis-08-n-c1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
  public_access_prevention    = "inherited"
}

resource "google_storage_bucket_iam_member" "fx_cis_08_n_k1" {
  bucket = google_storage_bucket.fx_cis_08_n_c1.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# ==== FX-CIS-08-I (CQ-CIS-08, incomplete)

variable "fx_cis_08_i_public_access_prevention" {
  type        = string
  description = "entrada simbólica da fixture FX-CIS-08-I; sem valor de propósito"
}

resource "google_storage_bucket" "fx_cis_08_i_c1" {
  name                        = "${var.run_id}-fx-cis-08-i-c1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
  public_access_prevention    = var.fx_cis_08_i_public_access_prevention
}

# ==== FX-IDL-01-C (CQ-IDL-01, conforming)

resource "google_storage_bucket" "fx_idl_01_c_c1" {
  name                        = "${var.run_id}-fx-idl-01-c-c1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
  versioning {
    enabled = true
  }
}

# ==== FX-IDL-01-N (CQ-IDL-01, nonconforming)

resource "google_storage_bucket" "fx_idl_01_n_c2" {
  name                        = "${var.run_id}-fx-idl-01-n-c2"
  location                    = var.location_2
  force_destroy               = true
  uniform_bucket_level_access = true
}

# ==== FX-IDL-01-I (CQ-IDL-01, incomplete)

resource "google_storage_bucket" "fx_idl_01_i_c1" {
  name                        = "${var.run_id}-fx-idl-01-i-c1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
  storage_class               = "NEARLINE"
}

# ==== FX-IDL-02-C (CQ-IDL-02, conforming)

resource "google_compute_network" "fx_idl_02_c_x_net" {
  name                    = "${var.run_id}-fx-idl-02-c-x-net"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "fx_idl_02_c_c1" {
  name          = "${var.run_id}-fx-idl-02-c-data"
  network       = google_compute_network.fx_idl_02_c_x_net.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

resource "google_compute_subnetwork" "fx_idl_02_c_c2" {
  name          = "${var.run_id}-fx-idl-02-c-data"
  network       = google_compute_network.fx_idl_02_c_x_net.id
  ip_cidr_range = "10.20.2.0/24"
  region        = var.location_2
}

# ==== FX-IDL-02-N (CQ-IDL-02, nonconforming)

resource "google_compute_network" "fx_idl_02_n_x_net" {
  name                    = "${var.run_id}-fx-idl-02-n-x-net"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "fx_idl_02_n_c1" {
  name          = "${var.run_id}-fx-idl-02-n-data"
  network       = google_compute_network.fx_idl_02_n_x_net.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

data "google_compute_subnetwork" "fx_idl_02_n_c2" {
  name       = "${var.run_id}-fx-idl-02-n-data"
  region     = var.location_1
  depends_on = [google_compute_subnetwork.fx_idl_02_n_c1]
}

# ==== FX-IDL-02-I (CQ-IDL-02, incomplete)

variable "fx_idl_02_i_c2_region" {
  type        = string
  description = "entrada simbólica da fixture FX-IDL-02-I; sem valor de propósito"
}

resource "google_compute_network" "fx_idl_02_i_x_net" {
  name                    = "${var.run_id}-fx-idl-02-i-x-net"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "fx_idl_02_i_c1" {
  name          = "${var.run_id}-fx-idl-02-i-data"
  network       = google_compute_network.fx_idl_02_i_x_net.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

data "google_compute_subnetwork" "fx_idl_02_i_c2" {
  name   = "${var.run_id}-fx-idl-02-i-data"
  region = var.fx_idl_02_i_c2_region
}

# ==== FX-IDL-03-C (CQ-IDL-03, conforming)

resource "google_service_account" "fx_idl_03_c_p1" {
  account_id   = "${var.run_id}-fx-idl-03-c-p1"
  display_name = "${var.run_id} FX-IDL-03-C"
}

resource "google_project_iam_custom_role" "fx_idl_03_c_ps1" {
  role_id     = "${var.run_id}_fx_idl_03_c_ps1"
  title       = "${var.run_id} FX-IDL-03-C"
  permissions = ["storage.objects.get"]
}

resource "google_project_iam_member" "fx_idl_03_c_a1" {
  project = var.project
  role    = google_project_iam_custom_role.fx_idl_03_c_ps1.id
  member  = "serviceAccount:${google_service_account.fx_idl_03_c_p1.email}"
}

# ==== FX-IDL-03-N (CQ-IDL-03, nonconforming)

resource "google_storage_bucket" "fx_idl_03_n_c1" {
  name                        = "${var.run_id}-fx-idl-03-n-c1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
}

# ==== FX-IDL-03-I (CQ-IDL-03, incomplete)

resource "google_storage_bucket" "fx_idl_03_i_c1" {
  name                        = "${var.run_id}-fx-idl-03-i-c1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
  retention_policy {
    retention_period = 86400
  }
}

# ==== FX-IDL-04-C (CQ-IDL-04, conforming)

resource "google_compute_network" "fx_idl_04_c_x_net" {
  name                    = "${var.run_id}-fx-idl-04-c-x-net"
  auto_create_subnetworks = false
}

resource "google_compute_firewall" "fx_idl_04_c_rs1" {
  name          = "${var.run_id}-fx-idl-04-c-rs1"
  network       = google_compute_network.fx_idl_04_c_x_net.id
  direction     = "INGRESS"
  source_ranges = ["203.0.113.0/24"]
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
  allow {
    protocol = "tcp"
    ports    = ["443"]
  }
}

# ==== FX-IDL-04-N (CQ-IDL-04, nonconforming)

resource "google_compute_network" "fx_idl_04_n_x_net" {
  name                    = "${var.run_id}-fx-idl-04-n-x-net"
  auto_create_subnetworks = false
}

resource "google_compute_firewall" "fx_idl_04_n_rs1" {
  name          = "${var.run_id}-fx-idl-04-n-rs1"
  network       = google_compute_network.fx_idl_04_n_x_net.id
  direction     = "INGRESS"
  source_ranges = ["203.0.113.0/24"]
  allow {
    protocol = "tcp"
    ports    = ["8443"]
  }
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# ==== FX-IDL-04-I (CQ-IDL-04, incomplete)

variable "fx_idl_04_i_r1_port" {
  type        = string
  description = "entrada simbólica da fixture FX-IDL-04-I; sem valor de propósito"
}

resource "google_compute_network" "fx_idl_04_i_x_net" {
  name                    = "${var.run_id}-fx-idl-04-i-x-net"
  auto_create_subnetworks = false
}

resource "google_compute_firewall" "fx_idl_04_i_rs1" {
  name          = "${var.run_id}-fx-idl-04-i-rs1"
  network       = google_compute_network.fx_idl_04_i_x_net.id
  direction     = "INGRESS"
  source_ranges = ["203.0.113.0/24"]
  allow {
    protocol = "tcp"
    ports    = [var.fx_idl_04_i_r1_port]
  }
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# ==== FX-CMP-01-C (CQ-CMP-01, conforming)

resource "google_compute_network" "fx_cmp_01_c_vn1" {
  name                    = "${var.run_id}-fx-cmp-01-c-vn1"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "fx_cmp_01_c_sa" {
  name          = "${var.run_id}-fx-cmp-01-c-sa"
  network       = google_compute_network.fx_cmp_01_c_vn1.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

resource "google_compute_instance" "fx_cmp_01_c_vm1" {
  name         = "${var.run_id}-fx-cmp-01-c-vm1"
  machine_type = "e2-micro"
  zone         = "${var.location_1}-a"
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.fx_cmp_01_c_sa.id
  }
}

# ==== FX-CMP-01-N (CQ-CMP-01, nonconforming)

resource "google_compute_network" "fx_cmp_01_n_vn1" {
  name                    = "${var.run_id}-fx-cmp-01-n-vn1"
  auto_create_subnetworks = false
}

resource "google_compute_instance" "fx_cmp_01_n_vm1" {
  name         = "${var.run_id}-fx-cmp-01-n-vm1"
  machine_type = "e2-micro"
  zone         = "${var.location_1}-a"
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }
  network_interface {
    subnetwork = "fx-missing-subnet"
  }
}

# ==== FX-CMP-01-I (CQ-CMP-01, incomplete)

variable "fx_cmp_01_i_subnetwork" {
  type        = string
  description = "entrada simbólica da fixture FX-CMP-01-I; sem valor de propósito"
}

resource "google_compute_instance" "fx_cmp_01_i_vm1" {
  name         = "${var.run_id}-fx-cmp-01-i-vm1"
  machine_type = "e2-micro"
  zone         = "${var.location_1}-a"
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }
  network_interface {
    subnetwork = var.fx_cmp_01_i_subnetwork
  }
}

# ==== FX-CMP-02-C (CQ-CMP-02, conforming)

resource "google_compute_network" "fx_cmp_02_c_x_net_a" {
  name                    = "${var.run_id}-fx-cmp-02-c-x-net-a"
  auto_create_subnetworks = false
}

resource "google_compute_network" "fx_cmp_02_c_x_net_b" {
  name                    = "${var.run_id}-fx-cmp-02-c-netb"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "fx_cmp_02_c_x_sub_a" {
  name          = "${var.run_id}-fx-cmp-02-c-x-sub-a"
  network       = google_compute_network.fx_cmp_02_c_x_net_a.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

resource "google_compute_subnetwork" "fx_cmp_02_c_x_sub_b" {
  name          = "${var.run_id}-fx-cmp-02-c-subb"
  network       = google_compute_network.fx_cmp_02_c_x_net_b.id
  ip_cidr_range = "10.21.1.0/24"
  region        = var.location_1
}

resource "google_compute_instance" "fx_cmp_02_c_vm1" {
  name         = "${var.run_id}-fx-cmp-02-c-vm1"
  machine_type = "e2-micro"
  zone         = "${var.location_1}-a"
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.fx_cmp_02_c_x_sub_a.id
  }
  network_interface {
    subnetwork = google_compute_subnetwork.fx_cmp_02_c_x_sub_b.id
  }
}

# ==== FX-CMP-02-N (CQ-CMP-02, nonconforming)

resource "google_compute_network" "fx_cmp_02_n_x_net_a" {
  name                    = "${var.run_id}-fx-cmp-02-n-x-net-a"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "fx_cmp_02_n_x_sub_a" {
  name          = "${var.run_id}-fx-cmp-02-n-x-sub-a"
  network       = google_compute_network.fx_cmp_02_n_x_net_a.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

resource "google_compute_instance" "fx_cmp_02_n_vm1" {
  name         = "${var.run_id}-fx-cmp-02-n-vm1"
  machine_type = "e2-micro"
  zone         = "${var.location_1}-a"
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.fx_cmp_02_n_x_sub_a.id
  }
}

# ==== FX-CMP-02-I (CQ-CMP-02, incomplete)

variable "fx_cmp_02_i_extra_interfaces" {
  type        = list(string)
  description = "entrada simbólica da fixture FX-CMP-02-I; sem valor de propósito"
}

resource "google_compute_network" "fx_cmp_02_i_x_net_a" {
  name                    = "${var.run_id}-fx-cmp-02-i-x-net-a"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "fx_cmp_02_i_x_sub_a" {
  name          = "${var.run_id}-fx-cmp-02-i-x-sub-a"
  network       = google_compute_network.fx_cmp_02_i_x_net_a.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

resource "google_compute_instance" "fx_cmp_02_i_vm1" {
  name         = "${var.run_id}-fx-cmp-02-i-vm1"
  machine_type = "e2-micro"
  zone         = "${var.location_1}-a"
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.fx_cmp_02_i_x_sub_a.id
  }
  dynamic "network_interface" {
    for_each = var.fx_cmp_02_i_extra_interfaces
    content {
      subnetwork = network_interface.value
    }
  }
}

# ==== FX-CMP-03-C (CQ-CMP-03, conforming)

resource "google_compute_network" "fx_cmp_03_c_x_net" {
  name                    = "${var.run_id}-fx-cmp-03-c-x-net"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "fx_cmp_03_c_x_sub" {
  name          = "${var.run_id}-fx-cmp-03-c-x-sub"
  network       = google_compute_network.fx_cmp_03_c_x_net.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

resource "google_compute_subnetwork" "fx_cmp_03_c_x_proxy_sub" {
  name          = "${var.run_id}-fx-cmp-03-c-proxy"
  network       = google_compute_network.fx_cmp_03_c_x_net.id
  ip_cidr_range = "10.20.250.0/24"
  region        = var.location_1
  purpose       = "REGIONAL_MANAGED_PROXY"
  role          = "ACTIVE"
}

resource "google_compute_region_health_check" "fx_cmp_03_c_hp1" {
  name   = "${var.run_id}-fx-cmp-03-c-hp1"
  region = var.location_1
  http_health_check {
    port = 80
  }
}

resource "google_compute_instance" "fx_cmp_03_c_vm1" {
  name         = "${var.run_id}-fx-cmp-03-c-vm1"
  machine_type = "e2-micro"
  zone         = "${var.location_1}-a"
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.fx_cmp_03_c_x_sub.id
  }
}

resource "google_compute_instance_group" "fx_cmp_03_c_x_group" {
  name      = "${var.run_id}-fx-cmp-03-c-grp"
  zone      = "${var.location_1}-a"
  instances = [google_compute_instance.fx_cmp_03_c_vm1.self_link]
}

resource "google_compute_region_backend_service" "fx_cmp_03_c_pool1" {
  name                  = "${var.run_id}-fx-cmp-03-c-pool1"
  region                = var.location_1
  load_balancing_scheme = "INTERNAL_MANAGED"
  protocol              = "HTTP"
  health_checks         = [google_compute_region_health_check.fx_cmp_03_c_hp1.id]
  backend {
    group           = google_compute_instance_group.fx_cmp_03_c_x_group.id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
}

resource "google_compute_region_url_map" "fx_cmp_03_c_ru1" {
  name            = "${var.run_id}-fx-cmp-03-c-ru1"
  region          = var.location_1
  default_service = google_compute_region_backend_service.fx_cmp_03_c_pool1.id
}

resource "google_compute_region_target_http_proxy" "fx_cmp_03_c_li1" {
  name    = "${var.run_id}-fx-cmp-03-c-li1"
  region  = var.location_1
  url_map = google_compute_region_url_map.fx_cmp_03_c_ru1.id
}

resource "google_compute_forwarding_rule" "fx_cmp_03_c_fe1" {
  name                  = "${var.run_id}-fx-cmp-03-c-fe1"
  region                = var.location_1
  load_balancing_scheme = "INTERNAL_MANAGED"
  port_range            = "443"
  network               = google_compute_network.fx_cmp_03_c_x_net.id
  subnetwork            = google_compute_subnetwork.fx_cmp_03_c_x_sub.id
  target                = google_compute_region_target_http_proxy.fx_cmp_03_c_li1.id
  depends_on            = [google_compute_subnetwork.fx_cmp_03_c_x_proxy_sub]
}

# ==== FX-CMP-03-N (CQ-CMP-03, nonconforming)

resource "google_compute_network" "fx_cmp_03_n_x_net" {
  name                    = "${var.run_id}-fx-cmp-03-n-x-net"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "fx_cmp_03_n_x_sub" {
  name          = "${var.run_id}-fx-cmp-03-n-x-sub"
  network       = google_compute_network.fx_cmp_03_n_x_net.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

resource "google_compute_subnetwork" "fx_cmp_03_n_x_proxy_sub" {
  name          = "${var.run_id}-fx-cmp-03-n-proxy"
  network       = google_compute_network.fx_cmp_03_n_x_net.id
  ip_cidr_range = "10.20.250.0/24"
  region        = var.location_1
  purpose       = "REGIONAL_MANAGED_PROXY"
  role          = "ACTIVE"
}

resource "google_compute_region_health_check" "fx_cmp_03_n_hp1" {
  name   = "${var.run_id}-fx-cmp-03-n-hp1"
  region = var.location_1
  http_health_check {
    port = 80
  }
}

resource "google_compute_instance_group" "fx_cmp_03_n_x_group" {
  name = "${var.run_id}-fx-cmp-03-n-grp"
  zone = "${var.location_1}-a"
}

resource "google_compute_region_backend_service" "fx_cmp_03_n_pool1" {
  name                  = "${var.run_id}-fx-cmp-03-n-pool1"
  region                = var.location_1
  load_balancing_scheme = "INTERNAL_MANAGED"
  protocol              = "HTTP"
  health_checks         = [google_compute_region_health_check.fx_cmp_03_n_hp1.id]
  backend {
    group           = google_compute_instance_group.fx_cmp_03_n_x_group.id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
}

resource "google_compute_region_url_map" "fx_cmp_03_n_ru1" {
  name            = "${var.run_id}-fx-cmp-03-n-ru1"
  region          = var.location_1
  default_service = google_compute_region_backend_service.fx_cmp_03_n_pool1.id
}

resource "google_compute_region_target_http_proxy" "fx_cmp_03_n_li1" {
  name    = "${var.run_id}-fx-cmp-03-n-li1"
  region  = var.location_1
  url_map = google_compute_region_url_map.fx_cmp_03_n_ru1.id
}

resource "google_compute_forwarding_rule" "fx_cmp_03_n_fe1" {
  name                  = "${var.run_id}-fx-cmp-03-n-fe1"
  region                = var.location_1
  load_balancing_scheme = "INTERNAL_MANAGED"
  port_range            = "443"
  network               = google_compute_network.fx_cmp_03_n_x_net.id
  subnetwork            = google_compute_subnetwork.fx_cmp_03_n_x_sub.id
  target                = google_compute_region_target_http_proxy.fx_cmp_03_n_li1.id
  depends_on            = [google_compute_subnetwork.fx_cmp_03_n_x_proxy_sub]
}

# ==== FX-CMP-03-I (CQ-CMP-03, incomplete)

variable "fx_cmp_03_i_group_instances" {
  type        = list(string)
  description = "entrada simbólica da fixture FX-CMP-03-I; sem valor de propósito"
}

resource "google_compute_network" "fx_cmp_03_i_x_net" {
  name                    = "${var.run_id}-fx-cmp-03-i-x-net"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "fx_cmp_03_i_x_sub" {
  name          = "${var.run_id}-fx-cmp-03-i-x-sub"
  network       = google_compute_network.fx_cmp_03_i_x_net.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

resource "google_compute_subnetwork" "fx_cmp_03_i_x_proxy_sub" {
  name          = "${var.run_id}-fx-cmp-03-i-proxy"
  network       = google_compute_network.fx_cmp_03_i_x_net.id
  ip_cidr_range = "10.20.250.0/24"
  region        = var.location_1
  purpose       = "REGIONAL_MANAGED_PROXY"
  role          = "ACTIVE"
}

resource "google_compute_region_health_check" "fx_cmp_03_i_hp1" {
  name   = "${var.run_id}-fx-cmp-03-i-hp1"
  region = var.location_1
  http_health_check {
    port = 80
  }
}

resource "google_compute_instance_group" "fx_cmp_03_i_x_group" {
  name      = "${var.run_id}-fx-cmp-03-i-grp"
  zone      = "${var.location_1}-a"
  instances = var.fx_cmp_03_i_group_instances
}

resource "google_compute_region_backend_service" "fx_cmp_03_i_pool1" {
  name                  = "${var.run_id}-fx-cmp-03-i-pool1"
  region                = var.location_1
  load_balancing_scheme = "INTERNAL_MANAGED"
  protocol              = "HTTP"
  health_checks         = [google_compute_region_health_check.fx_cmp_03_i_hp1.id]
  backend {
    group           = google_compute_instance_group.fx_cmp_03_i_x_group.id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
}

resource "google_compute_region_url_map" "fx_cmp_03_i_ru1" {
  name            = "${var.run_id}-fx-cmp-03-i-ru1"
  region          = var.location_1
  default_service = google_compute_region_backend_service.fx_cmp_03_i_pool1.id
}

resource "google_compute_region_target_http_proxy" "fx_cmp_03_i_li1" {
  name    = "${var.run_id}-fx-cmp-03-i-li1"
  region  = var.location_1
  url_map = google_compute_region_url_map.fx_cmp_03_i_ru1.id
}

resource "google_compute_forwarding_rule" "fx_cmp_03_i_fe1" {
  name                  = "${var.run_id}-fx-cmp-03-i-fe1"
  region                = var.location_1
  load_balancing_scheme = "INTERNAL_MANAGED"
  port_range            = "443"
  network               = google_compute_network.fx_cmp_03_i_x_net.id
  subnetwork            = google_compute_subnetwork.fx_cmp_03_i_x_sub.id
  target                = google_compute_region_target_http_proxy.fx_cmp_03_i_li1.id
  depends_on            = [google_compute_subnetwork.fx_cmp_03_i_x_proxy_sub]
}

# ==== FX-CMP-04-C (CQ-CMP-04, conforming)

resource "google_storage_bucket" "fx_cmp_04_c_c1" {
  name                        = "${var.run_id}-fx-cmp-04-c-c1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
}

resource "google_org_policy_policy" "fx_cmp_04_c_k1" {
  name   = "projects/${var.project}/policies/storage.publicAccessPrevention"
  parent = "projects/${var.project}"
  spec {
    rules {
      enforce = "TRUE"
    }
  }
}

# ==== FX-CMP-04-N (CQ-CMP-04, nonconforming)

resource "google_storage_bucket" "fx_cmp_04_n_c1" {
  name                        = "${var.run_id}-fx-cmp-04-n-c1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
}

resource "google_storage_bucket" "fx_cmp_04_n_c2" {
  name                        = "${var.run_id}-fx-cmp-04-n-c2"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
}

# ==== FX-CMP-04-I (CQ-CMP-04, incomplete)

variable "fx_cmp_04_i_c1_name" {
  type        = string
  description = "entrada simbólica da fixture FX-CMP-04-I; sem valor de propósito"
}

data "google_storage_bucket" "fx_cmp_04_i_c1" {
  name = var.fx_cmp_04_i_c1_name
}

resource "google_org_policy_policy" "fx_cmp_04_i_k1" {
  name   = "projects/${var.project}/policies/storage.publicAccessPrevention"
  parent = "projects/${var.project}"
  spec {
    rules {
      enforce = "TRUE"
    }
  }
}

# ==== FX-CMP-05-C (CQ-CMP-05, conforming)

resource "google_sql_database_instance" "fx_cmp_05_c_i1" {
  name                = "${var.run_id}-fx-cmp-05-c-i1"
  region              = var.location_1
  database_version    = "POSTGRES_16"
  deletion_protection = false
  settings {
    tier    = "db-f1-micro"
    edition = "ENTERPRISE"
  }
}

resource "google_sql_database" "fx_cmp_05_c_db1" {
  name     = "fxdb"
  instance = google_sql_database_instance.fx_cmp_05_c_i1.name
}

# ==== FX-CMP-05-N (CQ-CMP-05, nonconforming)

resource "google_spanner_instance" "fx_cmp_05_n_srv1" {
  name             = "${var.run_id}-fx-cmp-05-n-srv1"
  config           = "regional-${var.location_1}"
  display_name     = "${var.run_id} srv1"
  processing_units = 100
  force_destroy    = true
}

resource "google_spanner_database" "fx_cmp_05_n_db1" {
  name                = "fxdb"
  instance            = google_spanner_instance.fx_cmp_05_n_srv1.name
  deletion_protection = false
}

# ==== FX-CMP-05-I (CQ-CMP-05, incomplete)

resource "google_sql_database_instance" "fx_cmp_05_i_srv2" {
  name                = "${var.run_id}-fx-cmp-05-i-srv2"
  region              = var.location_1
  database_version    = "POSTGRES_16"
  deletion_protection = false
  settings {
    tier              = "db-f1-micro"
    edition           = "ENTERPRISE"
    availability_type = "REGIONAL"
  }
}

resource "google_sql_database" "fx_cmp_05_i_db1" {
  name     = "fxdb"
  instance = google_sql_database_instance.fx_cmp_05_i_srv2.name
}

# ==== FX-AUT-01-C (CQ-AUT-01, conforming)

resource "google_service_account" "fx_aut_01_c_p1" {
  account_id   = "${var.run_id}-fx-aut-01-c-p1"
  display_name = "${var.run_id} FX-AUT-01-C"
}

resource "google_storage_bucket" "fx_aut_01_c_r1" {
  name                        = "${var.run_id}-fx-aut-01-c-r1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
}

resource "google_project_iam_custom_role" "fx_aut_01_c_ps1" {
  role_id     = "${var.run_id}_fx_aut_01_c_ps1"
  title       = "${var.run_id} FX-AUT-01-C"
  permissions = ["storage.objects.get"]
}

resource "google_project_iam_member" "fx_aut_01_c_a1" {
  project = var.project
  role    = google_project_iam_custom_role.fx_aut_01_c_ps1.id
  member  = "serviceAccount:${google_service_account.fx_aut_01_c_p1.email}"
}

# ==== FX-AUT-01-N (CQ-AUT-01, nonconforming)

resource "google_service_account" "fx_aut_01_n_p1" {
  account_id   = "${var.run_id}-fx-aut-01-n-p1"
  display_name = "${var.run_id} FX-AUT-01-N"
}

resource "google_storage_bucket" "fx_aut_01_n_r1" {
  name                        = "${var.run_id}-fx-aut-01-n-r1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
}

resource "google_project_iam_custom_role" "fx_aut_01_n_ps1" {
  role_id     = "${var.run_id}_fx_aut_01_n_ps1"
  title       = "${var.run_id} FX-AUT-01-N"
  permissions = ["storage.objects.get"]
}

resource "google_folder_iam_member" "fx_aut_01_n_a1" {
  folder = "folders/${var.project}-parent"
  role   = google_project_iam_custom_role.fx_aut_01_n_ps1.id
  member = "serviceAccount:${google_service_account.fx_aut_01_n_p1.email}"
}

resource "google_iam_deny_policy" "fx_aut_01_n_d1" {
  name         = "${var.run_id}-fx-aut-01-n-d1"
  display_name = "${var.run_id} FX-AUT-01-N"
  parent       = "cloudresourcemanager.googleapis.com%2Fprojects%2F${var.project}"
  rules {
    deny_rule {
      denied_principals = [
        "principal://iam.googleapis.com/projects/-/serviceAccounts/${google_service_account.fx_aut_01_n_p1.email}",
      ]
      denied_permissions = ["storage.googleapis.com/objects.get"]
    }
  }
}

# ==== FX-AUT-01-I (CQ-AUT-01, incomplete)

resource "google_service_account" "fx_aut_01_i_p1" {
  account_id   = "${var.run_id}-fx-aut-01-i-p1"
  display_name = "${var.run_id} FX-AUT-01-I"
}

resource "google_storage_bucket" "fx_aut_01_i_r1" {
  name                        = "${var.run_id}-fx-aut-01-i-r1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
}

# ==== FX-AUT-02-C (CQ-AUT-02, conforming)

resource "google_service_account" "fx_aut_02_c_p1" {
  account_id   = "${var.run_id}-fx-aut-02-c-p1"
  display_name = "${var.run_id} FX-AUT-02-C"
}

resource "google_storage_bucket" "fx_aut_02_c_x_scope" {
  name                        = "${var.run_id}-fx-aut-02-c-x-scope"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
}

resource "google_project_iam_custom_role" "fx_aut_02_c_ps1" {
  role_id     = "${var.run_id}_fx_aut_02_c_ps1"
  title       = "${var.run_id} FX-AUT-02-C"
  permissions = ["storage.objects.get"]
}

resource "google_storage_bucket_iam_member" "fx_aut_02_c_a1" {
  bucket = google_storage_bucket.fx_aut_02_c_x_scope.name
  role   = google_project_iam_custom_role.fx_aut_02_c_ps1.id
  member = "serviceAccount:${google_service_account.fx_aut_02_c_p1.email}"
}

data "google_iam_policy" "fx_aut_02_c_doc1" {
  binding {
    role    = google_project_iam_custom_role.fx_aut_02_c_ps1.id
    members = ["serviceAccount:${google_service_account.fx_aut_02_c_p1.email}"]
  }
}

resource "google_storage_bucket_iam_policy" "fx_aut_02_c_x_apply_doc" {
  bucket      = google_storage_bucket.fx_aut_02_c_x_scope.name
  policy_data = data.google_iam_policy.fx_aut_02_c_doc1.policy_data
}

# ==== FX-AUT-02-N (CQ-AUT-02, nonconforming)

resource "google_service_account" "fx_aut_02_n_p1" {
  account_id   = "${var.run_id}-fx-aut-02-n-p1"
  display_name = "${var.run_id} FX-AUT-02-N"
}

resource "google_storage_bucket" "fx_aut_02_n_x_scope" {
  name                        = "${var.run_id}-fx-aut-02-n-x-scope"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
}

resource "google_project_iam_custom_role" "fx_aut_02_n_ps1" {
  role_id     = "${var.run_id}_fx_aut_02_n_ps1"
  title       = "${var.run_id} FX-AUT-02-N"
  permissions = ["storage.objects.get"]
}

resource "google_storage_bucket_iam_member" "fx_aut_02_n_a1" {
  bucket = google_storage_bucket.fx_aut_02_n_x_scope.name
  role   = google_project_iam_custom_role.fx_aut_02_n_ps1.id
  member = "serviceAccount:${google_service_account.fx_aut_02_n_p1.email}"
}

resource "google_project_iam_custom_role" "fx_aut_02_n_ps2" {
  role_id     = "${var.run_id}_fx_aut_02_n_ps2"
  title       = "${var.run_id} FX-AUT-02-N"
  permissions = ["storage.objects.list"]
}

resource "google_storage_bucket_iam_member" "fx_aut_02_n_a2" {
  bucket = google_storage_bucket.fx_aut_02_n_x_scope.name
  role   = google_project_iam_custom_role.fx_aut_02_n_ps2.id
  member = "serviceAccount:${google_service_account.fx_aut_02_n_p1.email}"
}

# ==== FX-AUT-02-I (CQ-AUT-02, incomplete)

variable "fx_aut_02_i_doc_member" {
  type        = string
  description = "entrada simbólica da fixture FX-AUT-02-I; sem valor de propósito"
}

resource "google_service_account" "fx_aut_02_i_p1" {
  account_id   = "${var.run_id}-fx-aut-02-i-p1"
  display_name = "${var.run_id} FX-AUT-02-I"
}

resource "google_storage_bucket" "fx_aut_02_i_x_scope" {
  name                        = "${var.run_id}-fx-aut-02-i-x-scope"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
}

resource "google_project_iam_custom_role" "fx_aut_02_i_ps1" {
  role_id     = "${var.run_id}_fx_aut_02_i_ps1"
  title       = "${var.run_id} FX-AUT-02-I"
  permissions = ["storage.objects.get"]
}

resource "google_storage_bucket_iam_member" "fx_aut_02_i_a1" {
  bucket = google_storage_bucket.fx_aut_02_i_x_scope.name
  role   = google_project_iam_custom_role.fx_aut_02_i_ps1.id
  member = "serviceAccount:${google_service_account.fx_aut_02_i_p1.email}"
}

data "google_iam_policy" "fx_aut_02_i_doc1" {
  binding {
    role    = google_project_iam_custom_role.fx_aut_02_i_ps1.id
    members = [var.fx_aut_02_i_doc_member]
  }
}

resource "google_storage_bucket_iam_policy" "fx_aut_02_i_x_apply_doc" {
  bucket      = google_storage_bucket.fx_aut_02_i_x_scope.name
  policy_data = data.google_iam_policy.fx_aut_02_i_doc1.policy_data
}

# ==== FX-AUT-03-C (CQ-AUT-03, conforming)

resource "google_service_account" "fx_aut_03_c_p1" {
  account_id   = "${var.run_id}-fx-aut-03-c-p1"
  display_name = "${var.run_id} FX-AUT-03-C"
}

resource "google_project_iam_custom_role" "fx_aut_03_c_ps1" {
  role_id     = "${var.run_id}_fx_aut_03_c_ps1"
  title       = "${var.run_id} FX-AUT-03-C"
  permissions = ["storage.objects.get"]
}

resource "google_storage_bucket" "fx_aut_03_c_r2" {
  name                        = "${var.run_id}-fx-aut-03-c-r2"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
}

resource "google_storage_bucket" "fx_aut_03_c_x_child" {
  name                        = "${var.run_id}-fx-aut-03-c-x-child"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
}

resource "google_storage_bucket_iam_member" "fx_aut_03_c_a1" {
  bucket = google_storage_bucket.fx_aut_03_c_x_child.name
  role   = google_project_iam_custom_role.fx_aut_03_c_ps1.id
  member = "serviceAccount:${google_service_account.fx_aut_03_c_p1.email}"
}

# ==== FX-AUT-03-N (CQ-AUT-03, nonconforming)

resource "google_service_account" "fx_aut_03_n_p1" {
  account_id   = "${var.run_id}-fx-aut-03-n-p1"
  display_name = "${var.run_id} FX-AUT-03-N"
}

resource "google_project_iam_custom_role" "fx_aut_03_n_ps1" {
  role_id     = "${var.run_id}_fx_aut_03_n_ps1"
  title       = "${var.run_id} FX-AUT-03-N"
  permissions = ["storage.objects.get"]
}

resource "google_storage_bucket" "fx_aut_03_n_r2" {
  name                        = "${var.run_id}-fx-aut-03-n-r2"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
}

resource "google_storage_bucket" "fx_aut_03_n_x_child" {
  name                        = "${var.run_id}-fx-aut-03-n-x-child"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
}

resource "google_project_iam_member" "fx_aut_03_n_a1" {
  project = var.project
  role    = google_project_iam_custom_role.fx_aut_03_n_ps1.id
  member  = "serviceAccount:${google_service_account.fx_aut_03_n_p1.email}"
}

# ==== FX-AUT-03-I (CQ-AUT-03, incomplete)

variable "fx_aut_03_i_child_scope_bucket" {
  type        = string
  description = "entrada simbólica da fixture FX-AUT-03-I; sem valor de propósito"
}

resource "google_service_account" "fx_aut_03_i_p1" {
  account_id   = "${var.run_id}-fx-aut-03-i-p1"
  display_name = "${var.run_id} FX-AUT-03-I"
}

resource "google_project_iam_custom_role" "fx_aut_03_i_ps1" {
  role_id     = "${var.run_id}_fx_aut_03_i_ps1"
  title       = "${var.run_id} FX-AUT-03-I"
  permissions = ["storage.objects.get"]
}

resource "google_storage_bucket" "fx_aut_03_i_r2" {
  name                        = "${var.run_id}-fx-aut-03-i-r2"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
}

resource "google_storage_bucket_iam_member" "fx_aut_03_i_a1" {
  bucket = var.fx_aut_03_i_child_scope_bucket
  role   = google_project_iam_custom_role.fx_aut_03_i_ps1.id
  member = "serviceAccount:${google_service_account.fx_aut_03_i_p1.email}"
}

# ==== FX-AUT-04-C (CQ-AUT-04, conforming)

resource "google_project_iam_custom_role" "fx_aut_04_c_ps1" {
  role_id     = "${var.run_id}_fx_aut_04_c_ps1"
  title       = "${var.run_id} FX-AUT-04-C"
  permissions = ["storage.objects.get"]
}

resource "google_service_account" "fx_aut_04_c_u1" {
  account_id   = "${var.run_id}-fx-aut-04-c-u1"
  display_name = "${var.run_id} FX-AUT-04-C"
}

resource "google_cloud_identity_group" "fx_aut_04_c_g1" {
  parent       = "customers/${var.project}-customer"
  display_name = "${var.run_id} g1"
  labels = {
    "cloudidentity.googleapis.com/groups.discussion_forum" = ""
  }
  group_key {
    id = "${var.run_id}-g1@example.com"
  }
}

resource "google_cloud_identity_group_membership" "fx_aut_04_c_x_membership" {
  group = google_cloud_identity_group.fx_aut_04_c_g1.id
  preferred_member_key {
    id = google_service_account.fx_aut_04_c_u1.email
  }
  roles {
    name = "MEMBER"
  }
}

resource "google_project_iam_member" "fx_aut_04_c_a1" {
  project = var.project
  role    = google_project_iam_custom_role.fx_aut_04_c_ps1.id
  member  = "group:${google_cloud_identity_group.fx_aut_04_c_g1.group_key[0].id}"
}

# ==== FX-AUT-04-N (CQ-AUT-04, nonconforming)

resource "google_project_iam_custom_role" "fx_aut_04_n_ps1" {
  role_id     = "${var.run_id}_fx_aut_04_n_ps1"
  title       = "${var.run_id} FX-AUT-04-N"
  permissions = ["storage.objects.get"]
}

resource "google_service_account" "fx_aut_04_n_u1" {
  account_id   = "${var.run_id}-fx-aut-04-n-u1"
  display_name = "${var.run_id} FX-AUT-04-N"
}

resource "google_cloud_identity_group" "fx_aut_04_n_g1" {
  parent       = "customers/${var.project}-customer"
  display_name = "${var.run_id} g1"
  labels = {
    "cloudidentity.googleapis.com/groups.discussion_forum" = ""
  }
  group_key {
    id = "${var.run_id}-g1@example.com"
  }
}

resource "google_project_iam_member" "fx_aut_04_n_a1" {
  project = var.project
  role    = google_project_iam_custom_role.fx_aut_04_n_ps1.id
  member  = "group:${google_cloud_identity_group.fx_aut_04_n_g1.group_key[0].id}"
}

# ==== FX-AUT-04-I (CQ-AUT-04, incomplete)

variable "fx_aut_04_i_workforce_pool" {
  type        = string
  description = "entrada simbólica da fixture FX-AUT-04-I; sem valor de propósito"
}

variable "fx_aut_04_i_external_group" {
  type        = string
  description = "entrada simbólica da fixture FX-AUT-04-I; sem valor de propósito"
}

resource "google_project_iam_custom_role" "fx_aut_04_i_ps1" {
  role_id     = "${var.run_id}_fx_aut_04_i_ps1"
  title       = "${var.run_id} FX-AUT-04-I"
  permissions = ["storage.objects.get"]
}

resource "google_project_iam_member" "fx_aut_04_i_a1" {
  project = var.project
  role    = google_project_iam_custom_role.fx_aut_04_i_ps1.id
  member  = "principalSet://iam.googleapis.com/locations/global/workforcePools/${var.fx_aut_04_i_workforce_pool}/group/${var.fx_aut_04_i_external_group}"
}

# ==== FX-AUT-05-C (CQ-AUT-05, conforming)

resource "google_service_account" "fx_aut_05_c_p1" {
  account_id   = "${var.run_id}-fx-aut-05-c-p1"
  display_name = "${var.run_id} FX-AUT-05-C"
}

resource "google_storage_bucket" "fx_aut_05_c_r1" {
  name                        = "${var.run_id}-fx-aut-05-c-r1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
}

resource "google_project_iam_custom_role" "fx_aut_05_c_ps1" {
  role_id     = "${var.run_id}_fx_aut_05_c_ps1"
  title       = "${var.run_id} FX-AUT-05-C"
  permissions = ["storage.objects.get"]
}

resource "google_project_iam_member" "fx_aut_05_c_a1" {
  project = var.project
  role    = google_project_iam_custom_role.fx_aut_05_c_ps1.id
  member  = "serviceAccount:${google_service_account.fx_aut_05_c_p1.email}"
  condition {
    title      = "fxcond"
    expression = "request.time < timestamp(\"2027-01-01T00:00:00Z\")"
  }
}

# ==== FX-AUT-05-N (CQ-AUT-05, nonconforming)

resource "google_service_account" "fx_aut_05_n_p1" {
  account_id   = "${var.run_id}-fx-aut-05-n-p1"
  display_name = "${var.run_id} FX-AUT-05-N"
}

resource "google_storage_bucket" "fx_aut_05_n_r1" {
  name                        = "${var.run_id}-fx-aut-05-n-r1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
}

resource "google_project_iam_custom_role" "fx_aut_05_n_ps1" {
  role_id     = "${var.run_id}_fx_aut_05_n_ps1"
  title       = "${var.run_id} FX-AUT-05-N"
  permissions = ["storage.objects.get"]
}

resource "google_project_iam_member" "fx_aut_05_n_a1" {
  project = var.project
  role    = google_project_iam_custom_role.fx_aut_05_n_ps1.id
  member  = "serviceAccount:${google_service_account.fx_aut_05_n_p1.email}"
  condition {
    title      = "fxcond"
    expression = "request.time < timestamp(\"2027-01-01T00:00:00Z\")"
  }
}

# ==== FX-AUT-05-I (CQ-AUT-05, incomplete)

resource "google_service_account" "fx_aut_05_i_p1" {
  account_id   = "${var.run_id}-fx-aut-05-i-p1"
  display_name = "${var.run_id} FX-AUT-05-I"
}

resource "google_storage_bucket" "fx_aut_05_i_r1" {
  name                        = "${var.run_id}-fx-aut-05-i-r1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
}

resource "google_project_iam_custom_role" "fx_aut_05_i_ps1" {
  role_id     = "${var.run_id}_fx_aut_05_i_ps1"
  title       = "${var.run_id} FX-AUT-05-I"
  permissions = ["storage.objects.get"]
}

resource "google_project_iam_member" "fx_aut_05_i_a1" {
  project = var.project
  role    = google_project_iam_custom_role.fx_aut_05_i_ps1.id
  member  = "serviceAccount:${google_service_account.fx_aut_05_i_p1.email}"
  condition {
    title      = "fxcond"
    expression = "\"accessPolicies/0/accessLevels/compliant_device\" in request.auth.access_levels"
  }
}

# ==== FX-NET-01-C (CQ-NET-01, conforming)

resource "google_compute_network" "fx_net_01_c_x_net" {
  name                            = "${var.run_id}-fx-net-01-c-x-net"
  auto_create_subnetworks         = false
  delete_default_routes_on_create = true
}

resource "google_compute_subnetwork" "fx_net_01_c_sa" {
  name          = "${var.run_id}-fx-net-01-c-sa"
  network       = google_compute_network.fx_net_01_c_x_net.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

resource "google_compute_instance" "fx_net_01_c_vm1" {
  name         = "${var.run_id}-fx-net-01-c-vm1"
  machine_type = "e2-micro"
  zone         = "${var.location_1}-a"
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.fx_net_01_c_sa.id
    access_config {
      network_tier = "STANDARD"
    }
  }
}

resource "google_compute_route" "fx_net_01_c_rte1" {
  name             = "${var.run_id}-fx-net-01-c-rte1"
  network          = google_compute_network.fx_net_01_c_x_net.id
  dest_range       = "0.0.0.0/0"
  next_hop_gateway = "default-internet-gateway"
}

resource "google_compute_firewall" "fx_net_01_c_r1" {
  name          = "${var.run_id}-fx-net-01-c-r1"
  network       = google_compute_network.fx_net_01_c_x_net.id
  direction     = "INGRESS"
  priority      = 200
  source_ranges = ["203.0.113.0/24"]
  allow {
    protocol = "tcp"
    ports    = ["443"]
  }
}

# ==== FX-NET-01-N (CQ-NET-01, nonconforming)

resource "google_compute_network" "fx_net_01_n_x_net" {
  name                            = "${var.run_id}-fx-net-01-n-x-net"
  auto_create_subnetworks         = false
  delete_default_routes_on_create = true
}

resource "google_compute_subnetwork" "fx_net_01_n_sa" {
  name          = "${var.run_id}-fx-net-01-n-sa"
  network       = google_compute_network.fx_net_01_n_x_net.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

resource "google_compute_instance" "fx_net_01_n_vm1" {
  name         = "${var.run_id}-fx-net-01-n-vm1"
  machine_type = "e2-micro"
  zone         = "${var.location_1}-a"
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.fx_net_01_n_sa.id
    access_config {
      network_tier = "STANDARD"
    }
  }
}

resource "google_compute_route" "fx_net_01_n_rte1" {
  name             = "${var.run_id}-fx-net-01-n-rte1"
  network          = google_compute_network.fx_net_01_n_x_net.id
  dest_range       = "0.0.0.0/0"
  next_hop_gateway = "default-internet-gateway"
}

resource "google_compute_firewall" "fx_net_01_n_r1" {
  name          = "${var.run_id}-fx-net-01-n-r1"
  network       = google_compute_network.fx_net_01_n_x_net.id
  direction     = "INGRESS"
  priority      = 200
  source_ranges = ["203.0.113.0/24"]
  allow {
    protocol = "tcp"
    ports    = ["443"]
  }
}

resource "google_compute_firewall" "fx_net_01_n_r2" {
  name          = "${var.run_id}-fx-net-01-n-r2"
  network       = google_compute_network.fx_net_01_n_x_net.id
  direction     = "INGRESS"
  priority      = 100
  source_ranges = ["0.0.0.0/0"]
  deny {
    protocol = "tcp"
    ports    = ["443"]
  }
}

# ==== FX-NET-01-I (CQ-NET-01, incomplete)

resource "google_compute_network" "fx_net_01_i_x_net" {
  name                            = "${var.run_id}-fx-net-01-i-x-net"
  auto_create_subnetworks         = false
  delete_default_routes_on_create = true
}

resource "google_compute_subnetwork" "fx_net_01_i_sa" {
  name          = "${var.run_id}-fx-net-01-i-sa"
  network       = google_compute_network.fx_net_01_i_x_net.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

resource "google_compute_instance" "fx_net_01_i_vm1" {
  name         = "${var.run_id}-fx-net-01-i-vm1"
  machine_type = "e2-micro"
  zone         = "${var.location_1}-a"
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.fx_net_01_i_sa.id
    access_config {
      network_tier = "STANDARD"
    }
  }
}

resource "google_compute_route" "fx_net_01_i_rte1" {
  name             = "${var.run_id}-fx-net-01-i-rte1"
  network          = google_compute_network.fx_net_01_i_x_net.id
  dest_range       = "0.0.0.0/0"
  next_hop_gateway = "default-internet-gateway"
}

resource "google_compute_firewall" "fx_net_01_i_r1" {
  name          = "${var.run_id}-fx-net-01-i-r1"
  network       = google_compute_network.fx_net_01_i_x_net.id
  direction     = "INGRESS"
  priority      = 200
  source_ranges = ["203.0.113.0/24"]
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# ==== FX-NET-02-C (CQ-NET-02, conforming)

resource "google_compute_network" "fx_net_02_c_x_net" {
  name                    = "${var.run_id}-fx-net-02-c-x-net"
  auto_create_subnetworks = false
}

resource "google_compute_firewall" "fx_net_02_c_r1" {
  name          = "${var.run_id}-fx-net-02-c-r1"
  network       = google_compute_network.fx_net_02_c_x_net.id
  direction     = "INGRESS"
  priority      = 1000
  source_ranges = ["203.0.113.0/24"]
  allow {
    protocol = "tcp"
    ports    = ["443"]
  }
}

# ==== FX-NET-02-N (CQ-NET-02, nonconforming): NOT_APPLICABLE — o firewall do GCP não tem regra sem estado

# ==== FX-NET-02-I (CQ-NET-02, incomplete): NOT_APPLICABLE — o estado de conexão não é declarável no GCP e o mecanismo é documentado como sempre com estado: a situação 'estado não declarado e padrão sem evidência' não existe

# ==== FX-NET-03-C (CQ-NET-03, conforming)

resource "google_compute_network" "fx_net_03_c_x_net" {
  name                            = "${var.run_id}-fx-net-03-c-x-net"
  auto_create_subnetworks         = false
  delete_default_routes_on_create = true
}

resource "google_compute_subnetwork" "fx_net_03_c_sa" {
  name          = "${var.run_id}-fx-net-03-c-sa"
  network       = google_compute_network.fx_net_03_c_x_net.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

resource "google_compute_instance" "fx_net_03_c_vm1" {
  name         = "${var.run_id}-fx-net-03-c-vm1"
  machine_type = "e2-micro"
  zone         = "${var.location_1}-a"
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.fx_net_03_c_sa.id
    access_config {
      network_tier = "STANDARD"
    }
  }
}

resource "google_compute_route" "fx_net_03_c_rte1" {
  name             = "${var.run_id}-fx-net-03-c-rte1"
  network          = google_compute_network.fx_net_03_c_x_net.id
  dest_range       = "0.0.0.0/0"
  next_hop_gateway = "default-internet-gateway"
}

resource "google_compute_firewall" "fx_net_03_c_r1" {
  name          = "${var.run_id}-fx-net-03-c-r1"
  network       = google_compute_network.fx_net_03_c_x_net.id
  direction     = "INGRESS"
  priority      = 200
  source_ranges = ["0.0.0.0/0"]
  allow {
    protocol = "tcp"
    ports    = ["443"]
  }
}

# ==== FX-NET-03-N (CQ-NET-03, nonconforming)

resource "google_compute_network" "fx_net_03_n_x_net" {
  name                            = "${var.run_id}-fx-net-03-n-x-net"
  auto_create_subnetworks         = false
  delete_default_routes_on_create = true
}

resource "google_compute_subnetwork" "fx_net_03_n_sa" {
  name          = "${var.run_id}-fx-net-03-n-sa"
  network       = google_compute_network.fx_net_03_n_x_net.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

resource "google_compute_instance" "fx_net_03_n_vm1" {
  name         = "${var.run_id}-fx-net-03-n-vm1"
  machine_type = "e2-micro"
  zone         = "${var.location_1}-a"
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.fx_net_03_n_sa.id
  }
}

resource "google_compute_firewall" "fx_net_03_n_r1" {
  name          = "${var.run_id}-fx-net-03-n-r1"
  network       = google_compute_network.fx_net_03_n_x_net.id
  direction     = "INGRESS"
  priority      = 1000
  source_ranges = ["0.0.0.0/0"]
  allow {
    protocol = "tcp"
    ports    = ["443"]
  }
}

# ==== FX-NET-03-I (CQ-NET-03, incomplete)

variable "fx_net_03_i_delete_default_routes" {
  type        = bool
  description = "entrada simbólica da fixture FX-NET-03-I; sem valor de propósito"
}

resource "google_compute_network" "fx_net_03_i_x_net" {
  name                            = "${var.run_id}-fx-net-03-i-x-net"
  auto_create_subnetworks         = false
  delete_default_routes_on_create = var.fx_net_03_i_delete_default_routes
}

resource "google_compute_subnetwork" "fx_net_03_i_sa" {
  name          = "${var.run_id}-fx-net-03-i-sa"
  network       = google_compute_network.fx_net_03_i_x_net.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

resource "google_compute_instance" "fx_net_03_i_vm1" {
  name         = "${var.run_id}-fx-net-03-i-vm1"
  machine_type = "e2-micro"
  zone         = "${var.location_1}-a"
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.fx_net_03_i_sa.id
    access_config {
      network_tier = "STANDARD"
    }
  }
}

resource "google_compute_firewall" "fx_net_03_i_r1" {
  name          = "${var.run_id}-fx-net-03-i-r1"
  network       = google_compute_network.fx_net_03_i_x_net.id
  direction     = "INGRESS"
  priority      = 1000
  source_ranges = ["0.0.0.0/0"]
  allow {
    protocol = "tcp"
    ports    = ["443"]
  }
}

# ==== FX-NET-04-C (CQ-NET-04, conforming)

resource "google_compute_network" "fx_net_04_c_x_net_a" {
  name                    = "${var.run_id}-fx-net-04-c-x-net-a"
  auto_create_subnetworks = false
}

resource "google_compute_network" "fx_net_04_c_x_net_b" {
  name                    = "${var.run_id}-fx-net-04-c-netb"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "fx_net_04_c_x_sub_a" {
  name          = "${var.run_id}-fx-net-04-c-x-sub-a"
  network       = google_compute_network.fx_net_04_c_x_net_a.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

resource "google_compute_subnetwork" "fx_net_04_c_x_sub_b" {
  name          = "${var.run_id}-fx-net-04-c-subb"
  network       = google_compute_network.fx_net_04_c_x_net_b.id
  ip_cidr_range = "10.21.1.0/24"
  region        = var.location_1
}

resource "google_compute_instance" "fx_net_04_c_vm1" {
  name         = "${var.run_id}-fx-net-04-c-vm1"
  machine_type = "e2-micro"
  zone         = "${var.location_1}-a"
  tags         = ["${var.run_id}-fxtag"]
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.fx_net_04_c_x_sub_a.id
  }
  network_interface {
    subnetwork = google_compute_subnetwork.fx_net_04_c_x_sub_b.id
  }
}

resource "google_compute_firewall" "fx_net_04_c_rs1" {
  name          = "${var.run_id}-fx-net-04-c-rs1"
  network       = google_compute_network.fx_net_04_c_x_net_b.id
  direction     = "INGRESS"
  source_ranges = ["203.0.113.0/24"]
  target_tags   = ["${var.run_id}-fxtag"]
  allow {
    protocol = "tcp"
    ports    = ["443"]
  }
}

# ==== FX-NET-04-N (CQ-NET-04, nonconforming)

resource "google_compute_network" "fx_net_04_n_x_net_a" {
  name                    = "${var.run_id}-fx-net-04-n-x-net-a"
  auto_create_subnetworks = false
}

resource "google_compute_network" "fx_net_04_n_x_net_b" {
  name                    = "${var.run_id}-fx-net-04-n-netb"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "fx_net_04_n_x_sub_a" {
  name          = "${var.run_id}-fx-net-04-n-x-sub-a"
  network       = google_compute_network.fx_net_04_n_x_net_a.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

resource "google_compute_subnetwork" "fx_net_04_n_x_sub_b" {
  name          = "${var.run_id}-fx-net-04-n-subb"
  network       = google_compute_network.fx_net_04_n_x_net_b.id
  ip_cidr_range = "10.21.1.0/24"
  region        = var.location_1
}

resource "google_compute_instance" "fx_net_04_n_vm1" {
  name         = "${var.run_id}-fx-net-04-n-vm1"
  machine_type = "e2-micro"
  zone         = "${var.location_1}-a"
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.fx_net_04_n_x_sub_a.id
  }
}

resource "google_compute_instance" "fx_net_04_n_vm2" {
  name         = "${var.run_id}-fx-net-04-n-vm2"
  machine_type = "e2-micro"
  zone         = "${var.location_1}-a"
  tags         = ["${var.run_id}-fxtag"]
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.fx_net_04_n_x_sub_b.id
  }
}

resource "google_compute_firewall" "fx_net_04_n_rs1" {
  name          = "${var.run_id}-fx-net-04-n-rs1"
  network       = google_compute_network.fx_net_04_n_x_net_b.id
  direction     = "INGRESS"
  source_ranges = ["203.0.113.0/24"]
  target_tags   = ["${var.run_id}-fxtag"]
  allow {
    protocol = "tcp"
    ports    = ["443"]
  }
}

# ==== FX-NET-04-I (CQ-NET-04, incomplete)

variable "fx_net_04_i_nic2_subnetwork" {
  type        = string
  description = "entrada simbólica da fixture FX-NET-04-I; sem valor de propósito"
}

resource "google_compute_network" "fx_net_04_i_x_net_a" {
  name                    = "${var.run_id}-fx-net-04-i-x-net-a"
  auto_create_subnetworks = false
}

resource "google_compute_network" "fx_net_04_i_x_net_b" {
  name                    = "${var.run_id}-fx-net-04-i-netb"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "fx_net_04_i_x_sub_a" {
  name          = "${var.run_id}-fx-net-04-i-x-sub-a"
  network       = google_compute_network.fx_net_04_i_x_net_a.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

resource "google_compute_subnetwork" "fx_net_04_i_x_sub_b" {
  name          = "${var.run_id}-fx-net-04-i-subb"
  network       = google_compute_network.fx_net_04_i_x_net_b.id
  ip_cidr_range = "10.21.1.0/24"
  region        = var.location_1
}

resource "google_compute_instance" "fx_net_04_i_vm1" {
  name         = "${var.run_id}-fx-net-04-i-vm1"
  machine_type = "e2-micro"
  zone         = "${var.location_1}-a"
  tags         = ["${var.run_id}-fxtag"]
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.fx_net_04_i_x_sub_a.id
  }
  network_interface {
    subnetwork = var.fx_net_04_i_nic2_subnetwork
  }
}

resource "google_compute_firewall" "fx_net_04_i_rs1" {
  name          = "${var.run_id}-fx-net-04-i-rs1"
  network       = google_compute_network.fx_net_04_i_x_net_b.id
  direction     = "INGRESS"
  source_ranges = ["203.0.113.0/24"]
  target_tags   = ["${var.run_id}-fxtag"]
  allow {
    protocol = "tcp"
    ports    = ["443"]
  }
}

# ==== FX-CVO-01-C (CQ-CVO-01, conforming)

resource "google_storage_bucket" "fx_cvo_01_c_c1" {
  name                        = "${var.run_id}-fx-cvo-01-c-c1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
  versioning {
    enabled = true
  }
}

# ==== FX-CVO-01-N (CQ-CVO-01, nonconforming)

resource "google_storage_bucket" "fx_cvo_01_n_c1" {
  name                        = "${var.run_id}-fx-cvo-01-n-c1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
  versioning {
    enabled = true
  }
}

# ==== FX-CVO-01-I (CQ-CVO-01, incomplete)

resource "google_storage_bucket" "fx_cvo_01_i_c1" {
  name                        = "${var.run_id}-fx-cvo-01-i-c1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
  versioning {
    enabled = true
  }
}

# ==== FX-CVO-02-C (CQ-CVO-02, conforming)

resource "google_storage_bucket" "fx_cvo_02_c_c1" {
  name                        = "${var.run_id}-fx-cvo-02-c-c1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
  versioning {
    enabled = true
  }
}

# ==== FX-CVO-02-N (CQ-CVO-02, nonconforming)

resource "google_storage_bucket" "fx_cvo_02_n_c1" {
  name                        = "${var.run_id}-fx-cvo-02-n-c1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
}

# ==== FX-CVO-02-I (CQ-CVO-02, incomplete)

variable "fx_cvo_02_i_versioning" {
  type        = bool
  description = "entrada simbólica da fixture FX-CVO-02-I; sem valor de propósito"
}

resource "google_storage_bucket" "fx_cvo_02_i_c1" {
  name                        = "${var.run_id}-fx-cvo-02-i-c1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
  versioning {
    enabled = var.fx_cvo_02_i_versioning
  }
}

# ==== FX-CVO-03-C (CQ-CVO-03, conforming)

resource "google_sql_database_instance" "fx_cvo_03_c_i1" {
  name                = "${var.run_id}-fx-cvo-03-c-i1"
  region              = var.location_1
  database_version    = "POSTGRES_16"
  deletion_protection = false
  settings {
    tier    = "db-f1-micro"
    edition = "ENTERPRISE"
  }
}

resource "google_pubsub_topic" "fx_cvo_03_c_t1" {
  name = "${var.run_id}-fx-cvo-03-c-t1"
}

resource "google_monitoring_notification_channel" "fx_cvo_03_c_x_channel" {
  display_name = "${var.run_id} FX-CVO-03-C"
  type         = "pubsub"
  labels = {
    topic = google_pubsub_topic.fx_cvo_03_c_t1.id
  }
}

resource "google_monitoring_alert_policy" "fx_cvo_03_c_al1" {
  display_name          = "${var.run_id} FX-CVO-03-C"
  combiner              = "OR"
  notification_channels = [google_monitoring_notification_channel.fx_cvo_03_c_x_channel.id]
  conditions {
    display_name = "cpu"
    condition_threshold {
      filter          = "resource.type = \"cloudsql_database\" AND resource.labels.database_id = \"${var.project}:${google_sql_database_instance.fx_cvo_03_c_i1.name}\" AND metric.type = \"cloudsql.googleapis.com/database/cpu/utilization\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0.9
      duration        = "300s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }
}

# ==== FX-CVO-03-N (CQ-CVO-03, nonconforming)

resource "google_sql_database_instance" "fx_cvo_03_n_i1" {
  name                = "${var.run_id}-fx-cvo-03-n-i1"
  region              = var.location_1
  database_version    = "POSTGRES_16"
  deletion_protection = false
  settings {
    tier    = "db-f1-micro"
    edition = "ENTERPRISE"
  }
}

# ==== FX-CVO-03-I (CQ-CVO-03, incomplete)

resource "google_sql_database_instance" "fx_cvo_03_i_i1" {
  name                = "${var.run_id}-fx-cvo-03-i-i1"
  region              = var.location_1
  database_version    = "POSTGRES_16"
  deletion_protection = false
  settings {
    tier    = "db-f1-micro"
    edition = "ENTERPRISE"
  }
}

# ==== FX-CVO-04-C (CQ-CVO-04, conforming)

resource "google_secret_manager_secret" "fx_cvo_04_c_x_secret" {
  secret_id = "${var.run_id}-fx-cvo-04-c-secret"
  replication {
    auto {
    }
  }
}

data "google_secret_manager_secret_version" "fx_cvo_04_c_x_secret_value" {
  secret = google_secret_manager_secret.fx_cvo_04_c_x_secret.id
}

resource "google_sql_database_instance" "fx_cvo_04_c_i1" {
  name                = "${var.run_id}-fx-cvo-04-c-i1"
  region              = var.location_1
  database_version    = "POSTGRES_16"
  deletion_protection = false
  root_password       = data.google_secret_manager_secret_version.fx_cvo_04_c_x_secret_value.secret_data
  settings {
    tier    = "db-f1-micro"
    edition = "ENTERPRISE"
  }
}

# ==== FX-CVO-04-N (CQ-CVO-04, nonconforming)

resource "google_sql_database_instance" "fx_cvo_04_n_i1" {
  name                = "${var.run_id}-fx-cvo-04-n-i1"
  region              = var.location_1
  database_version    = "POSTGRES_16"
  deletion_protection = false
  settings {
    tier    = "db-f1-micro"
    edition = "ENTERPRISE"
  }
}

# ==== FX-CVO-04-I (CQ-CVO-04, incomplete)

variable "fx_cvo_04_i_root_password" {
  type        = string
  description = "entrada simbólica da fixture FX-CVO-04-I; sem valor de propósito"
}

resource "google_sql_database_instance" "fx_cvo_04_i_i1" {
  name                = "${var.run_id}-fx-cvo-04-i-i1"
  region              = var.location_1
  database_version    = "POSTGRES_16"
  deletion_protection = false
  root_password       = var.fx_cvo_04_i_root_password
  settings {
    tier    = "db-f1-micro"
    edition = "ENTERPRISE"
  }
}

# ==== FX-LOSS-01-C (CQ-LOSS-01, conforming)

resource "google_logging_project_bucket_config" "fx_loss_01_c_s1" {
  project        = var.project
  location       = "global"
  bucket_id      = "${var.run_id}_fx_loss_01_c_s1"
  retention_days = 30
}

# ==== FX-LOSS-01-N (CQ-LOSS-01, nonconforming)

resource "google_logging_project_bucket_config" "fx_loss_01_n_s1" {
  project        = var.project
  location       = "global"
  bucket_id      = "${var.run_id}_fx_loss_01_n_s1"
  retention_days = 400
}

# ==== FX-LOSS-01-I (CQ-LOSS-01, incomplete)

resource "google_logging_project_bucket_config" "fx_loss_01_i_s1" {
  project        = var.project
  location       = "global"
  bucket_id      = "${var.run_id}_fx_loss_01_i_s1"
  retention_days = 30
}

# ==== FX-LOSS-02-C (CQ-LOSS-02, conforming)

resource "google_compute_network" "fx_loss_02_c_x_net" {
  name                    = "${var.run_id}-fx-loss-02-c-x-net"
  auto_create_subnetworks = false
}

resource "google_compute_firewall" "fx_loss_02_c_r1" {
  name          = "${var.run_id}-fx-loss-02-c-r1"
  network       = google_compute_network.fx_loss_02_c_x_net.id
  direction     = "INGRESS"
  priority      = 100
  source_ranges = ["0.0.0.0/0"]
  deny {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# ==== FX-LOSS-02-N (CQ-LOSS-02, nonconforming)

resource "google_compute_network" "fx_loss_02_n_x_net" {
  name                    = "${var.run_id}-fx-loss-02-n-x-net"
  auto_create_subnetworks = false
}

resource "google_compute_firewall" "fx_loss_02_n_r1" {
  name          = "${var.run_id}-fx-loss-02-n-r1"
  network       = google_compute_network.fx_loss_02_n_x_net.id
  direction     = "INGRESS"
  priority      = 100
  source_ranges = ["0.0.0.0/0"]
  deny {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# ==== FX-LOSS-02-I (CQ-LOSS-02, incomplete)

resource "google_compute_network" "fx_loss_02_i_x_net" {
  name                    = "${var.run_id}-fx-loss-02-i-x-net"
  auto_create_subnetworks = false
}

resource "google_compute_firewall" "fx_loss_02_i_r1" {
  name          = "${var.run_id}-fx-loss-02-i-r1"
  network       = google_compute_network.fx_loss_02_i_x_net.id
  direction     = "INGRESS"
  priority      = 100
  source_ranges = ["0.0.0.0/0"]
  deny {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# ==== FX-LOSS-03-C (CQ-LOSS-03, conforming)

resource "google_storage_bucket" "fx_loss_03_c_s1" {
  name                        = "${var.run_id}-fx-loss-03-c-s1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
  versioning {
    enabled = true
  }
}

# ==== FX-LOSS-03-N (CQ-LOSS-03, nonconforming)

resource "google_storage_bucket" "fx_loss_03_n_s1" {
  name                        = "${var.run_id}-fx-loss-03-n-s1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
}

# ==== FX-LOSS-03-I (CQ-LOSS-03, incomplete)

variable "fx_loss_03_i_versioning" {
  type        = bool
  description = "entrada simbólica da fixture FX-LOSS-03-I; sem valor de propósito"
}

resource "google_storage_bucket" "fx_loss_03_i_s1" {
  name                        = "${var.run_id}-fx-loss-03-i-s1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
  versioning {
    enabled = var.fx_loss_03_i_versioning
  }
}

# ==== FX-LOSS-04-C (CQ-LOSS-04, conforming)

resource "google_logging_project_bucket_config" "fx_loss_04_c_s1" {
  project        = var.project
  location       = "global"
  bucket_id      = "${var.run_id}_fx_loss_04_c_s1"
  retention_days = 7
}

# ==== FX-LOSS-04-N (CQ-LOSS-04, nonconforming): NOT_APPLICABLE — o GCP não exprime retenção em meses de calendário: durações são segundos ou dias inteiros

# ==== FX-LOSS-04-I (CQ-LOSS-04, incomplete)

resource "google_storage_bucket" "fx_loss_04_i_s1" {
  name                        = "${var.run_id}-fx-loss-04-i-s1"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }
}

# ==== FX-NEW-01-C (CQ-NEW-01, conforming)

resource "google_storage_bucket" "fx_new_01_c_x_c" {
  name                        = "${var.run_id}-fx-new-01-c-x-c"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
  versioning {
    enabled = true
  }
}

# ==== FX-NEW-01-N (CQ-NEW-01, nonconforming)

resource "google_storage_bucket" "fx_new_01_n_x_c" {
  name                        = "${var.run_id}-fx-new-01-n-x-c"
  location                    = "NAM4"
  force_destroy               = true
  uniform_bucket_level_access = true
  rpo                         = "ASYNC_TURBO"
}

# ==== FX-NEW-01-I (CQ-NEW-01, incomplete)

resource "google_storage_bucket" "fx_new_01_i_x_c" {
  name                        = "${var.run_id}-fx-new-01-i-x-c"
  location                    = var.location_1
  force_destroy               = true
  uniform_bucket_level_access = true
  ip_filter {
    mode = "Disabled"
  }
}

# ==== FX-NEW-02-C (CQ-NEW-02, conforming)

resource "google_compute_network" "fx_new_02_c_x_net_a" {
  name                    = "${var.run_id}-fx-new-02-c-x-net-a"
  auto_create_subnetworks = false
}

resource "google_compute_network" "fx_new_02_c_x_net_b" {
  name                    = "${var.run_id}-fx-new-02-c-netb"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "fx_new_02_c_x_sub_a" {
  name          = "${var.run_id}-fx-new-02-c-x-sub-a"
  network       = google_compute_network.fx_new_02_c_x_net_a.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

resource "google_compute_subnetwork" "fx_new_02_c_x_sub_b" {
  name          = "${var.run_id}-fx-new-02-c-subb"
  network       = google_compute_network.fx_new_02_c_x_net_b.id
  ip_cidr_range = "10.21.1.0/24"
  region        = var.location_1
}

resource "google_compute_instance" "fx_new_02_c_vm1" {
  name         = "${var.run_id}-fx-new-02-c-vm1"
  machine_type = "e2-micro"
  zone         = "${var.location_1}-a"
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.fx_new_02_c_x_sub_a.id
  }
  network_interface {
    subnetwork = google_compute_subnetwork.fx_new_02_c_x_sub_b.id
  }
}

# ==== FX-NEW-02-N (CQ-NEW-02, nonconforming)

resource "google_compute_network" "fx_new_02_n_x_net_a" {
  name                    = "${var.run_id}-fx-new-02-n-x-net-a"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "fx_new_02_n_x_sub_a" {
  name          = "${var.run_id}-fx-new-02-n-x-sub-a"
  network       = google_compute_network.fx_new_02_n_x_net_a.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

resource "google_compute_instance" "fx_new_02_n_vm1" {
  name         = "${var.run_id}-fx-new-02-n-vm1"
  machine_type = "e2-micro"
  zone         = "${var.location_1}-a"
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.fx_new_02_n_x_sub_a.id
    alias_ip_range {
      ip_cidr_range = "/32"
    }
  }
}

# ==== FX-NEW-02-I (CQ-NEW-02, incomplete)

variable "fx_new_02_i_extra_interfaces" {
  type        = list(string)
  description = "entrada simbólica da fixture FX-NEW-02-I; sem valor de propósito"
}

resource "google_compute_network" "fx_new_02_i_x_net_a" {
  name                    = "${var.run_id}-fx-new-02-i-x-net-a"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "fx_new_02_i_x_sub_a" {
  name          = "${var.run_id}-fx-new-02-i-x-sub-a"
  network       = google_compute_network.fx_new_02_i_x_net_a.id
  ip_cidr_range = "10.20.1.0/24"
  region        = var.location_1
}

resource "google_compute_instance" "fx_new_02_i_vm1" {
  name         = "${var.run_id}-fx-new-02-i-vm1"
  machine_type = "e2-micro"
  zone         = "${var.location_1}-a"
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.fx_new_02_i_x_sub_a.id
  }
  dynamic "network_interface" {
    for_each = var.fx_new_02_i_extra_interfaces
    content {
      subnetwork = network_interface.value
    }
  }
}

# ==== FX-NEW-03-C (CQ-NEW-03, conforming)

resource "google_compute_network" "fx_new_03_c_x_net" {
  name                    = "${var.run_id}-fx-new-03-c-x-net"
  auto_create_subnetworks = false
}

resource "google_compute_firewall" "fx_new_03_c_r1" {
  name          = "${var.run_id}-fx-new-03-c-r1"
  network       = google_compute_network.fx_new_03_c_x_net.id
  direction     = "INGRESS"
  priority      = 100
  source_ranges = ["0.0.0.0/0"]
  deny {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# ==== FX-NEW-03-N (CQ-NEW-03, nonconforming): NOT_APPLICABLE — o GCP não tem conjunto de regras de filtragem com precedência pela posição textual: toda precedência é numérica

# ==== FX-NEW-03-I (CQ-NEW-03, incomplete)

variable "fx_new_03_i_network" {
  type        = string
  description = "entrada simbólica da fixture FX-NEW-03-I; sem valor de propósito"
}

resource "google_compute_network_firewall_policy" "fx_new_03_i_rs1" {
  name = "${var.run_id}-fx-new-03-i-rs1"
}

resource "google_compute_network_firewall_policy_rule" "fx_new_03_i_r1" {
  firewall_policy = google_compute_network_firewall_policy.fx_new_03_i_rs1.name
  priority        = 100
  action          = "deny"
  direction       = "INGRESS"
  match {
    src_ip_ranges = ["0.0.0.0/0"]
    layer4_configs {
      ip_protocol = "tcp"
      ports       = ["22"]
    }
  }
}

resource "google_compute_network_firewall_policy_association" "fx_new_03_i_x_assoc" {
  name              = "${var.run_id}-fx-new-03-i-assoc"
  firewall_policy   = google_compute_network_firewall_policy.fx_new_03_i_rs1.name
  attachment_target = var.fx_new_03_i_network
}
