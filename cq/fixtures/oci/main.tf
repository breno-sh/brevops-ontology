# Fixtures das CQs (CQFIX) no provider oci — gerado por bo.cqfix.build; não editar.
# Cada seção é uma fixture (FX-...) e só ela; o conjunto de endereços de cada uma está em
# expected_answers.json. Valores reais (conta, região, projeto) nunca entram: vêm das variáveis
# de contexto, ligadas pelo runner do DEP. Variáveis fx_* sem valor são entradas simbólicas de
# fixtures incompletas, de propósito.

terraform {
  required_version = "= 1.15.8"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "= 9.11.0"
    }
  }
}

provider "oci" {
  region = var.location_1
}

provider "oci" {
  alias  = "loc2"
  region = var.location_2
}

variable "run_id" {
  type        = string
  description = "identificador curto da execução (prefixo de nomes e tag bo_run); ligado pelo runner"
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

variable "tenancy_ocid" {
  type        = string
  description = "tenancy sandbox (raiz: fontes de rede, domínio de identidade); ligado pelo runner, nunca gravado"
}

variable "compartment_ocid" {
  type        = string
  description = "compartimento da execução (todo recurso nasce nele ou abaixo dele); ligado pelo runner"
}

variable "idcs_endpoint" {
  type        = string
  description = "URL do domínio de identidade da tenancy sandbox; ligada pelo runner"
}

variable "ssh_public_key" {
  type        = string
  description = "chave pública SSH gerada pelo runner (só a pública; exigida pelo DB system)"
}

variable "db_admin_password" {
  type        = string
  description = "senha de administrador gerada na hora pelo runner; Withheld, nunca gravada"
  sensitive   = true
}

# ==== FX-CIS-01-C (CQ-CIS-01, conforming)

resource "oci_identity_user" "fx_cis_01_c_u1" {
  compartment_id = var.tenancy_ocid
  name           = "${var.run_id}-fx-cis-01-c-u1"
  description    = "${var.run_id} FX-CIS-01-C"
}

resource "oci_identity_domains_authentication_factor_setting" "fx_cis_01_c_d1" {
  idcs_endpoint                    = var.idcs_endpoint
  authentication_factor_setting_id = "AuthenticationFactorSettings"
  schemas                          = ["urn:ietf:params:scim:schemas:oracle:idcs:AuthenticationFactorSettings"]
  bypass_code_enabled              = false
  push_enabled                     = false
  security_questions_enabled       = false
  sms_enabled                      = false
  totp_enabled                     = true
  mfa_enrollment_type              = "Required"
  bypass_code_settings {
    help_desk_code_expiry_in_mins   = 60
    help_desk_generation_enabled    = false
    help_desk_max_usage             = 1
    length                          = 12
    max_active                      = 5
    self_service_generation_enabled = false
  }
  client_app_settings {
    device_protection_policy            = "NONE"
    initial_lockout_period_in_secs      = 30
    key_pair_length                     = 2048
    lockout_escalation_pattern          = "Constant"
    max_failures_before_lockout         = 10
    max_failures_before_warning         = 5
    max_lockout_interval_in_secs        = 86400
    min_pin_length                      = 6
    policy_update_freq_in_days          = 4
    request_signing_algo                = "SHA256withRSA"
    shared_secret_encoding              = "Base32"
    unlock_app_for_each_request_enabled = false
    unlock_app_interval_in_secs         = 300
    unlock_on_app_foreground_enabled    = false
    unlock_on_app_start_enabled         = false
  }
  compliance_policy {
    action = "Allow"
    name   = "lockScreenRequired"
    value  = "false"
  }
  endpoint_restrictions {
    max_endpoint_trust_duration_in_days = 180
    max_enrolled_devices                = 10
    max_incorrect_attempts              = 20
    max_trusted_endpoints               = 20
    trusted_endpoints_enabled           = true
  }
  notification_settings {
    pull_enabled = false
  }
  totp_settings {
    email_otp_validity_duration_in_mins = 10
    email_passcode_length               = 6
    hashing_algorithm                   = "SHA1"
    jwt_validity_duration_in_secs       = 300
    key_refresh_interval_in_days        = 60
    passcode_length                     = 6
    sms_otp_validity_duration_in_mins   = 10
    sms_passcode_length                 = 6
    time_step_in_secs                   = 30
    time_step_tolerance                 = 3
  }
}

# ==== FX-CIS-01-N (CQ-CIS-01, nonconforming)

resource "oci_identity_user" "fx_cis_01_n_u1" {
  compartment_id = var.tenancy_ocid
  name           = "${var.run_id}-fx-cis-01-n-u1"
  description    = "${var.run_id} FX-CIS-01-N"
}

resource "oci_identity_domains_authentication_factor_setting" "fx_cis_01_n_d1" {
  idcs_endpoint                    = var.idcs_endpoint
  authentication_factor_setting_id = "AuthenticationFactorSettings"
  schemas                          = ["urn:ietf:params:scim:schemas:oracle:idcs:AuthenticationFactorSettings"]
  bypass_code_enabled              = false
  push_enabled                     = false
  security_questions_enabled       = false
  sms_enabled                      = false
  totp_enabled                     = true
  mfa_enrollment_type              = "Optional"
  bypass_code_settings {
    help_desk_code_expiry_in_mins   = 60
    help_desk_generation_enabled    = false
    help_desk_max_usage             = 1
    length                          = 12
    max_active                      = 5
    self_service_generation_enabled = false
  }
  client_app_settings {
    device_protection_policy            = "NONE"
    initial_lockout_period_in_secs      = 30
    key_pair_length                     = 2048
    lockout_escalation_pattern          = "Constant"
    max_failures_before_lockout         = 10
    max_failures_before_warning         = 5
    max_lockout_interval_in_secs        = 86400
    min_pin_length                      = 6
    policy_update_freq_in_days          = 4
    request_signing_algo                = "SHA256withRSA"
    shared_secret_encoding              = "Base32"
    unlock_app_for_each_request_enabled = false
    unlock_app_interval_in_secs         = 300
    unlock_on_app_foreground_enabled    = false
    unlock_on_app_start_enabled         = false
  }
  compliance_policy {
    action = "Allow"
    name   = "lockScreenRequired"
    value  = "false"
  }
  endpoint_restrictions {
    max_endpoint_trust_duration_in_days = 180
    max_enrolled_devices                = 10
    max_incorrect_attempts              = 20
    max_trusted_endpoints               = 20
    trusted_endpoints_enabled           = true
  }
  notification_settings {
    pull_enabled = false
  }
  totp_settings {
    email_otp_validity_duration_in_mins = 10
    email_passcode_length               = 6
    hashing_algorithm                   = "SHA1"
    jwt_validity_duration_in_secs       = 300
    key_refresh_interval_in_days        = 60
    passcode_length                     = 6
    sms_otp_validity_duration_in_mins   = 10
    sms_passcode_length                 = 6
    time_step_in_secs                   = 30
    time_step_tolerance                 = 3
  }
}

# ==== FX-CIS-01-I (CQ-CIS-01, incomplete)

variable "fx_cis_01_i_mfa_enrollment_type" {
  type        = string
  description = "entrada simbólica da fixture FX-CIS-01-I; sem valor de propósito"
}

resource "oci_identity_user" "fx_cis_01_i_u1" {
  compartment_id = var.tenancy_ocid
  name           = "${var.run_id}-fx-cis-01-i-u1"
  description    = "${var.run_id} FX-CIS-01-I"
}

resource "oci_identity_domains_authentication_factor_setting" "fx_cis_01_i_d1" {
  idcs_endpoint                    = var.idcs_endpoint
  authentication_factor_setting_id = "AuthenticationFactorSettings"
  schemas                          = ["urn:ietf:params:scim:schemas:oracle:idcs:AuthenticationFactorSettings"]
  bypass_code_enabled              = false
  push_enabled                     = false
  security_questions_enabled       = false
  sms_enabled                      = false
  totp_enabled                     = true
  mfa_enrollment_type              = var.fx_cis_01_i_mfa_enrollment_type
  bypass_code_settings {
    help_desk_code_expiry_in_mins   = 60
    help_desk_generation_enabled    = false
    help_desk_max_usage             = 1
    length                          = 12
    max_active                      = 5
    self_service_generation_enabled = false
  }
  client_app_settings {
    device_protection_policy            = "NONE"
    initial_lockout_period_in_secs      = 30
    key_pair_length                     = 2048
    lockout_escalation_pattern          = "Constant"
    max_failures_before_lockout         = 10
    max_failures_before_warning         = 5
    max_lockout_interval_in_secs        = 86400
    min_pin_length                      = 6
    policy_update_freq_in_days          = 4
    request_signing_algo                = "SHA256withRSA"
    shared_secret_encoding              = "Base32"
    unlock_app_for_each_request_enabled = false
    unlock_app_interval_in_secs         = 300
    unlock_on_app_foreground_enabled    = false
    unlock_on_app_start_enabled         = false
  }
  compliance_policy {
    action = "Allow"
    name   = "lockScreenRequired"
    value  = "false"
  }
  endpoint_restrictions {
    max_endpoint_trust_duration_in_days = 180
    max_enrolled_devices                = 10
    max_incorrect_attempts              = 20
    max_trusted_endpoints               = 20
    trusted_endpoints_enabled           = true
  }
  notification_settings {
    pull_enabled = false
  }
  totp_settings {
    email_otp_validity_duration_in_mins = 10
    email_passcode_length               = 6
    hashing_algorithm                   = "SHA1"
    jwt_validity_duration_in_secs       = 300
    key_refresh_interval_in_days        = 60
    passcode_length                     = 6
    sms_otp_validity_duration_in_mins   = 10
    sms_passcode_length                 = 6
    time_step_in_secs                   = 30
    time_step_tolerance                 = 3
  }
}

# ==== FX-CIS-02-C (CQ-CIS-02, conforming)

resource "oci_identity_user" "fx_cis_02_c_p1" {
  compartment_id = var.tenancy_ocid
  name           = "${var.run_id}-fx-cis-02-c-p1"
  description    = "${var.run_id} FX-CIS-02-C"
}

resource "oci_identity_auth_token" "fx_cis_02_c_k1" {
  user_id     = oci_identity_user.fx_cis_02_c_p1.id
  description = "${var.run_id} FX-CIS-02-C"
}

# ==== FX-CIS-02-N (CQ-CIS-02, nonconforming)

resource "oci_identity_user" "fx_cis_02_n_p1" {
  compartment_id = var.tenancy_ocid
  name           = "${var.run_id}-fx-cis-02-n-p1"
  description    = "${var.run_id} FX-CIS-02-N"
}

resource "oci_identity_auth_token" "fx_cis_02_n_k1" {
  user_id     = oci_identity_user.fx_cis_02_n_p1.id
  description = "${var.run_id} FX-CIS-02-N"
}

# ==== FX-CIS-02-I (CQ-CIS-02, incomplete)

resource "oci_identity_user" "fx_cis_02_i_p1" {
  compartment_id = var.tenancy_ocid
  name           = "${var.run_id}-fx-cis-02-i-p1"
  description    = "${var.run_id} FX-CIS-02-I"
}

resource "oci_identity_auth_token" "fx_cis_02_i_k1" {
  user_id     = oci_identity_user.fx_cis_02_i_p1.id
  description = "${var.run_id} FX-CIS-02-I"
}

# ==== FX-CIS-03-C (CQ-CIS-03, conforming)

resource "oci_kms_vault" "fx_cis_03_c_x_vault" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.run_id}-fx-cis-03-c-vault"
  vault_type     = "DEFAULT"
}

resource "oci_kms_key" "fx_cis_03_c_k1" {
  compartment_id           = var.compartment_ocid
  display_name             = "${var.run_id}-fx-cis-03-c-k1"
  management_endpoint      = oci_kms_vault.fx_cis_03_c_x_vault.management_endpoint
  protection_mode          = "SOFTWARE"
  is_auto_rotation_enabled = true
  key_shape {
    algorithm = "AES"
    length    = 32
  }
  auto_key_rotation_details {
    rotation_interval_in_days = 90
  }
}

# ==== FX-CIS-03-N (CQ-CIS-03, nonconforming)

resource "oci_kms_vault" "fx_cis_03_n_x_vault" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.run_id}-fx-cis-03-n-vault"
  vault_type     = "DEFAULT"
}

resource "oci_kms_key" "fx_cis_03_n_k1" {
  compartment_id           = var.compartment_ocid
  display_name             = "${var.run_id}-fx-cis-03-n-k1"
  management_endpoint      = oci_kms_vault.fx_cis_03_n_x_vault.management_endpoint
  protection_mode          = "SOFTWARE"
  is_auto_rotation_enabled = false
  key_shape {
    algorithm = "AES"
    length    = 32
  }
}

# ==== FX-CIS-03-I (CQ-CIS-03, incomplete)

variable "fx_cis_03_i_rotation" {
  type        = bool
  description = "entrada simbólica da fixture FX-CIS-03-I; sem valor de propósito"
}

resource "oci_kms_vault" "fx_cis_03_i_x_vault" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.run_id}-fx-cis-03-i-vault"
  vault_type     = "DEFAULT"
}

resource "oci_kms_key" "fx_cis_03_i_k1" {
  compartment_id           = var.compartment_ocid
  display_name             = "${var.run_id}-fx-cis-03-i-k1"
  management_endpoint      = oci_kms_vault.fx_cis_03_i_x_vault.management_endpoint
  protection_mode          = "SOFTWARE"
  is_auto_rotation_enabled = var.fx_cis_03_i_rotation
  key_shape {
    algorithm = "AES"
    length    = 32
  }
}

# ==== FX-CIS-04-C (CQ-CIS-04, conforming)

resource "oci_core_vcn" "fx_cis_04_c_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-cis-04-c-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_security_list" "fx_cis_04_c_rs1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_cis_04_c_x_vcn.id
  display_name   = "${var.run_id}-fx-cis-04-c-rs1"
  ingress_security_rules {
    protocol    = "6"
    source      = "203.0.113.0/24"
    source_type = "CIDR_BLOCK"
    tcp_options {
      min = 22
      max = 22
    }
  }
}

# ==== FX-CIS-04-N (CQ-CIS-04, nonconforming)

resource "oci_core_vcn" "fx_cis_04_n_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-cis-04-n-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_security_list" "fx_cis_04_n_rs1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_cis_04_n_x_vcn.id
  display_name   = "${var.run_id}-fx-cis-04-n-rs1"
  ingress_security_rules {
    protocol    = "6"
    source      = "0.0.0.0/0"
    source_type = "CIDR_BLOCK"
    tcp_options {
      min = 22
      max = 22
    }
  }
}

# ==== FX-CIS-04-I (CQ-CIS-04, incomplete)

variable "fx_cis_04_i_source_cidr" {
  type        = string
  description = "entrada simbólica da fixture FX-CIS-04-I; sem valor de propósito"
}

resource "oci_core_vcn" "fx_cis_04_i_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-cis-04-i-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_security_list" "fx_cis_04_i_rs1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_cis_04_i_x_vcn.id
  display_name   = "${var.run_id}-fx-cis-04-i-rs1"
  ingress_security_rules {
    protocol    = "6"
    source      = var.fx_cis_04_i_source_cidr
    source_type = "CIDR_BLOCK"
    tcp_options {
      min = 22
      max = 22
    }
  }
}

# ==== FX-CIS-05-C (CQ-CIS-05, conforming)

resource "oci_core_vcn" "fx_cis_05_c_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-cis-05-c-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_security_list" "fx_cis_05_c_rs1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_cis_05_c_x_vcn.id
  display_name   = "${var.run_id}-fx-cis-05-c-rs1"
  ingress_security_rules {
    protocol    = "6"
    source      = "203.0.113.0/24"
    source_type = "CIDR_BLOCK"
    tcp_options {
      min = 3389
      max = 3389
    }
  }
}

# ==== FX-CIS-05-N (CQ-CIS-05, nonconforming)

resource "oci_core_vcn" "fx_cis_05_n_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-cis-05-n-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_security_list" "fx_cis_05_n_rs1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_cis_05_n_x_vcn.id
  display_name   = "${var.run_id}-fx-cis-05-n-rs1"
  ingress_security_rules {
    protocol    = "6"
    source      = "0.0.0.0/0"
    source_type = "CIDR_BLOCK"
    tcp_options {
      min = 3389
      max = 3389
    }
  }
}

# ==== FX-CIS-05-I (CQ-CIS-05, incomplete)

variable "fx_cis_05_i_source_cidr" {
  type        = string
  description = "entrada simbólica da fixture FX-CIS-05-I; sem valor de propósito"
}

resource "oci_core_vcn" "fx_cis_05_i_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-cis-05-i-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_security_list" "fx_cis_05_i_rs1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_cis_05_i_x_vcn.id
  display_name   = "${var.run_id}-fx-cis-05-i-rs1"
  ingress_security_rules {
    protocol    = "6"
    source      = var.fx_cis_05_i_source_cidr
    source_type = "CIDR_BLOCK"
    tcp_options {
      min = 3389
      max = 3389
    }
  }
}

# ==== FX-CIS-06-C (CQ-CIS-06, conforming)

resource "oci_core_vcn" "fx_cis_06_c_vn1" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-cis-06-c-vn1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_subnet" "fx_cis_06_c_sa" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_cis_06_c_vn1.id
  cidr_block     = "10.30.1.0/24"
  display_name   = "${var.run_id}-fx-cis-06-c-sa"
}

resource "oci_logging_log_group" "fx_cis_06_c_x_flowlogs" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.run_id}-fx-cis-06-c-flowlogs"
}

resource "oci_logging_log" "fx_cis_06_c_d1" {
  display_name = "${var.run_id}-fx-cis-06-c-d1"
  log_group_id = oci_logging_log_group.fx_cis_06_c_x_flowlogs.id
  log_type     = "SERVICE"
  is_enabled   = true
  configuration {
    compartment_id = var.compartment_ocid
    source {
      category    = "all"
      resource    = oci_core_subnet.fx_cis_06_c_sa.id
      service     = "flowlogs"
      source_type = "OCISERVICE"
    }
  }
}

# ==== FX-CIS-06-N (CQ-CIS-06, nonconforming)

resource "oci_core_vcn" "fx_cis_06_n_vn1" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-cis-06-n-vn1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_subnet" "fx_cis_06_n_sa" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_cis_06_n_vn1.id
  cidr_block     = "10.30.1.0/24"
  display_name   = "${var.run_id}-fx-cis-06-n-sa"
}

# ==== FX-CIS-06-I (CQ-CIS-06, incomplete)

variable "fx_cis_06_i_flow_log_enabled" {
  type        = bool
  description = "entrada simbólica da fixture FX-CIS-06-I; sem valor de propósito"
}

resource "oci_core_vcn" "fx_cis_06_i_vn1" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-cis-06-i-vn1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_subnet" "fx_cis_06_i_sa" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_cis_06_i_vn1.id
  cidr_block     = "10.30.1.0/24"
  display_name   = "${var.run_id}-fx-cis-06-i-sa"
}

resource "oci_logging_log_group" "fx_cis_06_i_x_flowlogs" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.run_id}-fx-cis-06-i-flowlogs"
}

resource "oci_logging_log" "fx_cis_06_i_d1" {
  display_name = "${var.run_id}-fx-cis-06-i-d1"
  log_group_id = oci_logging_log_group.fx_cis_06_i_x_flowlogs.id
  log_type     = "SERVICE"
  is_enabled   = var.fx_cis_06_i_flow_log_enabled
  configuration {
    compartment_id = var.compartment_ocid
    source {
      category    = "all"
      resource    = oci_core_subnet.fx_cis_06_i_sa.id
      service     = "flowlogs"
      source_type = "OCISERVICE"
    }
  }
}

# ==== FX-CIS-07-C (CQ-CIS-07, conforming)

resource "oci_ons_notification_topic" "fx_cis_07_c_t1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-cis-07-c-t1"
}

resource "oci_events_rule" "fx_cis_07_c_al1" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.run_id}-fx-cis-07-c-al1"
  is_enabled     = true
  condition = jsonencode({
    eventType = [
      "com.oraclecloud.virtualnetwork.createsecuritylist",
      "com.oraclecloud.virtualnetwork.updatesecuritylist",
      "com.oraclecloud.virtualnetwork.deletesecuritylist",
      "com.oraclecloud.virtualnetwork.changesecuritylistcompartment",
    ]
  })
  actions {
    actions {
      action_type = "ONS"
      is_enabled  = true
      topic_id    = oci_ons_notification_topic.fx_cis_07_c_t1.id
    }
  }
}

# ==== FX-CIS-07-N (CQ-CIS-07, nonconforming)

resource "oci_ons_notification_topic" "fx_cis_07_n_t1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-cis-07-n-t1"
}

resource "oci_events_rule" "fx_cis_07_n_al1" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.run_id}-fx-cis-07-n-al1"
  is_enabled     = true
  condition = jsonencode({
    eventType = [
      "com.oraclecloud.virtualnetwork.createroutetable",
      "com.oraclecloud.virtualnetwork.updateroutetable",
      "com.oraclecloud.virtualnetwork.deleteroutetable",
      "com.oraclecloud.virtualnetwork.changeroutetablecompartment",
    ]
  })
  actions {
    actions {
      action_type = "ONS"
      is_enabled  = true
      topic_id    = oci_ons_notification_topic.fx_cis_07_n_t1.id
    }
  }
}

# ==== FX-CIS-07-I (CQ-CIS-07, incomplete)

variable "fx_cis_07_i_event_condition" {
  type        = string
  description = "entrada simbólica da fixture FX-CIS-07-I; sem valor de propósito"
}

resource "oci_ons_notification_topic" "fx_cis_07_i_t1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-cis-07-i-t1"
}

resource "oci_events_rule" "fx_cis_07_i_al1" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.run_id}-fx-cis-07-i-al1"
  is_enabled     = true
  condition      = var.fx_cis_07_i_event_condition
  actions {
    actions {
      action_type = "ONS"
      is_enabled  = true
      topic_id    = oci_ons_notification_topic.fx_cis_07_i_t1.id
    }
  }
}

# ==== FX-CIS-08-C (CQ-CIS-08, conforming)

data "oci_objectstorage_namespace" "fx_cis_08_c_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_cis_08_c_c1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-cis-08-c-c1"
  namespace      = data.oci_objectstorage_namespace.fx_cis_08_c_x_ns.namespace
  access_type    = "NoPublicAccess"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-CIS-08-N (CQ-CIS-08, nonconforming)

data "oci_objectstorage_namespace" "fx_cis_08_n_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_cis_08_n_c1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-cis-08-n-c1"
  namespace      = data.oci_objectstorage_namespace.fx_cis_08_n_x_ns.namespace
  access_type    = "ObjectRead"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-CIS-08-I (CQ-CIS-08, incomplete)

variable "fx_cis_08_i_access_type" {
  type        = string
  description = "entrada simbólica da fixture FX-CIS-08-I; sem valor de propósito"
}

data "oci_objectstorage_namespace" "fx_cis_08_i_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_cis_08_i_c1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-cis-08-i-c1"
  namespace      = data.oci_objectstorage_namespace.fx_cis_08_i_x_ns.namespace
  access_type    = var.fx_cis_08_i_access_type
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-IDL-01-C (CQ-IDL-01, conforming)

data "oci_objectstorage_namespace" "fx_idl_01_c_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_idl_01_c_c1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-idl-01-c-data-a"
  namespace      = data.oci_objectstorage_namespace.fx_idl_01_c_x_ns.namespace
  versioning     = "Enabled"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-IDL-01-N (CQ-IDL-01, nonconforming)

data "oci_objectstorage_namespace" "fx_idl_01_n_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_idl_01_n_c2" {
  provider       = oci.loc2
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-idl-01-n-data-a"
  namespace      = data.oci_objectstorage_namespace.fx_idl_01_n_x_ns.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-IDL-01-I (CQ-IDL-01, incomplete)

data "oci_objectstorage_namespace" "fx_idl_01_i_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_idl_01_i_c1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-idl-01-i-data-a"
  namespace      = data.oci_objectstorage_namespace.fx_idl_01_i_x_ns.namespace
  storage_tier   = "Archive"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-IDL-02-C (CQ-IDL-02, conforming)

data "oci_objectstorage_namespace" "fx_idl_02_c_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_idl_02_c_c1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-idl-02-c-data"
  namespace      = data.oci_objectstorage_namespace.fx_idl_02_c_x_ns.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_objectstorage_bucket" "fx_idl_02_c_c2" {
  provider       = oci.loc2
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-idl-02-c-data"
  namespace      = data.oci_objectstorage_namespace.fx_idl_02_c_x_ns.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-IDL-02-N (CQ-IDL-02, nonconforming)

data "oci_objectstorage_namespace" "fx_idl_02_n_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_idl_02_n_c1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-idl-02-n-data"
  namespace      = data.oci_objectstorage_namespace.fx_idl_02_n_x_ns.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

data "oci_objectstorage_bucket" "fx_idl_02_n_c2" {
  name      = oci_objectstorage_bucket.fx_idl_02_n_c1.name
  namespace = data.oci_objectstorage_namespace.fx_idl_02_n_x_ns.namespace
}

# ==== FX-IDL-02-I (CQ-IDL-02, incomplete)

variable "fx_idl_02_i_c2_location" {
  type        = string
  description = "região do contêiner c2 da fixture FX-IDL-02-I; não lida, sem valor de propósito"
}

data "oci_objectstorage_namespace" "fx_idl_02_i_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_idl_02_i_c1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-idl-02-i-data"
  namespace      = data.oci_objectstorage_namespace.fx_idl_02_i_x_ns.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-IDL-03-C (CQ-IDL-03, conforming)

resource "oci_identity_group" "fx_idl_03_c_p1" {
  compartment_id = var.tenancy_ocid
  name           = "${var.run_id}-fx-idl-03-c-p1"
  description    = "${var.run_id} FX-IDL-03-C"
}

resource "oci_identity_policy" "fx_idl_03_c_a1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-idl-03-c-a1"
  description    = "${var.run_id} FX-IDL-03-C"
  statements = [
    "Allow group ${oci_identity_group.fx_idl_03_c_p1.name} to read buckets in compartment id ${var.compartment_ocid}",
  ]
}

# ==== FX-IDL-03-N (CQ-IDL-03, nonconforming)

data "oci_objectstorage_namespace" "fx_idl_03_n_ns1" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_idl_03_n_c1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-idl-03-n-c1"
  namespace      = data.oci_objectstorage_namespace.fx_idl_03_n_ns1.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-IDL-03-I (CQ-IDL-03, incomplete)

data "oci_objectstorage_namespace" "fx_idl_03_i_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_idl_03_i_c1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-idl-03-i-c1"
  namespace      = data.oci_objectstorage_namespace.fx_idl_03_i_x_ns.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_objectstorage_object_lifecycle_policy" "fx_idl_03_i_s1" {
  bucket    = oci_objectstorage_bucket.fx_idl_03_i_c1.name
  namespace = data.oci_objectstorage_namespace.fx_idl_03_i_x_ns.namespace
  rules {
    action      = "DELETE"
    is_enabled  = true
    name        = "retention"
    target      = "objects"
    time_amount = "30"
    time_unit   = "DAYS"
  }
}

# ==== FX-IDL-04-C (CQ-IDL-04, conforming)

resource "oci_core_vcn" "fx_idl_04_c_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-idl-04-c-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_security_list" "fx_idl_04_c_rs1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_idl_04_c_x_vcn.id
  display_name   = "${var.run_id}-fx-idl-04-c-rs1"
  ingress_security_rules {
    protocol    = "6"
    source      = "203.0.113.0/24"
    source_type = "CIDR_BLOCK"
    tcp_options {
      min = 22
      max = 22
    }
  }
  ingress_security_rules {
    protocol    = "6"
    source      = "203.0.113.0/24"
    source_type = "CIDR_BLOCK"
    tcp_options {
      min = 443
      max = 443
    }
  }
}

# ==== FX-IDL-04-N (CQ-IDL-04, nonconforming)

resource "oci_core_vcn" "fx_idl_04_n_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-idl-04-n-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_security_list" "fx_idl_04_n_rs1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_idl_04_n_x_vcn.id
  display_name   = "${var.run_id}-fx-idl-04-n-rs1"
  ingress_security_rules {
    protocol    = "6"
    source      = "203.0.113.0/24"
    source_type = "CIDR_BLOCK"
    tcp_options {
      min = 8443
      max = 8443
    }
  }
  ingress_security_rules {
    protocol    = "6"
    source      = "203.0.113.0/24"
    source_type = "CIDR_BLOCK"
    tcp_options {
      min = 22
      max = 22
    }
  }
}

# ==== FX-IDL-04-I (CQ-IDL-04, incomplete)

variable "fx_idl_04_i_r1_port" {
  type        = number
  description = "entrada simbólica da fixture FX-IDL-04-I; sem valor de propósito"
}

resource "oci_core_vcn" "fx_idl_04_i_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-idl-04-i-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_security_list" "fx_idl_04_i_rs1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_idl_04_i_x_vcn.id
  display_name   = "${var.run_id}-fx-idl-04-i-rs1"
  ingress_security_rules {
    protocol    = "6"
    source      = "203.0.113.0/24"
    source_type = "CIDR_BLOCK"
    tcp_options {
      min = var.fx_idl_04_i_r1_port
      max = var.fx_idl_04_i_r1_port
    }
  }
  ingress_security_rules {
    protocol    = "6"
    source      = "203.0.113.0/24"
    source_type = "CIDR_BLOCK"
    tcp_options {
      min = 22
      max = 22
    }
  }
}

# ==== FX-CMP-01-C (CQ-CMP-01, conforming)

resource "oci_core_vcn" "fx_cmp_01_c_vn1" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-cmp-01-c-vn1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_subnet" "fx_cmp_01_c_sa" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_cmp_01_c_vn1.id
  cidr_block     = "10.30.1.0/24"
  display_name   = "${var.run_id}-fx-cmp-01-c-sa"
}

data "oci_core_images" "fx_cmp_01_c_x_img" {
  compartment_id   = var.compartment_ocid
  operating_system = "Oracle Linux"
  shape            = "VM.Standard.E2.1.Micro"
  sort_by          = "TIMECREATED"
  sort_order       = "DESC"
}

data "oci_identity_availability_domains" "fx_cmp_01_c_x_ads" {
  compartment_id = var.compartment_ocid
}

resource "oci_core_instance" "fx_cmp_01_c_vm1" {
  availability_domain = data.oci_identity_availability_domains.fx_cmp_01_c_x_ads.availability_domains[0].name
  compartment_id      = var.compartment_ocid
  shape               = "VM.Standard.E2.1.Micro"
  display_name        = "${var.run_id}-fx-cmp-01-c-vm1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_cmp_01_c_sa.id
    assign_public_ip = "false"
    display_name     = "${var.run_id}-fx-cmp-01-c-vm1-vnic0"
  }
  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.fx_cmp_01_c_x_img.images[0].id
  }
}

# ==== FX-CMP-01-N (CQ-CMP-01, nonconforming)

resource "oci_core_vcn" "fx_cmp_01_n_vn1" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-cmp-01-n-vn1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

data "oci_core_images" "fx_cmp_01_n_x_img" {
  compartment_id   = var.compartment_ocid
  operating_system = "Oracle Linux"
  shape            = "VM.Standard.E2.1.Micro"
  sort_by          = "TIMECREATED"
  sort_order       = "DESC"
}

data "oci_identity_availability_domains" "fx_cmp_01_n_x_ads" {
  compartment_id = var.compartment_ocid
}

resource "oci_core_instance" "fx_cmp_01_n_vm1" {
  availability_domain = data.oci_identity_availability_domains.fx_cmp_01_n_x_ads.availability_domains[0].name
  compartment_id      = var.compartment_ocid
  shape               = "VM.Standard.E2.1.Micro"
  display_name        = "${var.run_id}-fx-cmp-01-n-vm1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  create_vnic_details {
    subnet_id        = "subnet-referenciada-ausente"
    assign_public_ip = "false"
    display_name     = "${var.run_id}-fx-cmp-01-n-vm1-vnic0"
  }
  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.fx_cmp_01_n_x_img.images[0].id
  }
}

# ==== FX-CMP-01-I (CQ-CMP-01, incomplete)

variable "fx_cmp_01_i_subnet_id" {
  type        = string
  description = "sub-rede externa da fixture FX-CMP-01-I; fora da leitura, sem valor de propósito"
}

data "oci_core_images" "fx_cmp_01_i_x_img" {
  compartment_id   = var.compartment_ocid
  operating_system = "Oracle Linux"
  shape            = "VM.Standard.E2.1.Micro"
  sort_by          = "TIMECREATED"
  sort_order       = "DESC"
}

data "oci_identity_availability_domains" "fx_cmp_01_i_x_ads" {
  compartment_id = var.compartment_ocid
}

resource "oci_core_instance" "fx_cmp_01_i_vm1" {
  availability_domain = data.oci_identity_availability_domains.fx_cmp_01_i_x_ads.availability_domains[0].name
  compartment_id      = var.compartment_ocid
  shape               = "VM.Standard.E2.1.Micro"
  display_name        = "${var.run_id}-fx-cmp-01-i-vm1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  create_vnic_details {
    subnet_id        = var.fx_cmp_01_i_subnet_id
    assign_public_ip = "false"
    display_name     = "${var.run_id}-fx-cmp-01-i-vm1-vnic0"
  }
  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.fx_cmp_01_i_x_img.images[0].id
  }
}

# ==== FX-CMP-02-C (CQ-CMP-02, conforming)

resource "oci_core_vcn" "fx_cmp_02_c_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-cmp-02-c-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_subnet" "fx_cmp_02_c_x_subnet" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_cmp_02_c_x_vcn.id
  cidr_block     = "10.30.1.0/24"
  display_name   = "${var.run_id}-fx-cmp-02-c-x-subnet"
}

data "oci_core_images" "fx_cmp_02_c_x_img_a1" {
  compartment_id   = var.compartment_ocid
  operating_system = "Oracle Linux"
  shape            = "VM.Standard.A1.Flex"
  sort_by          = "TIMECREATED"
  sort_order       = "DESC"
}

data "oci_identity_availability_domains" "fx_cmp_02_c_x_ads" {
  compartment_id = var.compartment_ocid
}

resource "oci_core_instance" "fx_cmp_02_c_vm1" {
  availability_domain = data.oci_identity_availability_domains.fx_cmp_02_c_x_ads.availability_domains[0].name
  compartment_id      = var.compartment_ocid
  shape               = "VM.Standard.A1.Flex"
  display_name        = "${var.run_id}-fx-cmp-02-c-vm1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_cmp_02_c_x_subnet.id
    assign_public_ip = "false"
    display_name     = "${var.run_id}-fx-cmp-02-c-vm1-vnic0"
  }
  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.fx_cmp_02_c_x_img_a1.images[0].id
  }
  shape_config {
    ocpus         = 1
    memory_in_gbs = 6
  }
}

resource "oci_core_vnic_attachment" "fx_cmp_02_c_nic2" {
  instance_id  = oci_core_instance.fx_cmp_02_c_vm1.id
  display_name = "${var.run_id}-fx-cmp-02-c-nic2-att"
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_cmp_02_c_x_subnet.id
    assign_public_ip = "false"
    display_name     = "${var.run_id}-fx-cmp-02-c-nic2"
  }
}

# ==== FX-CMP-02-N (CQ-CMP-02, nonconforming)

resource "oci_core_vcn" "fx_cmp_02_n_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-cmp-02-n-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_subnet" "fx_cmp_02_n_x_subnet" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_cmp_02_n_x_vcn.id
  cidr_block     = "10.30.1.0/24"
  display_name   = "${var.run_id}-fx-cmp-02-n-x-subnet"
}

data "oci_core_images" "fx_cmp_02_n_x_img" {
  compartment_id   = var.compartment_ocid
  operating_system = "Oracle Linux"
  shape            = "VM.Standard.E2.1.Micro"
  sort_by          = "TIMECREATED"
  sort_order       = "DESC"
}

data "oci_identity_availability_domains" "fx_cmp_02_n_x_ads" {
  compartment_id = var.compartment_ocid
}

resource "oci_core_instance" "fx_cmp_02_n_vm1" {
  availability_domain = data.oci_identity_availability_domains.fx_cmp_02_n_x_ads.availability_domains[0].name
  compartment_id      = var.compartment_ocid
  shape               = "VM.Standard.E2.1.Micro"
  display_name        = "${var.run_id}-fx-cmp-02-n-vm1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_cmp_02_n_x_subnet.id
    assign_public_ip = "false"
    display_name     = "${var.run_id}-fx-cmp-02-n-vm1-vnic0"
  }
  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.fx_cmp_02_n_x_img.images[0].id
  }
}

# ==== FX-CMP-02-I (CQ-CMP-02, incomplete)

variable "fx_cmp_02_i_nic2_instance_id" {
  type        = string
  description = "instância de anexação da VNIC nic2 da fixture FX-CMP-02-I; não lida"
}

resource "oci_core_vcn" "fx_cmp_02_i_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-cmp-02-i-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_subnet" "fx_cmp_02_i_x_subnet" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_cmp_02_i_x_vcn.id
  cidr_block     = "10.30.1.0/24"
  display_name   = "${var.run_id}-fx-cmp-02-i-x-subnet"
}

data "oci_core_images" "fx_cmp_02_i_x_img_a1" {
  compartment_id   = var.compartment_ocid
  operating_system = "Oracle Linux"
  shape            = "VM.Standard.A1.Flex"
  sort_by          = "TIMECREATED"
  sort_order       = "DESC"
}

data "oci_identity_availability_domains" "fx_cmp_02_i_x_ads" {
  compartment_id = var.compartment_ocid
}

resource "oci_core_instance" "fx_cmp_02_i_vm1" {
  availability_domain = data.oci_identity_availability_domains.fx_cmp_02_i_x_ads.availability_domains[0].name
  compartment_id      = var.compartment_ocid
  shape               = "VM.Standard.A1.Flex"
  display_name        = "${var.run_id}-fx-cmp-02-i-vm1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_cmp_02_i_x_subnet.id
    assign_public_ip = "false"
    display_name     = "${var.run_id}-fx-cmp-02-i-vm1-vnic0"
  }
  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.fx_cmp_02_i_x_img_a1.images[0].id
  }
  shape_config {
    ocpus         = 1
    memory_in_gbs = 6
  }
}

resource "oci_core_vnic_attachment" "fx_cmp_02_i_nic2" {
  instance_id  = var.fx_cmp_02_i_nic2_instance_id
  display_name = "${var.run_id}-fx-cmp-02-i-nic2-att"
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_cmp_02_i_x_subnet.id
    assign_public_ip = "false"
    display_name     = "${var.run_id}-fx-cmp-02-i-nic2"
  }
}

# ==== FX-CMP-03-C (CQ-CMP-03, conforming)

resource "oci_core_vcn" "fx_cmp_03_c_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-cmp-03-c-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_subnet" "fx_cmp_03_c_x_subnet" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_cmp_03_c_x_vcn.id
  cidr_block     = "10.30.1.0/24"
  display_name   = "${var.run_id}-fx-cmp-03-c-x-subnet"
}

resource "oci_load_balancer_load_balancer" "fx_cmp_03_c_lb1" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.run_id}-fx-cmp-03-c-lb1"
  shape          = "flexible"
  subnet_ids     = [oci_core_subnet.fx_cmp_03_c_x_subnet.id]
  is_private     = true
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  shape_details {
    minimum_bandwidth_in_mbps = 10
    maximum_bandwidth_in_mbps = 10
  }
}

resource "oci_load_balancer_backend_set" "fx_cmp_03_c_pool1" {
  load_balancer_id = oci_load_balancer_load_balancer.fx_cmp_03_c_lb1.id
  name             = "pool1"
  policy           = "ROUND_ROBIN"
  health_checker {
    protocol    = "HTTP"
    port        = 80
    url_path    = "/"
    return_code = 200
  }
}

resource "oci_load_balancer_load_balancer_routing_policy" "fx_cmp_03_c_ru1" {
  load_balancer_id           = oci_load_balancer_load_balancer.fx_cmp_03_c_lb1.id
  name                       = "ru1"
  condition_language_version = "V1"
  rules {
    name      = "any"
    condition = "any(http.request.url.path sw '/')"
    actions {
      name             = "FORWARD_TO_BACKENDSET"
      backend_set_name = oci_load_balancer_backend_set.fx_cmp_03_c_pool1.name
    }
  }
}

resource "oci_load_balancer_listener" "fx_cmp_03_c_li1" {
  load_balancer_id         = oci_load_balancer_load_balancer.fx_cmp_03_c_lb1.id
  name                     = "li1"
  port                     = 443
  protocol                 = "HTTP"
  default_backend_set_name = oci_load_balancer_backend_set.fx_cmp_03_c_pool1.name
  routing_policy_name      = oci_load_balancer_load_balancer_routing_policy.fx_cmp_03_c_ru1.name
}

data "oci_core_images" "fx_cmp_03_c_x_img" {
  compartment_id   = var.compartment_ocid
  operating_system = "Oracle Linux"
  shape            = "VM.Standard.E2.1.Micro"
  sort_by          = "TIMECREATED"
  sort_order       = "DESC"
}

data "oci_identity_availability_domains" "fx_cmp_03_c_x_ads" {
  compartment_id = var.compartment_ocid
}

resource "oci_core_instance" "fx_cmp_03_c_vm1" {
  availability_domain = data.oci_identity_availability_domains.fx_cmp_03_c_x_ads.availability_domains[0].name
  compartment_id      = var.compartment_ocid
  shape               = "VM.Standard.E2.1.Micro"
  display_name        = "${var.run_id}-fx-cmp-03-c-vm1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_cmp_03_c_x_subnet.id
    assign_public_ip = "false"
    display_name     = "${var.run_id}-fx-cmp-03-c-vm1-vnic0"
  }
  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.fx_cmp_03_c_x_img.images[0].id
  }
}

resource "oci_load_balancer_backend" "fx_cmp_03_c_x_member" {
  load_balancer_id = oci_load_balancer_load_balancer.fx_cmp_03_c_lb1.id
  backendset_name  = oci_load_balancer_backend_set.fx_cmp_03_c_pool1.name
  ip_address       = oci_core_instance.fx_cmp_03_c_vm1.private_ip
  port             = 80
}

# ==== FX-CMP-03-N (CQ-CMP-03, nonconforming)

resource "oci_core_vcn" "fx_cmp_03_n_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-cmp-03-n-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_subnet" "fx_cmp_03_n_x_subnet" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_cmp_03_n_x_vcn.id
  cidr_block     = "10.30.1.0/24"
  display_name   = "${var.run_id}-fx-cmp-03-n-x-subnet"
}

resource "oci_load_balancer_load_balancer" "fx_cmp_03_n_lb1" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.run_id}-fx-cmp-03-n-lb1"
  shape          = "flexible"
  subnet_ids     = [oci_core_subnet.fx_cmp_03_n_x_subnet.id]
  is_private     = true
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  shape_details {
    minimum_bandwidth_in_mbps = 10
    maximum_bandwidth_in_mbps = 10
  }
}

resource "oci_load_balancer_backend_set" "fx_cmp_03_n_pool1" {
  load_balancer_id = oci_load_balancer_load_balancer.fx_cmp_03_n_lb1.id
  name             = "pool1"
  policy           = "ROUND_ROBIN"
  health_checker {
    protocol    = "HTTP"
    port        = 80
    url_path    = "/"
    return_code = 200
  }
}

resource "oci_load_balancer_load_balancer_routing_policy" "fx_cmp_03_n_ru1" {
  load_balancer_id           = oci_load_balancer_load_balancer.fx_cmp_03_n_lb1.id
  name                       = "ru1"
  condition_language_version = "V1"
  rules {
    name      = "any"
    condition = "any(http.request.url.path sw '/')"
    actions {
      name             = "FORWARD_TO_BACKENDSET"
      backend_set_name = oci_load_balancer_backend_set.fx_cmp_03_n_pool1.name
    }
  }
}

resource "oci_load_balancer_listener" "fx_cmp_03_n_li1" {
  load_balancer_id         = oci_load_balancer_load_balancer.fx_cmp_03_n_lb1.id
  name                     = "li1"
  port                     = 443
  protocol                 = "HTTP"
  default_backend_set_name = oci_load_balancer_backend_set.fx_cmp_03_n_pool1.name
  routing_policy_name      = oci_load_balancer_load_balancer_routing_policy.fx_cmp_03_n_ru1.name
}

# ==== FX-CMP-03-I (CQ-CMP-03, incomplete)

resource "oci_core_vcn" "fx_cmp_03_i_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-cmp-03-i-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_subnet" "fx_cmp_03_i_x_subnet" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_cmp_03_i_x_vcn.id
  cidr_block     = "10.30.1.0/24"
  display_name   = "${var.run_id}-fx-cmp-03-i-x-subnet"
}

resource "oci_load_balancer_load_balancer" "fx_cmp_03_i_lb1" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.run_id}-fx-cmp-03-i-lb1"
  shape          = "flexible"
  subnet_ids     = [oci_core_subnet.fx_cmp_03_i_x_subnet.id]
  is_private     = true
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  shape_details {
    minimum_bandwidth_in_mbps = 10
    maximum_bandwidth_in_mbps = 10
  }
}

resource "oci_load_balancer_backend_set" "fx_cmp_03_i_pool1" {
  load_balancer_id = oci_load_balancer_load_balancer.fx_cmp_03_i_lb1.id
  name             = "pool1"
  policy           = "ROUND_ROBIN"
  health_checker {
    protocol    = "HTTP"
    port        = 80
    url_path    = "/"
    return_code = 200
  }
}

resource "oci_load_balancer_load_balancer_routing_policy" "fx_cmp_03_i_ru1" {
  load_balancer_id           = oci_load_balancer_load_balancer.fx_cmp_03_i_lb1.id
  name                       = "ru1"
  condition_language_version = "V1"
  rules {
    name      = "any"
    condition = "any(http.request.url.path sw '/')"
    actions {
      name             = "FORWARD_TO_BACKENDSET"
      backend_set_name = oci_load_balancer_backend_set.fx_cmp_03_i_pool1.name
    }
  }
}

resource "oci_load_balancer_listener" "fx_cmp_03_i_li1" {
  load_balancer_id         = oci_load_balancer_load_balancer.fx_cmp_03_i_lb1.id
  name                     = "li1"
  port                     = 443
  protocol                 = "HTTP"
  default_backend_set_name = oci_load_balancer_backend_set.fx_cmp_03_i_pool1.name
  routing_policy_name      = oci_load_balancer_load_balancer_routing_policy.fx_cmp_03_i_ru1.name
}

# ==== FX-CMP-04-C (CQ-CMP-04, conforming): NOT_APPLICABLE — a OCI não tem configuração de armazenamento (versionamento) declarada no namespace e herdada pelos buckets: o namespace só guarda compartimentos padrão de API

# ==== FX-CMP-04-N (CQ-CMP-04, nonconforming)

data "oci_objectstorage_namespace" "fx_cmp_04_n_ns1" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_cmp_04_n_c1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-cmp-04-n-c1"
  namespace      = data.oci_objectstorage_namespace.fx_cmp_04_n_ns1.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_objectstorage_bucket" "fx_cmp_04_n_c2" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-cmp-04-n-c2"
  namespace      = data.oci_objectstorage_namespace.fx_cmp_04_n_ns1.namespace
  versioning     = "Enabled"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-CMP-04-I (CQ-CMP-04, incomplete): NOT_APPLICABLE — a OCI não tem configuração de armazenamento (versionamento) declarada no namespace e herdada pelos buckets: o namespace só guarda compartimentos padrão de API

# ==== FX-CMP-05-C (CQ-CMP-05, conforming)

resource "oci_core_vcn" "fx_cmp_05_c_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-cmp-05-c-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_subnet" "fx_cmp_05_c_x_subnet" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_cmp_05_c_x_vcn.id
  cidr_block     = "10.30.1.0/24"
  display_name   = "${var.run_id}-fx-cmp-05-c-x-subnet"
}

data "oci_identity_availability_domains" "fx_cmp_05_c_x_ads" {
  compartment_id = var.compartment_ocid
}

resource "oci_database_db_system" "fx_cmp_05_c_i1" {
  availability_domain     = data.oci_identity_availability_domains.fx_cmp_05_c_x_ads.availability_domains[0].name
  compartment_id          = var.compartment_ocid
  shape                   = "VM.Standard.E4.Flex"
  cpu_core_count          = 1
  node_count              = 1
  subnet_id               = oci_core_subnet.fx_cmp_05_c_x_subnet.id
  ssh_public_keys         = [var.ssh_public_key]
  hostname                = "${var.run_id}cmp05"
  database_edition        = "STANDARD_EDITION"
  data_storage_size_in_gb = 256
  license_model           = "LICENSE_INCLUDED"
  display_name            = "${var.run_id}-fx-cmp-05-c-i1"
  db_home {
    db_version = "19.0.0.0"
    database {
      admin_password = var.db_admin_password
      db_name        = "cqfx5c"
    }
  }
}

# ==== FX-CMP-05-N (CQ-CMP-05, nonconforming)

resource "oci_database_autonomous_database" "fx_cmp_05_n_srv1" {
  compartment_id = var.compartment_ocid
  db_name        = "${substr(var.run_id, 0, 8)}c05n"
  display_name   = "${var.run_id}-fx-cmp-05-n-srv1"
  is_free_tier   = true
  db_workload    = "OLTP"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-CMP-05-I (CQ-CMP-05, incomplete)

resource "oci_database_autonomous_database" "fx_cmp_05_i_srv2" {
  compartment_id = var.compartment_ocid
  db_name        = "${substr(var.run_id, 0, 8)}c05i"
  display_name   = "${var.run_id}-fx-cmp-05-i-srv2"
  is_free_tier   = true
  db_workload    = "OLTP"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  is_local_data_guard_enabled = true
}

# ==== FX-AUT-01-C (CQ-AUT-01, conforming)

data "oci_objectstorage_namespace" "fx_aut_01_c_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_identity_group" "fx_aut_01_c_p1" {
  compartment_id = var.tenancy_ocid
  name           = "${var.run_id}-fx-aut-01-c-p1"
  description    = "${var.run_id} FX-AUT-01-C"
}

resource "oci_identity_compartment" "fx_aut_01_c_s_child" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-01-c-s-child"
  description    = "${var.run_id} FX-AUT-01-C"
  enable_delete  = true
}

resource "oci_objectstorage_bucket" "fx_aut_01_c_r1" {
  compartment_id = oci_identity_compartment.fx_aut_01_c_s_child.id
  name           = "${var.run_id}-fx-aut-01-c-r1"
  namespace      = data.oci_objectstorage_namespace.fx_aut_01_c_x_ns.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_identity_policy" "fx_aut_01_c_a1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-01-c-a1"
  description    = "${var.run_id} FX-AUT-01-C"
  statements = [
    "Allow group ${oci_identity_group.fx_aut_01_c_p1.name} to read objects in compartment id ${var.compartment_ocid}",
  ]
}

# ==== FX-AUT-01-N (CQ-AUT-01, nonconforming): NOT_APPLICABLE — a fixture exige negação explícita no escopo filho que vença a concessão herdada; a política da OCI concede com Allow e não há declaração de negação no vocabulário de política usado

# ==== FX-AUT-01-I (CQ-AUT-01, incomplete)

data "oci_objectstorage_namespace" "fx_aut_01_i_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_identity_group" "fx_aut_01_i_p1" {
  compartment_id = var.tenancy_ocid
  name           = "${var.run_id}-fx-aut-01-i-p1"
  description    = "${var.run_id} FX-AUT-01-I"
}

resource "oci_identity_compartment" "fx_aut_01_i_s_child" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-01-i-s-child"
  description    = "${var.run_id} FX-AUT-01-I"
  enable_delete  = true
}

resource "oci_objectstorage_bucket" "fx_aut_01_i_r1" {
  compartment_id = oci_identity_compartment.fx_aut_01_i_s_child.id
  name           = "${var.run_id}-fx-aut-01-i-r1"
  namespace      = data.oci_objectstorage_namespace.fx_aut_01_i_x_ns.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-AUT-02-C (CQ-AUT-02, conforming)

resource "oci_identity_group" "fx_aut_02_c_p1" {
  compartment_id = var.tenancy_ocid
  name           = "${var.run_id}-fx-aut-02-c-p1"
  description    = "${var.run_id} FX-AUT-02-C"
}

resource "oci_identity_policy" "fx_aut_02_c_a1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-02-c-a1"
  description    = "${var.run_id} FX-AUT-02-C"
  statements = [
    "Allow group ${oci_identity_group.fx_aut_02_c_p1.name} to read buckets in compartment id ${var.compartment_ocid}",
  ]
}

resource "oci_identity_policy" "fx_aut_02_c_doc1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-02-c-doc1"
  description    = "${var.run_id} FX-AUT-02-C"
  statements = [
    "Allow group ${oci_identity_group.fx_aut_02_c_p1.name} to read buckets in compartment id ${var.compartment_ocid}",
    "Allow group ${oci_identity_group.fx_aut_02_c_p1.name} to inspect compartments in compartment id ${var.compartment_ocid}",
  ]
}

# ==== FX-AUT-02-N (CQ-AUT-02, nonconforming)

resource "oci_identity_group" "fx_aut_02_n_p1" {
  compartment_id = var.tenancy_ocid
  name           = "${var.run_id}-fx-aut-02-n-p1"
  description    = "${var.run_id} FX-AUT-02-N"
}

resource "oci_identity_policy" "fx_aut_02_n_a1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-02-n-a1"
  description    = "${var.run_id} FX-AUT-02-N"
  statements = [
    "Allow group ${oci_identity_group.fx_aut_02_n_p1.name} to read buckets in compartment id ${var.compartment_ocid}",
  ]
}

resource "oci_identity_policy" "fx_aut_02_n_a2" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-02-n-a2"
  description    = "${var.run_id} FX-AUT-02-N"
  statements = [
    "Allow group ${oci_identity_group.fx_aut_02_n_p1.name} to manage objects in compartment id ${var.compartment_ocid}",
  ]
}

# ==== FX-AUT-02-I (CQ-AUT-02, incomplete)

variable "fx_aut_02_i_a2_group" {
  type        = string
  description = "grupo da declaração a2 da fixture FX-AUT-02-I; não resolvido"
}

resource "oci_identity_group" "fx_aut_02_i_p1" {
  compartment_id = var.tenancy_ocid
  name           = "${var.run_id}-fx-aut-02-i-p1"
  description    = "${var.run_id} FX-AUT-02-I"
}

resource "oci_identity_policy" "fx_aut_02_i_a1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-02-i-a1"
  description    = "${var.run_id} FX-AUT-02-I"
  statements = [
    "Allow group ${oci_identity_group.fx_aut_02_i_p1.name} to read buckets in compartment id ${var.compartment_ocid}",
  ]
}

resource "oci_identity_policy" "fx_aut_02_i_doc1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-02-i-doc1"
  description    = "${var.run_id} FX-AUT-02-I"
  statements = [
    "Allow group ${var.fx_aut_02_i_a2_group} to read buckets in compartment id ${var.compartment_ocid}",
    "Allow group ${oci_identity_group.fx_aut_02_i_p1.name} to inspect compartments in compartment id ${var.compartment_ocid}",
  ]
}

# ==== FX-AUT-03-C (CQ-AUT-03, conforming)

data "oci_objectstorage_namespace" "fx_aut_03_c_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_identity_group" "fx_aut_03_c_p1" {
  compartment_id = var.tenancy_ocid
  name           = "${var.run_id}-fx-aut-03-c-p1"
  description    = "${var.run_id} FX-AUT-03-C"
}

resource "oci_objectstorage_bucket" "fx_aut_03_c_r2" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-03-c-r2"
  namespace      = data.oci_objectstorage_namespace.fx_aut_03_c_x_ns.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_identity_compartment" "fx_aut_03_c_s_child" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-03-c-s-child"
  description    = "${var.run_id} FX-AUT-03-C"
  enable_delete  = true
}

resource "oci_identity_policy" "fx_aut_03_c_a1" {
  compartment_id = oci_identity_compartment.fx_aut_03_c_s_child.id
  name           = "${var.run_id}-fx-aut-03-c-a1"
  description    = "${var.run_id} FX-AUT-03-C"
  statements = [
    "Allow group ${oci_identity_group.fx_aut_03_c_p1.name} to read objects in compartment id ${oci_identity_compartment.fx_aut_03_c_s_child.id}",
  ]
}

# ==== FX-AUT-03-N (CQ-AUT-03, nonconforming)

data "oci_objectstorage_namespace" "fx_aut_03_n_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_identity_group" "fx_aut_03_n_p1" {
  compartment_id = var.tenancy_ocid
  name           = "${var.run_id}-fx-aut-03-n-p1"
  description    = "${var.run_id} FX-AUT-03-N"
}

resource "oci_objectstorage_bucket" "fx_aut_03_n_r2" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-03-n-r2"
  namespace      = data.oci_objectstorage_namespace.fx_aut_03_n_x_ns.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_identity_compartment" "fx_aut_03_n_s_child" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-03-n-s-child"
  description    = "${var.run_id} FX-AUT-03-N"
  enable_delete  = true
}

resource "oci_identity_policy" "fx_aut_03_n_a1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-03-n-a1"
  description    = "${var.run_id} FX-AUT-03-N"
  statements = [
    "Allow group ${oci_identity_group.fx_aut_03_n_p1.name} to read objects in compartment id ${var.compartment_ocid}",
  ]
}

# ==== FX-AUT-03-I (CQ-AUT-03, incomplete)

variable "fx_aut_03_i_s_child_id" {
  type        = string
  description = "compartimento s_child da fixture FX-AUT-03-I; hierarquia não lida"
}

data "oci_objectstorage_namespace" "fx_aut_03_i_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_identity_group" "fx_aut_03_i_p1" {
  compartment_id = var.tenancy_ocid
  name           = "${var.run_id}-fx-aut-03-i-p1"
  description    = "${var.run_id} FX-AUT-03-I"
}

resource "oci_objectstorage_bucket" "fx_aut_03_i_r2" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-03-i-r2"
  namespace      = data.oci_objectstorage_namespace.fx_aut_03_i_x_ns.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_identity_policy" "fx_aut_03_i_a1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-03-i-a1"
  description    = "${var.run_id} FX-AUT-03-I"
  statements = [
    "Allow group ${oci_identity_group.fx_aut_03_i_p1.name} to read objects in compartment id ${var.fx_aut_03_i_s_child_id}",
  ]
}

# ==== FX-AUT-04-C (CQ-AUT-04, conforming)

resource "oci_identity_group" "fx_aut_04_c_g1" {
  compartment_id = var.tenancy_ocid
  name           = "${var.run_id}-fx-aut-04-c-g1"
  description    = "${var.run_id} FX-AUT-04-C"
}

resource "oci_identity_user" "fx_aut_04_c_u1" {
  compartment_id = var.tenancy_ocid
  name           = "${var.run_id}-fx-aut-04-c-u1"
  description    = "${var.run_id} FX-AUT-04-C"
}

resource "oci_identity_user_group_membership" "fx_aut_04_c_x_member" {
  group_id = oci_identity_group.fx_aut_04_c_g1.id
  user_id  = oci_identity_user.fx_aut_04_c_u1.id
}

resource "oci_identity_policy" "fx_aut_04_c_a1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-04-c-a1"
  description    = "${var.run_id} FX-AUT-04-C"
  statements = [
    "Allow group ${oci_identity_group.fx_aut_04_c_g1.name} to read buckets in compartment id ${var.compartment_ocid}",
  ]
}

# ==== FX-AUT-04-N (CQ-AUT-04, nonconforming)

resource "oci_identity_group" "fx_aut_04_n_g1" {
  compartment_id = var.tenancy_ocid
  name           = "${var.run_id}-fx-aut-04-n-g1"
  description    = "${var.run_id} FX-AUT-04-N"
}

resource "oci_identity_user" "fx_aut_04_n_u1" {
  compartment_id = var.tenancy_ocid
  name           = "${var.run_id}-fx-aut-04-n-u1"
  description    = "${var.run_id} FX-AUT-04-N"
}

resource "oci_identity_policy" "fx_aut_04_n_a1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-04-n-a1"
  description    = "${var.run_id} FX-AUT-04-N"
  statements = [
    "Allow group ${oci_identity_group.fx_aut_04_n_g1.name} to read buckets in compartment id ${var.compartment_ocid}",
  ]
}

# ==== FX-AUT-04-I (CQ-AUT-04, incomplete)

variable "fx_aut_04_i_g1_name" {
  type        = string
  description = "grupo do IdP federado da fixture FX-AUT-04-I; fora do pin"
}

resource "oci_identity_policy" "fx_aut_04_i_a1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-04-i-a1"
  description    = "${var.run_id} FX-AUT-04-I"
  statements = [
    "Allow group ${var.fx_aut_04_i_g1_name} to read buckets in compartment id ${var.compartment_ocid}",
  ]
}

# ==== FX-AUT-05-C (CQ-AUT-05, conforming)

data "oci_objectstorage_namespace" "fx_aut_05_c_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_identity_group" "fx_aut_05_c_p1" {
  compartment_id = var.tenancy_ocid
  name           = "${var.run_id}-fx-aut-05-c-p1"
  description    = "${var.run_id} FX-AUT-05-C"
}

resource "oci_objectstorage_bucket" "fx_aut_05_c_r1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-05-c-r1"
  namespace      = data.oci_objectstorage_namespace.fx_aut_05_c_x_ns.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_identity_network_source" "fx_aut_05_c_c1" {
  compartment_id     = var.tenancy_ocid
  name               = "${var.run_id}-fx-aut-05-c-c1"
  description        = "${var.run_id} FX-AUT-05-C"
  public_source_list = ["198.51.100.0/24"]
}

resource "oci_identity_policy" "fx_aut_05_c_a1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-05-c-a1"
  description    = "${var.run_id} FX-AUT-05-C"
  statements = [
    "Allow group ${oci_identity_group.fx_aut_05_c_p1.name} to read objects in compartment id ${var.compartment_ocid} where request.networkSource.name = '${oci_identity_network_source.fx_aut_05_c_c1.name}'",
  ]
}

# ==== FX-AUT-05-N (CQ-AUT-05, nonconforming)

data "oci_objectstorage_namespace" "fx_aut_05_n_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_identity_group" "fx_aut_05_n_p1" {
  compartment_id = var.tenancy_ocid
  name           = "${var.run_id}-fx-aut-05-n-p1"
  description    = "${var.run_id} FX-AUT-05-N"
}

resource "oci_objectstorage_bucket" "fx_aut_05_n_r1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-05-n-r1"
  namespace      = data.oci_objectstorage_namespace.fx_aut_05_n_x_ns.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_identity_network_source" "fx_aut_05_n_c1" {
  compartment_id     = var.tenancy_ocid
  name               = "${var.run_id}-fx-aut-05-n-c1"
  description        = "${var.run_id} FX-AUT-05-N"
  public_source_list = ["198.51.100.0/24"]
}

resource "oci_identity_policy" "fx_aut_05_n_a1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-05-n-a1"
  description    = "${var.run_id} FX-AUT-05-N"
  statements = [
    "Allow group ${oci_identity_group.fx_aut_05_n_p1.name} to read objects in compartment id ${var.compartment_ocid} where request.networkSource.name = '${oci_identity_network_source.fx_aut_05_n_c1.name}'",
  ]
}

# ==== FX-AUT-05-I (CQ-AUT-05, incomplete)

data "oci_objectstorage_namespace" "fx_aut_05_i_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_identity_group" "fx_aut_05_i_p1" {
  compartment_id = var.tenancy_ocid
  name           = "${var.run_id}-fx-aut-05-i-p1"
  description    = "${var.run_id} FX-AUT-05-I"
}

resource "oci_objectstorage_bucket" "fx_aut_05_i_r1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-05-i-r1"
  namespace      = data.oci_objectstorage_namespace.fx_aut_05_i_x_ns.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_identity_policy" "fx_aut_05_i_a1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-aut-05-i-a1"
  description    = "${var.run_id} FX-AUT-05-I"
  statements = [
    "Allow group ${oci_identity_group.fx_aut_05_i_p1.name} to read objects in compartment id ${var.compartment_ocid} where request.principal.group.tag.posture.state = 'compliant'",
  ]
}

# ==== FX-NET-01-C (CQ-NET-01, conforming)

resource "oci_core_vcn" "fx_net_01_c_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-net-01-c-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_internet_gateway" "fx_net_01_c_igw" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_net_01_c_x_vcn.id
  display_name   = "${var.run_id}-fx-net-01-c-igw"
  enabled        = true
}

resource "oci_core_route_table" "fx_net_01_c_rt1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_net_01_c_x_vcn.id
  display_name   = "${var.run_id}-fx-net-01-c-rt1"
  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.fx_net_01_c_igw.id
  }
}

resource "oci_core_subnet" "fx_net_01_c_sa" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.fx_net_01_c_x_vcn.id
  cidr_block                 = "10.30.1.0/24"
  display_name               = "${var.run_id}-fx-net-01-c-sa"
  route_table_id             = oci_core_route_table.fx_net_01_c_rt1.id
  prohibit_public_ip_on_vnic = false
}

resource "oci_core_network_security_group" "fx_net_01_c_rs1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_net_01_c_x_vcn.id
  display_name   = "${var.run_id}-fx-net-01-c-rs1"
}

data "oci_core_images" "fx_net_01_c_x_img" {
  compartment_id   = var.compartment_ocid
  operating_system = "Oracle Linux"
  shape            = "VM.Standard.E2.1.Micro"
  sort_by          = "TIMECREATED"
  sort_order       = "DESC"
}

data "oci_identity_availability_domains" "fx_net_01_c_x_ads" {
  compartment_id = var.compartment_ocid
}

resource "oci_core_instance" "fx_net_01_c_vm1" {
  availability_domain = data.oci_identity_availability_domains.fx_net_01_c_x_ads.availability_domains[0].name
  compartment_id      = var.compartment_ocid
  shape               = "VM.Standard.E2.1.Micro"
  display_name        = "${var.run_id}-fx-net-01-c-vm1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_net_01_c_sa.id
    assign_public_ip = "true"
    display_name     = "${var.run_id}-fx-net-01-c-vm1-vnic0"
    nsg_ids          = [oci_core_network_security_group.fx_net_01_c_rs1.id]
  }
  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.fx_net_01_c_x_img.images[0].id
  }
}

resource "oci_core_network_security_group_security_rule" "fx_net_01_c_r1" {
  network_security_group_id = oci_core_network_security_group.fx_net_01_c_rs1.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = "203.0.113.0/24"
  source_type               = "CIDR_BLOCK"
  stateless                 = false
  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

# ==== FX-NET-01-N (CQ-NET-01, nonconforming): NOT_APPLICABLE — a fixture exige regra de negação de maior precedência no conjunto anexado à interface; NSG e security list da OCI só permitem, sem efeito nem precedência

# ==== FX-NET-01-I (CQ-NET-01, incomplete)

resource "oci_core_vcn" "fx_net_01_i_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-net-01-i-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_internet_gateway" "fx_net_01_i_igw" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_net_01_i_x_vcn.id
  display_name   = "${var.run_id}-fx-net-01-i-igw"
  enabled        = true
}

resource "oci_core_route_table" "fx_net_01_i_rt1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_net_01_i_x_vcn.id
  display_name   = "${var.run_id}-fx-net-01-i-rt1"
  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.fx_net_01_i_igw.id
  }
}

resource "oci_core_subnet" "fx_net_01_i_sa" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.fx_net_01_i_x_vcn.id
  cidr_block                 = "10.30.1.0/24"
  display_name               = "${var.run_id}-fx-net-01-i-sa"
  route_table_id             = oci_core_route_table.fx_net_01_i_rt1.id
  prohibit_public_ip_on_vnic = false
}

resource "oci_core_network_security_group" "fx_net_01_i_rs1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_net_01_i_x_vcn.id
  display_name   = "${var.run_id}-fx-net-01-i-rs1"
}

data "oci_core_images" "fx_net_01_i_x_img" {
  compartment_id   = var.compartment_ocid
  operating_system = "Oracle Linux"
  shape            = "VM.Standard.E2.1.Micro"
  sort_by          = "TIMECREATED"
  sort_order       = "DESC"
}

data "oci_identity_availability_domains" "fx_net_01_i_x_ads" {
  compartment_id = var.compartment_ocid
}

resource "oci_core_instance" "fx_net_01_i_vm1" {
  availability_domain = data.oci_identity_availability_domains.fx_net_01_i_x_ads.availability_domains[0].name
  compartment_id      = var.compartment_ocid
  shape               = "VM.Standard.E2.1.Micro"
  display_name        = "${var.run_id}-fx-net-01-i-vm1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_net_01_i_sa.id
    assign_public_ip = "true"
    display_name     = "${var.run_id}-fx-net-01-i-vm1-vnic0"
    nsg_ids          = [oci_core_network_security_group.fx_net_01_i_rs1.id]
  }
  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.fx_net_01_i_x_img.images[0].id
  }
}

resource "oci_core_network_security_group_security_rule" "fx_net_01_i_r1" {
  network_security_group_id = oci_core_network_security_group.fx_net_01_i_rs1.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = "203.0.113.0/24"
  source_type               = "CIDR_BLOCK"
  stateless                 = false
  tcp_options {
    destination_port_range {
      min = 22
      max = 22
    }
  }
}

# ==== FX-NET-02-C (CQ-NET-02, conforming)

resource "oci_core_vcn" "fx_net_02_c_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-net-02-c-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_security_list" "fx_net_02_c_rs1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_net_02_c_x_vcn.id
  display_name   = "${var.run_id}-fx-net-02-c-rs1"
  ingress_security_rules {
    protocol    = "6"
    source      = "203.0.113.0/24"
    source_type = "CIDR_BLOCK"
    stateless   = false
    tcp_options {
      min = 443
      max = 443
    }
  }
}

# ==== FX-NET-02-N (CQ-NET-02, nonconforming)

resource "oci_core_vcn" "fx_net_02_n_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-net-02-n-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_security_list" "fx_net_02_n_rs1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_net_02_n_x_vcn.id
  display_name   = "${var.run_id}-fx-net-02-n-rs1"
  ingress_security_rules {
    protocol    = "6"
    source      = "203.0.113.0/24"
    source_type = "CIDR_BLOCK"
    stateless   = true
    tcp_options {
      min = 443
      max = 443
    }
  }
}

# ==== FX-NET-02-I (CQ-NET-02, incomplete)

resource "oci_core_vcn" "fx_net_02_i_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-net-02-i-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_security_list" "fx_net_02_i_rs1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_net_02_i_x_vcn.id
  display_name   = "${var.run_id}-fx-net-02-i-rs1"
  ingress_security_rules {
    protocol    = "6"
    source      = "203.0.113.0/24"
    source_type = "CIDR_BLOCK"
    tcp_options {
      min = 443
      max = 443
    }
  }
}

# ==== FX-NET-03-C (CQ-NET-03, conforming)

resource "oci_core_vcn" "fx_net_03_c_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-net-03-c-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_internet_gateway" "fx_net_03_c_igw" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_net_03_c_x_vcn.id
  display_name   = "${var.run_id}-fx-net-03-c-igw"
  enabled        = true
}

resource "oci_core_route_table" "fx_net_03_c_rt1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_net_03_c_x_vcn.id
  display_name   = "${var.run_id}-fx-net-03-c-rt1"
  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.fx_net_03_c_igw.id
  }
}

resource "oci_core_subnet" "fx_net_03_c_sa" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.fx_net_03_c_x_vcn.id
  cidr_block                 = "10.30.1.0/24"
  display_name               = "${var.run_id}-fx-net-03-c-sa"
  route_table_id             = oci_core_route_table.fx_net_03_c_rt1.id
  prohibit_public_ip_on_vnic = false
}

resource "oci_core_network_security_group" "fx_net_03_c_rs1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_net_03_c_x_vcn.id
  display_name   = "${var.run_id}-fx-net-03-c-rs1"
}

data "oci_core_images" "fx_net_03_c_x_img" {
  compartment_id   = var.compartment_ocid
  operating_system = "Oracle Linux"
  shape            = "VM.Standard.E2.1.Micro"
  sort_by          = "TIMECREATED"
  sort_order       = "DESC"
}

data "oci_identity_availability_domains" "fx_net_03_c_x_ads" {
  compartment_id = var.compartment_ocid
}

resource "oci_core_instance" "fx_net_03_c_vm1" {
  availability_domain = data.oci_identity_availability_domains.fx_net_03_c_x_ads.availability_domains[0].name
  compartment_id      = var.compartment_ocid
  shape               = "VM.Standard.E2.1.Micro"
  display_name        = "${var.run_id}-fx-net-03-c-vm1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_net_03_c_sa.id
    assign_public_ip = "true"
    display_name     = "${var.run_id}-fx-net-03-c-vm1-vnic0"
    nsg_ids          = [oci_core_network_security_group.fx_net_03_c_rs1.id]
  }
  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.fx_net_03_c_x_img.images[0].id
  }
}

resource "oci_core_network_security_group_security_rule" "fx_net_03_c_r1" {
  network_security_group_id = oci_core_network_security_group.fx_net_03_c_rs1.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = "0.0.0.0/0"
  source_type               = "CIDR_BLOCK"
  stateless                 = false
  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

# ==== FX-NET-03-N (CQ-NET-03, nonconforming)

resource "oci_core_vcn" "fx_net_03_n_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-net-03-n-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_route_table" "fx_net_03_n_rt1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_net_03_n_x_vcn.id
  display_name   = "${var.run_id}-fx-net-03-n-rt1"
}

resource "oci_core_subnet" "fx_net_03_n_sa" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.fx_net_03_n_x_vcn.id
  cidr_block                 = "10.30.1.0/24"
  display_name               = "${var.run_id}-fx-net-03-n-sa"
  route_table_id             = oci_core_route_table.fx_net_03_n_rt1.id
  prohibit_public_ip_on_vnic = true
}

resource "oci_core_network_security_group" "fx_net_03_n_rs1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_net_03_n_x_vcn.id
  display_name   = "${var.run_id}-fx-net-03-n-rs1"
}

data "oci_core_images" "fx_net_03_n_x_img" {
  compartment_id   = var.compartment_ocid
  operating_system = "Oracle Linux"
  shape            = "VM.Standard.E2.1.Micro"
  sort_by          = "TIMECREATED"
  sort_order       = "DESC"
}

data "oci_identity_availability_domains" "fx_net_03_n_x_ads" {
  compartment_id = var.compartment_ocid
}

resource "oci_core_instance" "fx_net_03_n_vm1" {
  availability_domain = data.oci_identity_availability_domains.fx_net_03_n_x_ads.availability_domains[0].name
  compartment_id      = var.compartment_ocid
  shape               = "VM.Standard.E2.1.Micro"
  display_name        = "${var.run_id}-fx-net-03-n-vm1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_net_03_n_sa.id
    assign_public_ip = "false"
    display_name     = "${var.run_id}-fx-net-03-n-vm1-vnic0"
    nsg_ids          = [oci_core_network_security_group.fx_net_03_n_rs1.id]
  }
  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.fx_net_03_n_x_img.images[0].id
  }
}

resource "oci_core_network_security_group_security_rule" "fx_net_03_n_r1" {
  network_security_group_id = oci_core_network_security_group.fx_net_03_n_rs1.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = "0.0.0.0/0"
  source_type               = "CIDR_BLOCK"
  stateless                 = false
  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

# ==== FX-NET-03-I (CQ-NET-03, incomplete)

variable "fx_net_03_i_rt1_id" {
  type        = string
  description = "tabela de rotas da fixture FX-NET-03-I; não lida"
}

resource "oci_core_vcn" "fx_net_03_i_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-net-03-i-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_subnet" "fx_net_03_i_sa" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.fx_net_03_i_x_vcn.id
  cidr_block                 = "10.30.1.0/24"
  display_name               = "${var.run_id}-fx-net-03-i-sa"
  route_table_id             = var.fx_net_03_i_rt1_id
  prohibit_public_ip_on_vnic = false
}

resource "oci_core_network_security_group" "fx_net_03_i_rs1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_net_03_i_x_vcn.id
  display_name   = "${var.run_id}-fx-net-03-i-rs1"
}

data "oci_core_images" "fx_net_03_i_x_img" {
  compartment_id   = var.compartment_ocid
  operating_system = "Oracle Linux"
  shape            = "VM.Standard.E2.1.Micro"
  sort_by          = "TIMECREATED"
  sort_order       = "DESC"
}

data "oci_identity_availability_domains" "fx_net_03_i_x_ads" {
  compartment_id = var.compartment_ocid
}

resource "oci_core_instance" "fx_net_03_i_vm1" {
  availability_domain = data.oci_identity_availability_domains.fx_net_03_i_x_ads.availability_domains[0].name
  compartment_id      = var.compartment_ocid
  shape               = "VM.Standard.E2.1.Micro"
  display_name        = "${var.run_id}-fx-net-03-i-vm1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_net_03_i_sa.id
    assign_public_ip = "true"
    display_name     = "${var.run_id}-fx-net-03-i-vm1-vnic0"
    nsg_ids          = [oci_core_network_security_group.fx_net_03_i_rs1.id]
  }
  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.fx_net_03_i_x_img.images[0].id
  }
}

resource "oci_core_network_security_group_security_rule" "fx_net_03_i_r1" {
  network_security_group_id = oci_core_network_security_group.fx_net_03_i_rs1.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = "0.0.0.0/0"
  source_type               = "CIDR_BLOCK"
  stateless                 = false
  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

# ==== FX-NET-04-C (CQ-NET-04, conforming)

resource "oci_core_vcn" "fx_net_04_c_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-net-04-c-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_subnet" "fx_net_04_c_x_subnet" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_net_04_c_x_vcn.id
  cidr_block     = "10.30.1.0/24"
  display_name   = "${var.run_id}-fx-net-04-c-x-subnet"
}

resource "oci_core_network_security_group" "fx_net_04_c_rs1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_net_04_c_x_vcn.id
  display_name   = "${var.run_id}-fx-net-04-c-rs1"
}

data "oci_core_images" "fx_net_04_c_x_img_a1" {
  compartment_id   = var.compartment_ocid
  operating_system = "Oracle Linux"
  shape            = "VM.Standard.A1.Flex"
  sort_by          = "TIMECREATED"
  sort_order       = "DESC"
}

data "oci_identity_availability_domains" "fx_net_04_c_x_ads" {
  compartment_id = var.compartment_ocid
}

resource "oci_core_instance" "fx_net_04_c_vm1" {
  availability_domain = data.oci_identity_availability_domains.fx_net_04_c_x_ads.availability_domains[0].name
  compartment_id      = var.compartment_ocid
  shape               = "VM.Standard.A1.Flex"
  display_name        = "${var.run_id}-fx-net-04-c-vm1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_net_04_c_x_subnet.id
    assign_public_ip = "false"
    display_name     = "${var.run_id}-fx-net-04-c-vm1-vnic0"
  }
  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.fx_net_04_c_x_img_a1.images[0].id
  }
  shape_config {
    ocpus         = 1
    memory_in_gbs = 6
  }
}

resource "oci_core_vnic_attachment" "fx_net_04_c_nic2" {
  instance_id  = oci_core_instance.fx_net_04_c_vm1.id
  display_name = "${var.run_id}-fx-net-04-c-nic2-att"
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_net_04_c_x_subnet.id
    assign_public_ip = "false"
    display_name     = "${var.run_id}-fx-net-04-c-nic2"
    nsg_ids          = [oci_core_network_security_group.fx_net_04_c_rs1.id]
  }
}

# ==== FX-NET-04-N (CQ-NET-04, nonconforming)

resource "oci_core_vcn" "fx_net_04_n_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-net-04-n-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_subnet" "fx_net_04_n_x_subnet" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_net_04_n_x_vcn.id
  cidr_block     = "10.30.1.0/24"
  display_name   = "${var.run_id}-fx-net-04-n-x-subnet"
}

resource "oci_core_network_security_group" "fx_net_04_n_rs1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_net_04_n_x_vcn.id
  display_name   = "${var.run_id}-fx-net-04-n-rs1"
}

data "oci_core_images" "fx_net_04_n_x_img" {
  compartment_id   = var.compartment_ocid
  operating_system = "Oracle Linux"
  shape            = "VM.Standard.E2.1.Micro"
  sort_by          = "TIMECREATED"
  sort_order       = "DESC"
}

data "oci_identity_availability_domains" "fx_net_04_n_x_ads" {
  compartment_id = var.compartment_ocid
}

resource "oci_core_instance" "fx_net_04_n_vm1" {
  availability_domain = data.oci_identity_availability_domains.fx_net_04_n_x_ads.availability_domains[0].name
  compartment_id      = var.compartment_ocid
  shape               = "VM.Standard.E2.1.Micro"
  display_name        = "${var.run_id}-fx-net-04-n-vm1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_net_04_n_x_subnet.id
    assign_public_ip = "false"
    display_name     = "${var.run_id}-fx-net-04-n-vm1-vnic0"
  }
  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.fx_net_04_n_x_img.images[0].id
  }
}

resource "oci_core_instance" "fx_net_04_n_vm2" {
  availability_domain = data.oci_identity_availability_domains.fx_net_04_n_x_ads.availability_domains[0].name
  compartment_id      = var.compartment_ocid
  shape               = "VM.Standard.E2.1.Micro"
  display_name        = "${var.run_id}-fx-net-04-n-vm2"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_net_04_n_x_subnet.id
    assign_public_ip = "false"
    display_name     = "${var.run_id}-fx-net-04-n-vm2-vnic0"
    nsg_ids          = [oci_core_network_security_group.fx_net_04_n_rs1.id]
  }
  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.fx_net_04_n_x_img.images[0].id
  }
}

# ==== FX-NET-04-I (CQ-NET-04, incomplete)

variable "fx_net_04_i_nic2_nsg_ids" {
  type        = list(string)
  description = "NSGs da VNIC nic2 da fixture FX-NET-04-I; não lidos"
}

resource "oci_core_vcn" "fx_net_04_i_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-net-04-i-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_subnet" "fx_net_04_i_x_subnet" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_net_04_i_x_vcn.id
  cidr_block     = "10.30.1.0/24"
  display_name   = "${var.run_id}-fx-net-04-i-x-subnet"
}

resource "oci_core_network_security_group" "fx_net_04_i_rs1" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_net_04_i_x_vcn.id
  display_name   = "${var.run_id}-fx-net-04-i-rs1"
}

data "oci_core_images" "fx_net_04_i_x_img_a1" {
  compartment_id   = var.compartment_ocid
  operating_system = "Oracle Linux"
  shape            = "VM.Standard.A1.Flex"
  sort_by          = "TIMECREATED"
  sort_order       = "DESC"
}

data "oci_identity_availability_domains" "fx_net_04_i_x_ads" {
  compartment_id = var.compartment_ocid
}

resource "oci_core_instance" "fx_net_04_i_vm1" {
  availability_domain = data.oci_identity_availability_domains.fx_net_04_i_x_ads.availability_domains[0].name
  compartment_id      = var.compartment_ocid
  shape               = "VM.Standard.A1.Flex"
  display_name        = "${var.run_id}-fx-net-04-i-vm1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_net_04_i_x_subnet.id
    assign_public_ip = "false"
    display_name     = "${var.run_id}-fx-net-04-i-vm1-vnic0"
  }
  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.fx_net_04_i_x_img_a1.images[0].id
  }
  shape_config {
    ocpus         = 1
    memory_in_gbs = 6
  }
}

resource "oci_core_vnic_attachment" "fx_net_04_i_nic2" {
  instance_id  = oci_core_instance.fx_net_04_i_vm1.id
  display_name = "${var.run_id}-fx-net-04-i-nic2-att"
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_net_04_i_x_subnet.id
    assign_public_ip = "false"
    display_name     = "${var.run_id}-fx-net-04-i-nic2"
    nsg_ids          = var.fx_net_04_i_nic2_nsg_ids
  }
}

# ==== FX-CVO-01-C (CQ-CVO-01, conforming)

data "oci_objectstorage_namespace" "fx_cvo_01_c_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_cvo_01_c_c1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-cvo-01-c-c1"
  namespace      = data.oci_objectstorage_namespace.fx_cvo_01_c_x_ns.namespace
  versioning     = "Enabled"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-CVO-01-N (CQ-CVO-01, nonconforming)

data "oci_objectstorage_namespace" "fx_cvo_01_n_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_cvo_01_n_c1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-cvo-01-n-c1"
  namespace      = data.oci_objectstorage_namespace.fx_cvo_01_n_x_ns.namespace
  versioning     = "Enabled"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-CVO-01-I (CQ-CVO-01, incomplete)

data "oci_objectstorage_namespace" "fx_cvo_01_i_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_cvo_01_i_c1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-cvo-01-i-c1"
  namespace      = data.oci_objectstorage_namespace.fx_cvo_01_i_x_ns.namespace
  versioning     = "Enabled"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-CVO-02-C (CQ-CVO-02, conforming)

data "oci_objectstorage_namespace" "fx_cvo_02_c_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_cvo_02_c_c1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-cvo-02-c-c1"
  namespace      = data.oci_objectstorage_namespace.fx_cvo_02_c_x_ns.namespace
  versioning     = "Enabled"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-CVO-02-N (CQ-CVO-02, nonconforming)

data "oci_objectstorage_namespace" "fx_cvo_02_n_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_cvo_02_n_c1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-cvo-02-n-c1"
  namespace      = data.oci_objectstorage_namespace.fx_cvo_02_n_x_ns.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-CVO-02-I (CQ-CVO-02, incomplete)

variable "fx_cvo_02_i_versioning" {
  type        = string
  description = "entrada simbólica da fixture FX-CVO-02-I; sem valor de propósito"
}

data "oci_objectstorage_namespace" "fx_cvo_02_i_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_cvo_02_i_c1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-cvo-02-i-c1"
  namespace      = data.oci_objectstorage_namespace.fx_cvo_02_i_x_ns.namespace
  versioning     = var.fx_cvo_02_i_versioning
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-CVO-03-C (CQ-CVO-03, conforming)

resource "oci_database_autonomous_database" "fx_cvo_03_c_i1" {
  compartment_id = var.compartment_ocid
  db_name        = "${substr(var.run_id, 0, 8)}cvo3c"
  display_name   = "${var.run_id}-fx-cvo-03-c-i1"
  is_free_tier   = true
  db_workload    = "OLTP"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_ons_notification_topic" "fx_cvo_03_c_t1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-cvo-03-c-t1"
}

resource "oci_monitoring_alarm" "fx_cvo_03_c_al1" {
  compartment_id        = var.compartment_ocid
  destinations          = [oci_ons_notification_topic.fx_cvo_03_c_t1.id]
  display_name          = "${var.run_id}-fx-cvo-03-c-al1"
  is_enabled            = true
  metric_compartment_id = var.compartment_ocid
  namespace             = "oci_autonomous_database"
  query                 = "CpuUtilization[1m]{resourceId = \"${oci_database_autonomous_database.fx_cvo_03_c_i1.id}\"}.mean() > 80"
  severity              = "CRITICAL"
}

# ==== FX-CVO-03-N (CQ-CVO-03, nonconforming)

resource "oci_database_autonomous_database" "fx_cvo_03_n_i1" {
  compartment_id = var.compartment_ocid
  db_name        = "${substr(var.run_id, 0, 8)}cvo3n"
  display_name   = "${var.run_id}-fx-cvo-03-n-i1"
  is_free_tier   = true
  db_workload    = "OLTP"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-CVO-03-I (CQ-CVO-03, incomplete)

resource "oci_database_autonomous_database" "fx_cvo_03_i_i1" {
  compartment_id = var.compartment_ocid
  db_name        = "${substr(var.run_id, 0, 8)}cvo3i"
  display_name   = "${var.run_id}-fx-cvo-03-i-i1"
  is_free_tier   = true
  db_workload    = "OLTP"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-CVO-04-C (CQ-CVO-04, conforming)

resource "oci_database_autonomous_database" "fx_cvo_04_c_i1" {
  compartment_id = var.compartment_ocid
  db_name        = "${substr(var.run_id, 0, 8)}cvo4c"
  display_name   = "${var.run_id}-fx-cvo-04-c-i1"
  is_free_tier   = true
  db_workload    = "OLTP"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  admin_password = var.db_admin_password
}

# ==== FX-CVO-04-N (CQ-CVO-04, nonconforming)

resource "oci_database_autonomous_database" "fx_cvo_04_n_i1" {
  compartment_id = var.compartment_ocid
  db_name        = "${substr(var.run_id, 0, 8)}cvo4n"
  display_name   = "${var.run_id}-fx-cvo-04-n-i1"
  is_free_tier   = true
  db_workload    = "OLTP"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-CVO-04-I (CQ-CVO-04, incomplete)

variable "fx_cvo_04_i_admin_password" {
  type        = string
  description = "senha da fixture FX-CVO-04-I; não lida"
  sensitive   = true
}

resource "oci_database_autonomous_database" "fx_cvo_04_i_i1" {
  compartment_id = var.compartment_ocid
  db_name        = "${substr(var.run_id, 0, 8)}cvo4i"
  display_name   = "${var.run_id}-fx-cvo-04-i-i1"
  is_free_tier   = true
  db_workload    = "OLTP"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  admin_password = var.fx_cvo_04_i_admin_password
}

# ==== FX-LOSS-01-C (CQ-LOSS-01, conforming)

data "oci_objectstorage_namespace" "fx_loss_01_c_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_loss_01_c_s1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-loss-01-c-s1"
  namespace      = data.oci_objectstorage_namespace.fx_loss_01_c_x_ns.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  retention_rules {
    display_name = "retention"
    duration {
      time_amount = "30"
      time_unit   = "DAYS"
    }
  }
}

# ==== FX-LOSS-01-N (CQ-LOSS-01, nonconforming)

data "oci_objectstorage_namespace" "fx_loss_01_n_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_loss_01_n_s1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-loss-01-n-s1"
  namespace      = data.oci_objectstorage_namespace.fx_loss_01_n_x_ns.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  retention_rules {
    display_name = "retention"
    duration {
      time_amount = "400"
      time_unit   = "DAYS"
    }
  }
}

# ==== FX-LOSS-01-I (CQ-LOSS-01, incomplete)

data "oci_objectstorage_namespace" "fx_loss_01_i_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_loss_01_i_s1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-loss-01-i-s1"
  namespace      = data.oci_objectstorage_namespace.fx_loss_01_i_x_ns.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  retention_rules {
    display_name = "retention"
    duration {
      time_amount = "30"
      time_unit   = "DAYS"
    }
  }
}

# ==== FX-LOSS-02-C (CQ-LOSS-02, conforming)

resource "oci_network_firewall_network_firewall_policy" "fx_loss_02_c_rs1" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.run_id}-fx-loss-02-c-rs1"
}

resource "oci_network_firewall_network_firewall_policy_service" "fx_loss_02_c_x_svc22" {
  network_firewall_policy_id = oci_network_firewall_network_firewall_policy.fx_loss_02_c_rs1.id
  name                       = "tcp22"
  type                       = "TCP_SERVICE"
  port_ranges {
    minimum_port = 22
    maximum_port = 22
  }
}

resource "oci_network_firewall_network_firewall_policy_service_list" "fx_loss_02_c_x_svcl22" {
  network_firewall_policy_id = oci_network_firewall_network_firewall_policy.fx_loss_02_c_rs1.id
  name                       = "list22"
  services                   = [oci_network_firewall_network_firewall_policy_service.fx_loss_02_c_x_svc22.name]
}

resource "oci_network_firewall_network_firewall_policy_security_rule" "fx_loss_02_c_r1" {
  network_firewall_policy_id = oci_network_firewall_network_firewall_policy.fx_loss_02_c_rs1.id
  name                       = "r1"
  action                     = "DROP"
  condition {
    service = [
      oci_network_firewall_network_firewall_policy_service_list.fx_loss_02_c_x_svcl22.name,
    ]
  }
}

# ==== FX-LOSS-02-N (CQ-LOSS-02, nonconforming)

resource "oci_network_firewall_network_firewall_policy" "fx_loss_02_n_rs1" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.run_id}-fx-loss-02-n-rs1"
}

resource "oci_network_firewall_network_firewall_policy_service" "fx_loss_02_n_x_svc22" {
  network_firewall_policy_id = oci_network_firewall_network_firewall_policy.fx_loss_02_n_rs1.id
  name                       = "tcp22"
  type                       = "TCP_SERVICE"
  port_ranges {
    minimum_port = 22
    maximum_port = 22
  }
}

resource "oci_network_firewall_network_firewall_policy_service_list" "fx_loss_02_n_x_svcl22" {
  network_firewall_policy_id = oci_network_firewall_network_firewall_policy.fx_loss_02_n_rs1.id
  name                       = "list22"
  services                   = [oci_network_firewall_network_firewall_policy_service.fx_loss_02_n_x_svc22.name]
}

resource "oci_network_firewall_network_firewall_policy_security_rule" "fx_loss_02_n_r1" {
  network_firewall_policy_id = oci_network_firewall_network_firewall_policy.fx_loss_02_n_rs1.id
  name                       = "r1"
  action                     = "DROP"
  condition {
    service = [
      oci_network_firewall_network_firewall_policy_service_list.fx_loss_02_n_x_svcl22.name,
    ]
  }
}

# ==== FX-LOSS-02-I (CQ-LOSS-02, incomplete)

resource "oci_network_firewall_network_firewall_policy" "fx_loss_02_i_rs1" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.run_id}-fx-loss-02-i-rs1"
}

resource "oci_network_firewall_network_firewall_policy_service" "fx_loss_02_i_x_svc22" {
  network_firewall_policy_id = oci_network_firewall_network_firewall_policy.fx_loss_02_i_rs1.id
  name                       = "tcp22"
  type                       = "TCP_SERVICE"
  port_ranges {
    minimum_port = 22
    maximum_port = 22
  }
}

resource "oci_network_firewall_network_firewall_policy_service_list" "fx_loss_02_i_x_svcl22" {
  network_firewall_policy_id = oci_network_firewall_network_firewall_policy.fx_loss_02_i_rs1.id
  name                       = "list22"
  services                   = [oci_network_firewall_network_firewall_policy_service.fx_loss_02_i_x_svc22.name]
}

resource "oci_network_firewall_network_firewall_policy_security_rule" "fx_loss_02_i_r1" {
  network_firewall_policy_id = oci_network_firewall_network_firewall_policy.fx_loss_02_i_rs1.id
  name                       = "r1"
  action                     = "DROP"
  condition {
    service = [
      oci_network_firewall_network_firewall_policy_service_list.fx_loss_02_i_x_svcl22.name,
    ]
  }
}

# ==== FX-LOSS-03-C (CQ-LOSS-03, conforming)

data "oci_objectstorage_namespace" "fx_loss_03_c_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_loss_03_c_s1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-loss-03-c-s1"
  namespace      = data.oci_objectstorage_namespace.fx_loss_03_c_x_ns.namespace
  versioning     = "Enabled"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-LOSS-03-N (CQ-LOSS-03, nonconforming)

data "oci_objectstorage_namespace" "fx_loss_03_n_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_loss_03_n_s1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-loss-03-n-s1"
  namespace      = data.oci_objectstorage_namespace.fx_loss_03_n_x_ns.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-LOSS-03-I (CQ-LOSS-03, incomplete)

variable "fx_loss_03_i_versioning" {
  type        = string
  description = "entrada simbólica da fixture FX-LOSS-03-I; sem valor de propósito"
}

data "oci_objectstorage_namespace" "fx_loss_03_i_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_loss_03_i_s1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-loss-03-i-s1"
  namespace      = data.oci_objectstorage_namespace.fx_loss_03_i_x_ns.namespace
  versioning     = var.fx_loss_03_i_versioning
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-LOSS-04-C (CQ-LOSS-04, conforming)

data "oci_objectstorage_namespace" "fx_loss_04_c_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_loss_04_c_s1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-loss-04-c-s1"
  namespace      = data.oci_objectstorage_namespace.fx_loss_04_c_x_ns.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  retention_rules {
    display_name = "retention"
    duration {
      time_amount = "7"
      time_unit   = "DAYS"
    }
  }
}

# ==== FX-LOSS-04-N (CQ-LOSS-04, nonconforming)

data "oci_objectstorage_namespace" "fx_loss_04_n_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_loss_04_n_s1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-loss-04-n-s1"
  namespace      = data.oci_objectstorage_namespace.fx_loss_04_n_x_ns.namespace
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  retention_rules {
    display_name = "retention"
    duration {
      time_amount = "1"
      time_unit   = "YEARS"
    }
  }
}

# ==== FX-LOSS-04-I (CQ-LOSS-04, incomplete)

resource "oci_logging_log_group" "fx_loss_04_i_x_lg" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.run_id}-fx-loss-04-i-lg"
}

resource "oci_logging_log" "fx_loss_04_i_s1" {
  display_name       = "${var.run_id}-fx-loss-04-i-s1"
  log_group_id       = oci_logging_log_group.fx_loss_04_i_x_lg.id
  log_type           = "CUSTOM"
  retention_duration = 30
}

# ==== FX-NEW-01-C (CQ-NEW-01, conforming)

data "oci_objectstorage_namespace" "fx_new_01_c_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_new_01_c_s1" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-new-01-c-s1"
  namespace      = data.oci_objectstorage_namespace.fx_new_01_c_x_ns.namespace
  versioning     = "Enabled"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-NEW-01-N (CQ-NEW-01, nonconforming)

resource "oci_core_vcn" "fx_new_01_n_s2" {
  compartment_id                   = var.compartment_ocid
  cidr_blocks                      = ["10.30.0.0/16"]
  display_name                     = "${var.run_id}-fx-new-01-n-s2"
  is_ipv6enabled                   = true
  is_oracle_gua_allocation_enabled = true
}

# ==== FX-NEW-01-I (CQ-NEW-01, incomplete)

data "oci_objectstorage_namespace" "fx_new_01_i_x_ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "fx_new_01_i_src3" {
  compartment_id = var.compartment_ocid
  name           = "${var.run_id}-fx-new-01-i-src3"
  namespace      = data.oci_objectstorage_namespace.fx_new_01_i_x_ns.namespace
  auto_tiering   = "InfrequentAccess"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

# ==== FX-NEW-02-C (CQ-NEW-02, conforming)

resource "oci_core_vcn" "fx_new_02_c_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-new-02-c-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_subnet" "fx_new_02_c_x_subnet" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_new_02_c_x_vcn.id
  cidr_block     = "10.30.1.0/24"
  display_name   = "${var.run_id}-fx-new-02-c-x-subnet"
}

data "oci_core_images" "fx_new_02_c_x_img_a1" {
  compartment_id   = var.compartment_ocid
  operating_system = "Oracle Linux"
  shape            = "VM.Standard.A1.Flex"
  sort_by          = "TIMECREATED"
  sort_order       = "DESC"
}

data "oci_identity_availability_domains" "fx_new_02_c_x_ads" {
  compartment_id = var.compartment_ocid
}

resource "oci_core_instance" "fx_new_02_c_vm1" {
  availability_domain = data.oci_identity_availability_domains.fx_new_02_c_x_ads.availability_domains[0].name
  compartment_id      = var.compartment_ocid
  shape               = "VM.Standard.A1.Flex"
  display_name        = "${var.run_id}-fx-new-02-c-vm1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_new_02_c_x_subnet.id
    assign_public_ip = "false"
    display_name     = "${var.run_id}-fx-new-02-c-vm1-vnic0"
  }
  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.fx_new_02_c_x_img_a1.images[0].id
  }
  shape_config {
    ocpus         = 1
    memory_in_gbs = 6
  }
}

resource "oci_core_vnic_attachment" "fx_new_02_c_nic2" {
  instance_id  = oci_core_instance.fx_new_02_c_vm1.id
  display_name = "${var.run_id}-fx-new-02-c-nic2-att"
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_new_02_c_x_subnet.id
    assign_public_ip = "false"
    display_name     = "${var.run_id}-fx-new-02-c-nic2"
  }
}

# ==== FX-NEW-02-N (CQ-NEW-02, nonconforming)

resource "oci_core_vcn" "fx_new_02_n_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-new-02-n-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_subnet" "fx_new_02_n_x_subnet" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_new_02_n_x_vcn.id
  cidr_block     = "10.30.1.0/24"
  display_name   = "${var.run_id}-fx-new-02-n-x-subnet"
}

data "oci_core_images" "fx_new_02_n_x_img" {
  compartment_id   = var.compartment_ocid
  operating_system = "Oracle Linux"
  shape            = "VM.Standard.E2.1.Micro"
  sort_by          = "TIMECREATED"
  sort_order       = "DESC"
}

data "oci_identity_availability_domains" "fx_new_02_n_x_ads" {
  compartment_id = var.compartment_ocid
}

resource "oci_core_instance" "fx_new_02_n_vm1" {
  availability_domain = data.oci_identity_availability_domains.fx_new_02_n_x_ads.availability_domains[0].name
  compartment_id      = var.compartment_ocid
  shape               = "VM.Standard.E2.1.Micro"
  display_name        = "${var.run_id}-fx-new-02-n-vm1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_new_02_n_x_subnet.id
    assign_public_ip = "false"
    display_name     = "${var.run_id}-fx-new-02-n-vm1-vnic0"
  }
  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.fx_new_02_n_x_img.images[0].id
  }
}

data "oci_core_vnic_attachments" "fx_new_02_n_x_vnics" {
  compartment_id = var.compartment_ocid
  instance_id    = oci_core_instance.fx_new_02_n_vm1.id
}

resource "oci_core_private_ip" "fx_new_02_n_ip2" {
  vnic_id      = data.oci_core_vnic_attachments.fx_new_02_n_x_vnics.vnic_attachments[0].vnic_id
  display_name = "${var.run_id}-fx-new-02-n-ip2"
}

# ==== FX-NEW-02-I (CQ-NEW-02, incomplete)

variable "fx_new_02_i_nic2_instance_id" {
  type        = string
  description = "instância de anexação de nic2 da fixture FX-NEW-02-I; não lida"
}

resource "oci_core_vcn" "fx_new_02_i_x_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.30.0.0/16"]
  display_name   = "${var.run_id}-fx-new-02-i-x-vcn"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
}

resource "oci_core_subnet" "fx_new_02_i_x_subnet" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fx_new_02_i_x_vcn.id
  cidr_block     = "10.30.1.0/24"
  display_name   = "${var.run_id}-fx-new-02-i-x-subnet"
}

data "oci_core_images" "fx_new_02_i_x_img_a1" {
  compartment_id   = var.compartment_ocid
  operating_system = "Oracle Linux"
  shape            = "VM.Standard.A1.Flex"
  sort_by          = "TIMECREATED"
  sort_order       = "DESC"
}

data "oci_identity_availability_domains" "fx_new_02_i_x_ads" {
  compartment_id = var.compartment_ocid
}

resource "oci_core_instance" "fx_new_02_i_vm1" {
  availability_domain = data.oci_identity_availability_domains.fx_new_02_i_x_ads.availability_domains[0].name
  compartment_id      = var.compartment_ocid
  shape               = "VM.Standard.A1.Flex"
  display_name        = "${var.run_id}-fx-new-02-i-vm1"
  freeform_tags = {
    bo_run    = var.run_id
    bo_module = "CQFIX"
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_new_02_i_x_subnet.id
    assign_public_ip = "false"
    display_name     = "${var.run_id}-fx-new-02-i-vm1-vnic0"
  }
  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.fx_new_02_i_x_img_a1.images[0].id
  }
  shape_config {
    ocpus         = 1
    memory_in_gbs = 6
  }
}

resource "oci_core_vnic_attachment" "fx_new_02_i_nic2" {
  instance_id  = var.fx_new_02_i_nic2_instance_id
  display_name = "${var.run_id}-fx-new-02-i-nic2-att"
  create_vnic_details {
    subnet_id        = oci_core_subnet.fx_new_02_i_x_subnet.id
    assign_public_ip = "false"
    display_name     = "${var.run_id}-fx-new-02-i-nic2"
  }
}

# ==== FX-NEW-03-C (CQ-NEW-03, conforming)

resource "oci_network_firewall_network_firewall_policy" "fx_new_03_c_rs1" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.run_id}-fx-new-03-c-rs1"
}

resource "oci_network_firewall_network_firewall_policy_service" "fx_new_03_c_x_svc22" {
  network_firewall_policy_id = oci_network_firewall_network_firewall_policy.fx_new_03_c_rs1.id
  name                       = "tcp22"
  type                       = "TCP_SERVICE"
  port_ranges {
    minimum_port = 22
    maximum_port = 22
  }
}

resource "oci_network_firewall_network_firewall_policy_service_list" "fx_new_03_c_x_svcl22" {
  network_firewall_policy_id = oci_network_firewall_network_firewall_policy.fx_new_03_c_rs1.id
  name                       = "list22"
  services                   = [oci_network_firewall_network_firewall_policy_service.fx_new_03_c_x_svc22.name]
}

resource "oci_network_firewall_network_firewall_policy_security_rule" "fx_new_03_c_r1" {
  network_firewall_policy_id = oci_network_firewall_network_firewall_policy.fx_new_03_c_rs1.id
  name                       = "r1"
  action                     = "DROP"
  priority_order             = 1
  condition {
    service = [
      oci_network_firewall_network_firewall_policy_service_list.fx_new_03_c_x_svcl22.name,
    ]
  }
}

# ==== FX-NEW-03-N (CQ-NEW-03, nonconforming): NOT_APPLICABLE — a fixture exige precedência por posição textual sem mecanismo de ordem; na OCI a filtragem é união de permissões (sem precedência) ou lista ordenada explícita do Network Firewall

# ==== FX-NEW-03-I (CQ-NEW-03, incomplete)

resource "oci_network_firewall_network_firewall_policy" "fx_new_03_i_rs1" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.run_id}-fx-new-03-i-rs1"
}

resource "oci_network_firewall_network_firewall_policy_service" "fx_new_03_i_x_svc22" {
  network_firewall_policy_id = oci_network_firewall_network_firewall_policy.fx_new_03_i_rs1.id
  name                       = "tcp22"
  type                       = "TCP_SERVICE"
  port_ranges {
    minimum_port = 22
    maximum_port = 22
  }
}

resource "oci_network_firewall_network_firewall_policy_service_list" "fx_new_03_i_x_svcl22" {
  network_firewall_policy_id = oci_network_firewall_network_firewall_policy.fx_new_03_i_rs1.id
  name                       = "list22"
  services                   = [oci_network_firewall_network_firewall_policy_service.fx_new_03_i_x_svc22.name]
}

resource "oci_network_firewall_network_firewall_policy_security_rule" "fx_new_03_i_r1" {
  network_firewall_policy_id = oci_network_firewall_network_firewall_policy.fx_new_03_i_rs1.id
  name                       = "r1"
  action                     = "DROP"
  condition {
    service = [
      oci_network_firewall_network_firewall_policy_service_list.fx_new_03_i_x_svcl22.name,
    ]
  }
}
