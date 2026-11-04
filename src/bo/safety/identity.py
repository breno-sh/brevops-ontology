"""Identidade efetiva (§10.2): imediatamente antes de cada apply, ler a identidade da sessão e casar com a
allowlist privada de contas sandbox. Não casou, aborta. A conta nunca é inferida do ambiente sem esta checagem.

Allowlist: ~/.config/bo/allowlist (BO_ALLOWLIST só nos testes), escrita pelo Breno, chmod 600, fora de qualquer
repositório git. Uma linha por identidade:
    <provedor> sha256:<hex64> [rótulo]       (recomendado: só o hash)
    <provedor> <identidade canônica> [rótulo]  (aceito: vira hash ao carregar; nunca é impresso)
Identidade canônica por provedor (a mesma que o provider do Terraform usará, garantida pelas checagens de env):
    aws      aws|account=<Account>                          sts get-caller-identity; usuário root recusado
    google   google|project=<project>|account=<account>     gcloud config list; o runner exporta o token do
                                                            mesmo gcloud (GOOGLE_OAUTH_ACCESS_TOKEN) e o projeto
    azurerm  azurerm|subscription=<id>|tenant=<tenantId>    az account show; ARM_SUBSCRIPTION_ID = a conferida
    oci      oci|tenancy=<tenancy>|user=<user>              perfil do ~/.oci/config + oci iam user get
Só o sha256 da identidade sai daqui (C16 effective_identity_check); o id nunca é gravado nem impresso.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from configparser import ConfigParser
from datetime import timedelta
from pathlib import Path

from .common import PROVIDERS, SafetyError, inside_git_repo, iso, now_dt, parse_iso, sha256_text

FRESH_SECONDS = 300
HASH_LINE = re.compile(r"^sha256:([0-9a-f]{64})$")


class IdentityRefused(SafetyError):
    def __init__(self, msg):
        super().__init__(msg, "IDENTITY")


def allowlist_path() -> Path:
    return Path(os.environ.get("BO_ALLOWLIST") or (Path.home() / ".config" / "bo" / "allowlist"))


def identity_hash(canonical: str) -> str:
    return sha256_text(canonical)


def load_allowlist(path: Path | None = None) -> dict[str, set[str]]:
    """{provedor: {sha256}}. Recusa arquivo ausente, link, permissão aberta, dono diferente ou dentro de repo."""
    p = Path(path or allowlist_path())
    if not p.exists():
        raise IdentityRefused(f"allowlist privada ausente ({p}); o Breno escreve (D2)")
    st = os.lstat(p)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise IdentityRefused("allowlist não é arquivo regular (link simbólico recusado)")
    if st.st_mode & 0o077:
        raise IdentityRefused(f"allowlist com permissão {oct(st.st_mode & 0o777)}; exige 600")
    if hasattr(os, "getuid") and st.st_uid != os.getuid():
        raise IdentityRefused("allowlist pertence a outro usuário")
    repo = inside_git_repo(p.parent)
    if repo is not None:
        raise IdentityRefused("allowlist dentro de um repositório git; tem de ficar no canal privado")
    out: dict[str, set[str]] = {k: set() for k in PROVIDERS}
    for n, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        parts = ln.split()
        if len(parts) < 2 or parts[0] not in PROVIDERS:
            raise IdentityRefused(f"allowlist linha {n}: formato '<provedor> sha256:<hex>|<identidade> [rótulo]'")
        m = HASH_LINE.match(parts[1])
        out[parts[0]].add(m.group(1) if m else identity_hash(parts[1]))
    return out


# --------------------------------------------------------------------------------------------- leitores
def _default_run(argv, env):
    r = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    return r.returncode, r.stdout


def _json(run, argv, env, what):
    rc, out = run(argv, env)
    if rc != 0:
        raise IdentityRefused(f"leitura da identidade falhou ({what}, código {rc}); sem identidade, sem apply")
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise IdentityRefused(f"resposta de {what} não é JSON") from None


ENV_REFUSE = {
    # variáveis que mudam a identidade do provider do Terraform sem passar pela leitura conferida
    "aws": [],
    "google": ["GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CREDENTIALS", "GOOGLE_CLOUD_KEYFILE_JSON",
               "GCLOUD_KEYFILE_JSON", "GOOGLE_IMPERSONATE_SERVICE_ACCOUNT"],
    "azurerm": ["ARM_CLIENT_ID", "ARM_CLIENT_SECRET", "ARM_CLIENT_CERTIFICATE_PATH", "ARM_USE_MSI", "ARM_USE_OIDC",
                "ARM_OIDC_TOKEN", "ARM_TENANT_ID"],
    "oci": ["OCI_CLI_AUTH", "TF_VAR_private_key", "TF_VAR_private_key_path", "OCI_PRIVATE_KEY_PATH"],
}


def env_conflicts(provider: str, env: dict) -> list[str]:
    probs = [f"{k} definido (a identidade do Terraform não seria a conferida)" for k in ENV_REFUSE[provider]
             if env.get(k)]
    if provider == "aws":
        # o sts e o provider aws leem a MESMA cadeia (env, perfil, SSO); só um perfil explícito por bloco provider
        # escaparia, e isso o plan_guard recusa. Chaves no ambiente e perfil ao mesmo tempo é ambíguo.
        if env.get("AWS_ACCESS_KEY_ID") and env.get("AWS_PROFILE"):
            probs.append("AWS_ACCESS_KEY_ID e AWS_PROFILE ao mesmo tempo (identidade ambígua)")
    return probs


def read_identity(provider: str, env: dict | None = None, run=None) -> str:
    """Identidade canônica (texto, só em memória)."""
    env = dict(os.environ if env is None else env)
    run = run or _default_run
    bad = env_conflicts(provider, env)
    if bad:
        raise IdentityRefused("; ".join(bad))
    if provider == "aws":
        d = _json(run, ["aws", "sts", "get-caller-identity", "--output", "json"], env, "sts get-caller-identity")
        acct, principal = str(d.get("Account", "")), str(d.get("Arn", ""))
        if not re.fullmatch(r"\d{12}", acct):
            raise IdentityRefused("sts não devolveu conta")
        if principal.endswith(":root"):
            raise IdentityRefused("sessão é o usuário root da conta; use identidade restrita")
        return f"aws|account={acct}"
    if provider == "google":
        d = _json(run, ["gcloud", "config", "list", "--format=json"], env, "gcloud config list")
        core = d.get("core", {})
        proj, acct = core.get("project"), core.get("account")
        if not proj or not acct:
            raise IdentityRefused("gcloud sem projeto ou conta ativa")
        if env.get("GOOGLE_PROJECT") and env["GOOGLE_PROJECT"] != proj:
            raise IdentityRefused("GOOGLE_PROJECT difere do projeto do gcloud conferido")
        return f"google|project={proj}|account={acct}"
    if provider == "azurerm":
        d = _json(run, ["az", "account", "show", "-o", "json"], env, "az account show")
        sub, ten = d.get("id"), d.get("tenantId")
        if not sub or not ten:
            raise IdentityRefused("az sem subscription ativa")
        if env.get("ARM_SUBSCRIPTION_ID") and env["ARM_SUBSCRIPTION_ID"] != sub:
            raise IdentityRefused("ARM_SUBSCRIPTION_ID difere da subscription conferida")
        return f"azurerm|subscription={sub}|tenant={ten}"
    if provider == "oci":
        cfg_path = Path(env.get("OCI_CLI_CONFIG_FILE") or Path(env.get("HOME", str(Path.home()))) / ".oci" / "config")
        prof = env.get("OCI_CLI_PROFILE") or "DEFAULT"
        cp = ConfigParser()
        if not cp.read(cfg_path):
            raise IdentityRefused("configuração do oci ausente")
        sec = cp[prof] if prof in cp else cp.defaults() if prof == "DEFAULT" else None
        if not sec or not sec.get("tenancy") or not sec.get("user"):
            raise IdentityRefused(f"perfil oci {prof} sem tenancy/usuário")
        ten, usr = sec.get("tenancy"), sec.get("user")
        d = _json(run, ["oci", "iam", "user", "get", "--user-id", usr, "--profile", prof], env, "oci iam user get")
        data = d.get("data", {})
        if data.get("id") != usr or data.get("lifecycle-state") != "ACTIVE":
            raise IdentityRefused("oci iam não confirmou o usuário do perfil")
        return f"oci|tenancy={ten}|user={usr}"
    raise IdentityRefused(f"provedor desconhecido: {provider}")


def check(provider: str, env: dict | None = None, run=None, allowlist: Path | None = None) -> dict:
    """effective_identity_check do C16. Levanta IdentityRefused se não casar (o chamador aborta)."""
    allowed = load_allowlist(allowlist)
    h = identity_hash(read_identity(provider, env, run))
    res = {"identity_sha256": h, "checked_at": iso(now_dt()), "matches_allowlist": h in allowed[provider]}
    if not res["matches_allowlist"]:
        raise IdentityRefused(f"identidade {provider} ({h[:12]}…) fora da allowlist sandbox; abortado")
    return res


def require_fresh(chk: dict | None, max_age_s: int = FRESH_SECONDS, now=None) -> None:
    """A conferência tem de ser de agora há pouco (imediatamente antes do apply)."""
    if not chk or not chk.get("matches_allowlist"):
        raise IdentityRefused("sem identidade conferida que case com a allowlist")
    age = ((now or now_dt()) - parse_iso(chk["checked_at"])).total_seconds()
    if age < -5 or age > max_age_s:
        raise IdentityRefused(f"conferência de identidade velha ({int(age)} s > {max_age_s} s); confira de novo")


def same_identity(a: dict, b: dict) -> bool:
    return bool(a and b and a.get("identity_sha256") == b.get("identity_sha256"))


def expires(chk: dict) -> str:
    return iso(parse_iso(chk["checked_at"]) + timedelta(seconds=FRESH_SECONDS))
