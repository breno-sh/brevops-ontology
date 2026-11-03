"""Catálogo curado de conceitos de controle, neutro de provedor, sobre a versão CIS mais nova de cada mod.

Cada conceito lista os itens CIS que o realizam em cada provedor. A pertença é CURADA a partir dos títulos
(leitura humana/agente), não provada: toda correspondência que sai daqui é UNPROVEN. Para o erro de
digitação não passar calado, cada membro traz uma guarda (regex sobre o título em minúsculas) que tem de
casar com o título extraído; se o mod mudar o título ou o número, a regeneração reprova.

Parâmetros (extraídos do TÍTULO, nunca do SQL) servem só para orientar a relação SKOS. A extensão de um
controle é o conjunto de configurações CONFORMES a ele; quanto mais exigente, mais estreito. Operadores:
  max N         conforme se valor <= N (N menor = mais estreito); ausente = sem limite
  min N         conforme se valor >= N (N maior = mais estreito); ausente = sem limite
  forbid {..}   conjunto de coisas proibidas (mais itens = mais estreito); ausente = conjunto vazio
  allow {..}    exceções permitidas (mais itens = mais largo); ausente = conjunto vazio
  require {..}  coisas exigidas (mais itens = mais estreito); ausente = conjunto vazio
  eq v          categoria; valores diferentes ou ausente de um lado = incomparável
"""

from __future__ import annotations

# provedores na ordem do index_set do catálogo (Terraform) e o nome do mod do Steampipe
PROVIDERS = ("aws", "google", "azurerm", "oci")
MOD_OF = {"aws": "aws", "google": "gcp", "azurerm": "azure", "oci": "oci"}
PAIR_CODE = {("aws", "google"): "AWSGCP", ("aws", "azurerm"): "AWSAZ", ("aws", "oci"): "AWSOCI",
             ("google", "azurerm"): "GCPAZ", ("google", "oci"): "GCPOCI", ("azurerm", "oci"): "AZOCI"}

ANY4, ANY6 = "ipv4_any", "ipv6_any"
INTERNET = (ANY4, ANY6)
CHANGES = ("create", "update", "delete")


def M(provider: str, item: str, guard: str, **params):
    return {"provider": provider, "item": item, "guard": guard, "params": params}


CONCEPTS = [
    # ---------------- identidade e acesso (SEC) ----------------
    {"id": "SEC-MFA-ALL-USERS", "domain": "SEC",
     "label": "segundo fator exigido para todas as contas humanas de console",
     "members": [
         M("aws", "2.9", r"multi-factor authentication.*all iam users", population=("eq", "console_password_users")),
         M("google", "1.2", r"multi-factor authentication.*all non-service accounts",
           population=("eq", "non_service_accounts")),
         M("azurerm", "5.1.2", r"'multifactor authentication' is 'enabled' for all users",
           population=("eq", "all_users"), form=("eq", "per_user_setting")),
         M("azurerm", "5.2.4", r"multifactor authentication policy exists for all users",
           population=("eq", "all_users"), form=("eq", "conditional_access_policy")),
         M("oci", "1.7", r"mfa is enabled for all users with a console password",
           population=("eq", "console_password_users")),
     ]},
    {"id": "SEC-MFA-PRIVILEGED", "domain": "SEC",
     "label": "segundo fator exigido para a conta de topo ou contas administrativas",
     "members": [
         M("aws", "2.4", r"mfa is enabled for the 'root' user", principal=("eq", "root")),
         M("aws", "2.5", r"hardware mfa is enabled for the 'root' user", principal=("eq", "root"),
           factor=("min", 2)),
         M("google", "1.3", r"security key enforcement is enabled for all admin accounts", principal=("eq", "admin"),
           factor=("min", 2)),
         M("azurerm", "5.2.7", r"multifactor authentication is required to access microsoft admin portals",
           principal=("eq", "admin_portal_access")),
     ]},
    {"id": "SEC-PASSWORD-MIN-LENGTH", "domain": "SEC", "label": "política de senha com tamanho mínimo",
     "members": [
         M("aws", "2.7", r"password policy requires minimum length of 14", min_length=("min", 14)),
         M("oci", "1.4", r"password policy requires minimum length of 14", min_length=("min", 14)),
     ]},
    {"id": "SEC-PASSWORD-REUSE", "domain": "SEC", "label": "política de senha impede reutilização",
     "members": [
         M("aws", "2.8", r"password policy prevents password reuse"),
         M("oci", "1.6", r"password policy prevents password reuse"),
     ]},
    {"id": "SEC-UNUSED-CREDENTIALS", "domain": "SEC", "label": "credencial sem uso por N dias é desativada",
     "members": [
         M("aws", "2.11", r"credentials unused for 45 days or more are disabled", idle_days=("max", 45)),
         M("oci", "1.16", r"credentials unused for 45 days or more are disabled", idle_days=("max", 45)),
     ]},
    {"id": "SEC-ONE-ACTIVE-USER-KEY", "domain": "SEC",
     "label": "no máximo uma chave programática ativa por usuário",
     "members": [
         M("aws", "2.12", r"only one active access key for any single iam user", kind=("eq", "user_programmatic_key")),
         M("oci", "1.17", r"only one active api key for any single oci iam user", kind=("eq", "user_programmatic_key")),
     ]},
    {"id": "SEC-CREDENTIAL-ROTATION", "domain": "SEC",
     "label": "credencial programática de longa duração rotacionada dentro de um prazo",
     "members": [
         M("aws", "2.13", r"access keys are rotated every 90 days", kind=("eq", "user_programmatic_key"),
           max_age_days=("max", 90)),
         M("google", "1.7", r"keys for service accounts are rotated every 90 days",
           kind=("eq", "service_account_key"), max_age_days=("max", 90)),
         M("google", "1.15", r"api keys are rotated every 90 days", kind=("eq", "api_key"), max_age_days=("max", 90)),
         M("azurerm", "9.3.1.2", r"storage account access keys are periodically regenerated",
           kind=("eq", "storage_account_key")),
         M("oci", "1.8", r"user api keys rotate within 90 days", kind=("eq", "user_programmatic_key"),
           max_age_days=("max", 90)),
         M("oci", "1.9", r"customer secret keys rotate every 90 days", kind=("eq", "customer_secret_key"),
           max_age_days=("max", 90)),
         M("oci", "1.10", r"auth tokens rotate within 90 days", kind=("eq", "auth_token"), max_age_days=("max", 90)),
     ]},
    {"id": "SEC-NO-TOP-PRINCIPAL-KEYS", "domain": "SEC",
     "label": "a conta de topo ou de administração não tem chave programática",
     "members": [
         M("aws", "2.3", r"no 'root' user account access key exists", principal=("eq", "root")),
         M("oci", "1.12", r"api keys are not created for tenancy administrator users", principal=("eq", "admin")),
     ]},
    {"id": "SEC-TOP-PRINCIPAL-DAILY-USE", "domain": "SEC",
     "label": "conta de topo ou administrativa não é usada no dia a dia",
     "members": [
         M("aws", "2.6", r"eliminate use of the 'root' user for administrative and daily tasks",
           principal=("eq", "root")),
         M("azurerm", "5.3.1", r"admin accounts are not used for daily operations", principal=("eq", "admin")),
     ]},
    {"id": "SEC-WORKLOAD-IDENTITY", "domain": "SEC",
     "label": "máquina acessa a nuvem com identidade de carga de trabalho, sem chave embutida",
     "members": [
         M("aws", "2.17", r"iam instance roles are used for aws resource access from instances"),
         M("oci", "1.14", r"instance principal authentication is used"),
     ]},
    {"id": "SEC-SECURITY-CONTACT", "domain": "SEC", "label": "contato de segurança registrado no provedor",
     "members": [
         M("aws", "2.2", r"security contact information is registered"),
         M("google", "1.16", r"essential contacts is configured for organization"),
         M("azurerm", "8.1.13", r"'additional email addresses' is configured with a security contact email"),
     ]},
    {"id": "SEC-KMS-KEY-ROTATION", "domain": "SEC", "label": "chave de cifra gerida pelo cliente é rotacionada",
     "members": [
         M("aws", "4.6", r"rotation for customer-created symmetric cmks is enabled"),
         M("google", "1.10", r"kms encryption keys are rotated within a period of 90 days", period_days=("max", 90)),
         M("azurerm", "8.3.9", r"automatic key rotation is enabled within azure key vault"),
         M("oci", "4.16", r"customer managed key \(cmk\) is rotated at least annually", period_days=("max", 365)),
     ]},
    {"id": "SEC-POSTURE-SERVICE", "domain": "SEC",
     "label": "serviço nativo de postura de segurança ligado",
     "members": [
         M("aws", "5.16", r"aws security hub is enabled"),
         M("azurerm", "8.1.1.1", r"microsoft defender cspm is set to 'on'"),
         M("oci", "4.14", r"cloud guard is enabled in the root compartment"),
     ]},
    # ---------------- rede (NET) ----------------
    {"id": "NET-SSH-FROM-ANYWHERE", "domain": "NET",
     "label": "filtro de entrada não abre a porta 22 para qualquer origem",
     "members": [
         M("aws", "6.2", r"no network acls allow ingress from 0\.0\.0\.0/0 to remote server administration ports",
           ports=("forbid", (22, 3389)), sources=("forbid", (ANY4,)), filter=("eq", "stateless_list")),
         M("aws", "6.3", r"no security groups allow ingress from 0\.0\.0\.0/0 to remote server administration ports",
           ports=("forbid", (22, 3389)), sources=("forbid", (ANY4,)), filter=("eq", "stateful_group")),
         M("aws", "6.4", r"no security groups allow ingress from ::/0 to remote server administration ports",
           ports=("forbid", (22, 3389)), sources=("forbid", (ANY6,)), filter=("eq", "stateful_group")),
         M("google", "3.6", r"ssh access is restricted from the internet", ports=("forbid", (22,)),
           sources=("forbid", INTERNET), filter=("eq", "stateful_group")),
         M("azurerm", "7.2", r"ssh access from the internet is evaluated and restricted", ports=("forbid", (22,)),
           sources=("forbid", INTERNET), filter=("eq", "stateful_group")),
         M("oci", "2.1", r"no security lists allow ingress from 0\.0\.0\.0/0 to port 22", ports=("forbid", (22,)),
           sources=("forbid", (ANY4,)), filter=("eq", "stateless_list")),
         M("oci", "2.3", r"no network security groups allow ingress from 0\.0\.0\.0/0 to port 22",
           ports=("forbid", (22,)), sources=("forbid", (ANY4,)), filter=("eq", "stateful_group")),
     ]},
    {"id": "NET-RDP-FROM-ANYWHERE", "domain": "NET",
     "label": "filtro de entrada não abre a porta 3389 para qualquer origem",
     "members": [
         M("aws", "6.2", r"no network acls allow ingress from 0\.0\.0\.0/0 to remote server administration ports",
           ports=("forbid", (22, 3389)), sources=("forbid", (ANY4,)), filter=("eq", "stateless_list")),
         M("aws", "6.3", r"no security groups allow ingress from 0\.0\.0\.0/0 to remote server administration ports",
           ports=("forbid", (22, 3389)), sources=("forbid", (ANY4,)), filter=("eq", "stateful_group")),
         M("aws", "6.4", r"no security groups allow ingress from ::/0 to remote server administration ports",
           ports=("forbid", (22, 3389)), sources=("forbid", (ANY6,)), filter=("eq", "stateful_group")),
         M("google", "3.7", r"rdp access is restricted from the internet", ports=("forbid", (3389,)),
           sources=("forbid", INTERNET), filter=("eq", "stateful_group")),
         M("azurerm", "7.1", r"rdp access from the internet is evaluated and restricted", ports=("forbid", (3389,)),
           sources=("forbid", INTERNET), filter=("eq", "stateful_group")),
         M("oci", "2.2", r"no security lists allow ingress from 0\.0\.0\.0/0 to port 3389",
           ports=("forbid", (3389,)), sources=("forbid", (ANY4,)), filter=("eq", "stateless_list")),
         M("oci", "2.4", r"no network security groups allow ingress from 0\.0\.0\.0/0 to port 3389",
           ports=("forbid", (3389,)), sources=("forbid", (ANY4,)), filter=("eq", "stateful_group")),
     ]},
    {"id": "NET-DEFAULT-FILTER-DENY", "domain": "NET",
     "label": "o filtro padrão da rede virtual não deixa passar tráfego",
     "members": [
         M("aws", "6.5", r"default security group of every vpc restricts all traffic"),
         M("oci", "2.5", r"default security list of every vcn restricts all traffic except icmp within vcn",
           exceptions=("allow", ("icmp_within_network",))),
     ]},
    {"id": "NET-FLOW-LOGS", "domain": "NET", "label": "registro de fluxo de rede ligado",
     "members": [
         M("aws", "4.7", r"vpc flow logging is enabled in all vpcs", scope=("eq", "network")),
         M("google", "3.8", r"vpc flow logs is enabled for every subnet", scope=("eq", "subnet")),
         M("azurerm", "6.1.1.5", r"network security group flow logs are captured and sent to log analytics",
           scope=("eq", "filter_group")),
         M("azurerm", "6.1.1.7", r"virtual network flow logs are captured and sent to log analytics",
           scope=("eq", "network")),
         M("oci", "4.13", r"vcn flow logging is enabled for all subnets", scope=("eq", "subnet")),
     ]},
    # ---------------- operação: trilha, alertas, inventário (OPS) ----------------
    {"id": "OPS-AUDIT-TRAIL", "domain": "OPS", "label": "trilha de auditoria do plano de controle ligada e retida",
     "members": [
         M("aws", "4.1", r"cloudtrail is enabled in all regions"),
         M("google", "2.1", r"cloud audit logging is configured properly"),
         M("azurerm", "6.1.1.1", r"'diagnostic setting' exists for subscription activity logs"),
     ]},
    {"id": "OPS-AUDIT-LOG-CMK", "domain": "OPS",
     "label": "a trilha de auditoria guardada é cifrada com chave do cliente",
     "members": [
         M("aws", "4.5", r"cloudtrail logs are encrypted at rest using kms cmks"),
         M("azurerm", "6.1.1.3", r"storage account containing the container with activity logs is encrypted with"
                                 r" customer-managed key"),
     ]},
    {"id": "OPS-AUDIT-LOG-TAMPER", "domain": "OPS",
     "label": "a trilha de auditoria guardada resiste a adulteração",
     "members": [
         M("aws", "4.2", r"cloudtrail log file validation is enabled", mechanism=("eq", "integrity_digest")),
         M("google", "2.3", r"retention policies on cloud storage buckets used for exporting logs are configured using"
                            r" bucket lock", mechanism=("eq", "retention_lock")),
     ]},
    {"id": "OPS-OBJECT-DATA-EVENTS", "domain": "OPS",
     "label": "eventos de dados de objeto (por objeto) registrados no armazenamento de objetos",
     "members": [
         M("aws", "4.8", r"object-level logging for write events is enabled for s3 buckets",
           events=("require", ("write",))),
         M("aws", "4.9", r"object-level logging for read events is enabled for s3 buckets",
           events=("require", ("read",))),
         M("oci", "4.17", r"write level object storage logging is enabled for all buckets",
           events=("require", ("write",))),
     ]},
    {"id": "OPS-CONFIG-INVENTORY", "domain": "OPS", "label": "inventário/histórico de configuração ligado",
     "members": [
         M("aws", "4.3", r"aws config is enabled in all regions"),
         M("google", "2.13", r"cloud asset inventory is enabled"),
     ]},
    {"id": "OPS-ALERT-NETFILTER-CHANGE", "domain": "OPS", "label": "alerta para mudança em filtro de rede",
     "members": [
         M("aws", "5.10", r"security group changes are monitored", ops=("require", CHANGES),
           filter=("eq", "stateful_group")),
         M("aws", "5.11", r"network access control list \(nacl\) changes are monitored", ops=("require", CHANGES),
           filter=("eq", "stateless_list")),
         M("google", "2.7", r"alerts exist for vpc network firewall rule changes", ops=("require", CHANGES),
           filter=("eq", "stateful_group")),
         M("azurerm", "6.1.2.3", r"activity log alert exists for create or update network security group",
           ops=("require", ("create", "update")), filter=("eq", "stateful_group")),
         M("azurerm", "6.1.2.4", r"activity log alert exists for delete network security group",
           ops=("require", ("delete",)), filter=("eq", "stateful_group")),
         M("oci", "4.10", r"notification is configured for security list changes", ops=("require", CHANGES),
           filter=("eq", "stateless_list")),
         M("oci", "4.11", r"notification is configured for network security group changes", ops=("require", CHANGES),
           filter=("eq", "stateful_group")),
     ]},
    {"id": "OPS-ALERT-ROUTE-CHANGE", "domain": "OPS", "label": "alerta para mudança em tabela de rotas",
     "members": [
         M("aws", "5.13", r"route table changes are monitored"),
         M("google", "2.8", r"alerts exist for vpc network route changes"),
         M("oci", "4.9", r"notification is configured for changes to route tables"),
     ]},
    {"id": "OPS-ALERT-NETWORK-CHANGE", "domain": "OPS", "label": "alerta para mudança na rede virtual",
     "members": [
         M("aws", "5.14", r"vpc changes are monitored"),
         M("google", "2.9", r"alerts exist for vpc network changes"),
         M("oci", "4.8", r"notification is configured for vcn changes"),
     ]},
    {"id": "OPS-ALERT-GATEWAY-CHANGE", "domain": "OPS", "label": "alerta para mudança em gateway de rede",
     "members": [
         M("aws", "5.12", r"changes to network gateways are monitored"),
         M("oci", "4.12", r"notification is configured for changes to network gateways"),
     ]},
    {"id": "OPS-ALERT-AUTHZ-POLICY-CHANGE", "domain": "OPS",
     "label": "alerta para mudança em política ou papel de autorização",
     "members": [
         M("aws", "5.4", r"iam policy changes are monitored", object=("eq", "policy")),
         M("google", "2.6", r"alerts exist for custom role changes", object=("eq", "custom_role")),
         M("oci", "4.6", r"notification is configured for iam policy changes", object=("eq", "policy")),
     ]},
    {"id": "OPS-ALERT-AUDIT-CONFIG-CHANGE", "domain": "OPS", "label": "alerta para mudança na configuração da auditoria",
     "members": [
         M("aws", "5.5", r"cloudtrail configuration changes are monitored"),
         M("google", "2.5", r"alerts exist for audit configuration changes"),
     ]},
    {"id": "OPS-ALERT-BUCKET-PERMISSION-CHANGE", "domain": "OPS",
     "label": "alerta para mudança na permissão do armazenamento de objetos",
     "members": [
         M("aws", "5.8", r"s3 bucket policy changes are monitored"),
         M("google", "2.10", r"alerts exist for cloud storage iam permission changes"),
     ]},
    # ---------------- armazenamento (STO) ----------------
    {"id": "STO-BUCKET-NOT-PUBLIC", "domain": "STO", "label": "contêiner de objetos não é acessível ao público",
     "members": [
         M("aws", "3.1.4", r"s3 is configured with 'block public access' enabled", form=("eq", "guard_setting")),
         M("google", "5.1", r"cloud storage bucket is not anonymously or publicly accessible", form=("eq", "state")),
         M("azurerm", "9.3.8", r"'allow blob anonymous access' is set to 'disabled'", form=("eq", "guard_setting")),
         M("oci", "5.1.1", r"no object storage buckets are publicly visible", form=("eq", "state")),
     ]},
    {"id": "STO-BUCKET-VERSIONING", "domain": "STO", "label": "versionamento de objetos ligado",
     "members": [
         M("azurerm", "9.2.3", r"'versioning' is set to 'enabled' on azure blob storage"),
         M("oci", "5.1.3", r"versioning is enabled for object storage buckets"),
     ]},
    {"id": "STO-TRANSPORT-ENCRYPTION", "domain": "STO",
     "label": "acesso ao armazenamento de objetos só por transporte cifrado",
     "members": [
         M("aws", "3.1.1", r"s3 bucket policy is set to deny http requests"),
         M("azurerm", "9.3.4", r"'secure transfer required' is set to 'enabled'"),
     ]},
    {"id": "STO-BLOCK-VOLUME-ENCRYPTION", "domain": "STO", "label": "volume de bloco cifrado em repouso",
     "members": [
         M("aws", "6.1.1", r"ebs volume encryption is enabled in all regions", key_control=("min", 1)),
         M("google", "4.7", r"vm disks for critical vms are encrypted with customer-supplied encryption keys",
           key_control=("min", 3)),
         M("oci", "5.2.1", r"block volumes are encrypted with customer managed keys", key_control=("min", 2),
           volume=("eq", "data")),
         M("oci", "5.2.2", r"boot volumes are encrypted with customer managed key", key_control=("min", 2),
           volume=("eq", "boot")),
     ]},
    {"id": "STO-FILE-SYSTEM-ENCRYPTION", "domain": "STO", "label": "sistema de arquivos gerenciado cifrado em repouso",
     "members": [
         M("aws", "3.3.1", r"encryption is enabled for efs file systems", key_control=("min", 1)),
         M("oci", "5.3.1", r"file storage systems are encrypted with customer managed keys", key_control=("min", 2)),
     ]},
    # ---------------- banco de dados (DB) ----------------
    {"id": "DB-NOT-PUBLIC", "domain": "DB", "label": "instância de banco gerenciado sem ponto de acesso público",
     "members": [
         M("aws", "3.2.3", r"rds instances are not publicly accessible", form=("eq", "no_public_endpoint")),
         M("google", "6.6", r"cloud sql database instances do not have public ips", form=("eq", "no_public_endpoint")),
         M("oci", "2.8", r"autonomous shared databases \(adb\) access is restricted to allowed sources or deployed"
                         r" within a virtual cloud network", form=("eq", "allowlist_or_private")),
     ]},
    # ---------------- computação (CMP) ----------------
    {"id": "CMP-METADATA-LEGACY-OFF", "domain": "CMP",
     "label": "serviço de metadados da instância só na versão com sessão (legado desligado)",
     "members": [
         M("aws", "6.7", r"ec2 metadata service only allows imdsv2"),
         M("oci", "3.1", r"legacy metadata service endpoint is disabled"),
     ]},
    {"id": "CMP-BOOT-INTEGRITY", "domain": "CMP", "label": "inicialização verificada da instância",
     "members": [
         M("google", "4.8", r"launched with shielded vm enabled", feature=("eq", "shielded_vm")),
         M("oci", "3.2", r"secure boot is enabled on compute instance", feature=("eq", "secure_boot")),
     ]},
    {"id": "CMP-OS-UPDATES", "domain": "CMP", "label": "atualizações do sistema operacional das VMs acompanhadas",
     "members": [
         M("google", "4.12", r"latest operating system updates are installed", form=("eq", "installed_state")),
         M("azurerm", "8.1.10", r"configured to check vm operating systems for updates", form=("eq", "assessment_on")),
     ]},
]

# Pares de títulos parecidos (auditoria lexical) que a curadoria leu e decidiu NÃO alinhar, com o motivo.
# Chave: (provedor, item, provedor, item) na ordem do index_set.
REVIEWED_NON_MATCHES = {
    ("azurerm", "2.1.8", "oci", "5.2.1"): "objetos diferentes: dados do Databricks x volume de bloco",
    ("google", "3.6", "azurerm", "7.1"): "portas disjuntas: 22 x 3389",
    ("google", "3.6", "azurerm", "7.3"): "protocolos disjuntos: SSH (TCP 22) x UDP qualquer",
    ("google", "3.7", "azurerm", "7.2"): "portas disjuntas: 3389 x 22",
    ("google", "3.7", "azurerm", "7.3"): "protocolos disjuntos: RDP (TCP 3389) x UDP qualquer",
}
