"""Catálogo fixado das fontes do GOLD-XPLANE (composições e providers), com commit, licença e escolha declarada.

Critério de inclusão (declarado antes de extrair): repositório público com licença explícita no commit fixado, com
pelo menos duas composições do MESMO XR (mesmo apiVersion/kind de compositeTypeRef) para provedores diferentes,
escritas em patch-and-transform (modo Resources ou passo function-patch-and-transform do modo Pipeline). Fica
de fora o que exige executar código para obter os patches (KCL, CUE/Timoni, go-templating, Python).

Exclusões registradas (no summary.json): vfarcic/crossplane-sql (sem arquivo de licença enquanto as composições
eram YAML; LICENSE só em 2025-04, depois da migração para KCL) e vfarcic/crossplane-kubernetes (sem licença; a
partir de 2024-05 em KCL).
"""
from __future__ import annotations

# --------------------------------------------------------------------------------------------- composições
# role: "top" = XR multi-provedor de entrada; "nested" = configuração da qual um XR de topo depende (os patches
# dela levam o campo do XR aninhado até o MR). provider_pins: família de API -> (repositório, tag) do provider.
COMPOSITION_SOURCES = [
    {
        "id": "xp-snippets",
        "repo": "crossplane/crossplane",
        "ref": "v1.10.4",
        "commit": "d10c0f81f81f33c793896a94d29961a74d5e2ecf",
        "license": "Apache-2.0",
        "family": "crossplane-docs",
        "role": "top",
        "files": [
            "docs/snippets/package/definition.yaml",
            "docs/snippets/package/aws/composition.yaml",
            "docs/snippets/package/aws/crossplane.yaml",
            "docs/snippets/package/aws-with-vpc/composition.yaml",
            "docs/snippets/package/aws-with-vpc/crossplane.yaml",
            "docs/snippets/package/gcp/composition.yaml",
            "docs/snippets/package/gcp/crossplane.yaml",
            "docs/snippets/package/azure/composition.yaml",
            "docs/snippets/package/azure/crossplane.yaml",
        ],
        # crossplane.yaml de cada snippet pede faixa (>=); fixamos o limite inferior (escolha declarada).
        "provider_pins": {
            "aws-classic": ("crossplane-contrib/provider-aws", "v0.24.1"),
            "gcp-classic": ("crossplane-contrib/provider-gcp", "v0.20.0"),
            "azure-classic": ("crossplane-contrib/provider-azure", "v0.18.1"),
        },
        "pin_rule": "limite inferior da faixa em docs/snippets/package/<p>/crossplane.yaml",
    },
    {
        "id": "dtk",
        "repo": "vfarcic/devops-toolkit-crossplane",
        "ref": "master",
        "commit": "8d54d4ceae752f652174b33ead7aebd9abd0d1c9",
        "license": "MIT",
        "family": "vfarcic",
        "role": "top",
        "files": [
            "packages/sql/definition.yaml",
            "packages/sql/aws.yaml",
            "packages/sql/aws-official.yaml",
            "packages/sql/azure.yaml",
            "packages/sql/azure-official.yaml",
            "packages/sql/gcp.yaml",
            "packages/sql/gcp-official.yaml",
            "packages/sql/local-k8s.yaml",
            "packages/sql/crossplane.yaml",
            "packages/k8s/definition.yaml",
            "packages/k8s/eks.yaml",
            "packages/k8s/gke.yaml",
            "packages/k8s/gke-official.yaml",
            "packages/k8s/aks.yaml",
            "packages/k8s/aks-official.yaml",
            "packages/k8s/civo.yaml",
            "packages/k8s/crossplane.yaml",
            "crossplane-config/provider-aws.yaml",
            "crossplane-config/provider-aws-official.yaml",
            "crossplane-config/provider-gcp.yaml",
            "crossplane-config/provider-gcp-official.yaml",
            "crossplane-config/provider-azure.yaml",
            "crossplane-config/provider-azure-official.yaml",
            "crossplane-config/provider-civo.yaml",
        ],
        "provider_pins": {
            "aws-classic": ("crossplane-contrib/provider-aws", "v0.29.0"),
            "aws-upjet": ("upbound/provider-aws", "v0.24.0"),
            "gcp-classic": ("crossplane-contrib/provider-gcp", "v0.21.0"),
            "gcp-upjet": ("upbound/provider-gcp", "v0.30.0"),
            "azure-jet": ("crossplane-contrib/provider-jet-azure", "v0.12.0"),
            "azure-upjet": ("upbound/provider-azure", "v0.22.0"),
        },
        "pin_rule": "spec.package de crossplane-config/provider-*.yaml no mesmo commit",
    },
    {
        "id": "mk8s",
        "repo": "upbound/platform-ref-multi-k8s",
        "ref": "main",
        "commit": "f2df0d8e3c80d598535dcba554466e891ce250d1",
        "license": "Apache-2.0",
        "family": "upbound",
        "role": "top",
        "files": ["apis/definition.yaml", "apis/composition.yaml", "crossplane.yaml"],
        "provider_pins": {},
        "pin_rule": "dependsOn de crossplane.yaml (versões exatas das configurações aninhadas)",
    },
    {
        "id": "up-aws-network", "repo": "upbound/configuration-aws-network", "ref": "v0.10.0",
        "commit": "daea01f7989d2989914cf8a9b9a778b51633f8b1", "license": "Apache-2.0", "family": "upbound",
        "role": "nested", "files": ["apis/definition.yaml", "apis/basic/composition.yaml", "crossplane.yaml"],
        "provider_pins": {"aws-upjet": ("upbound/provider-aws", "v0.47.1")},
        "pin_rule": "dependsOn de crossplane.yaml (provider-aws-ec2 v0.47.1)",
    },
    {
        "id": "up-aws-eks", "repo": "upbound/configuration-aws-eks", "ref": "v0.8.0",
        "commit": "2e1882f21f9986fcb900544d699d9d34119e2863", "license": "Apache-2.0", "family": "upbound",
        "role": "nested", "files": ["apis/definition.yaml", "apis/composition.yaml", "crossplane.yaml"],
        "provider_pins": {"aws-upjet": ("upbound/provider-aws", "v0.47.1")},
        "pin_rule": "dependsOn de crossplane.yaml (provider-aws-{ec2,eks,iam} v0.47.1)",
    },
    {
        "id": "up-azure-network", "repo": "upbound/configuration-azure-network", "ref": "v0.5.0",
        "commit": "3f3f7dd9bf2752e56f86ae30278d8999ce6d8e07", "license": "Apache-2.0", "family": "upbound",
        "role": "nested", "files": ["apis/definition.yaml", "apis/default/composition.yaml", "crossplane.yaml"],
        "provider_pins": {"azure-upjet": ("upbound/provider-azure", "v0.42.0")},
        "pin_rule": "dependsOn de crossplane.yaml (provider-azure-network v0.42.0)",
    },
    {
        "id": "up-azure-aks", "repo": "upbound/configuration-azure-aks", "ref": "v0.4.0",
        "commit": "aa721d20c76509cd43be45be96e9dc60afdc1385", "license": "Apache-2.0", "family": "upbound",
        "role": "nested", "files": ["apis/definition.yaml", "apis/composition.yaml", "crossplane.yaml"],
        "provider_pins": {"azure-upjet": ("upbound/provider-azure", "v0.42.0")},
        "pin_rule": "dependsOn de crossplane.yaml (provider-azure-containerservice v0.42.0)",
    },
    {
        "id": "up-gcp-network", "repo": "upbound/configuration-gcp-network", "ref": "v0.2.0",
        "commit": "95a1da332941274c5a25b1993f0cc3325b2fa51e", "license": "Apache-2.0", "family": "upbound",
        "role": "nested", "files": ["apis/definition.yaml", "apis/default/composition.yaml", "crossplane.yaml"],
        "provider_pins": {"gcp-upjet": ("upbound/provider-gcp", "v0.41.1")},
        "pin_rule": "dependsOn de crossplane.yaml (provider-gcp-compute v0.41.1)",
    },
    {
        "id": "up-gcp-gke", "repo": "upbound/configuration-gcp-gke", "ref": "v0.2.0",
        "commit": "8d148ebf93b65adbae8e997d44b4fd1bbcaca47a", "license": "Apache-2.0", "family": "upbound",
        "role": "nested", "files": ["apis/definition.yaml", "apis/composition.yaml", "crossplane.yaml"],
        "provider_pins": {"gcp-upjet": ("upbound/provider-gcp", "v0.41.1")},
        "pin_rule": "dependsOn de crossplane.yaml (provider-gcp-{compute,container,cloudplatform} v0.41.1)",
    },
]

EXCLUDED_SOURCES = [
    {"repo": "vfarcic/crossplane-sql", "reason": "sem licença no período em que as composições eram YAML "
     "(LICENSE adicionado em 2025-04-19, depois da migração para KCL em 2024-09)"},
    {"repo": "vfarcic/crossplane-kubernetes", "reason": "sem arquivo de licença; desde 2024-05 as composições são KCL"},
]

# ------------------------------------------------------------------------------------------------ providers
# Commit resolvido da tag (git rev-parse <tag>^{commit}) na hora do fetch; conferido de novo pelo build.
PROVIDER_REPOS = {
    ("crossplane-contrib/provider-aws", "v0.24.1"): {"kind": "classic", "license": "Apache-2.0"},
    ("crossplane-contrib/provider-aws", "v0.29.0"): {"kind": "classic", "license": "Apache-2.0"},
    ("crossplane-contrib/provider-gcp", "v0.20.0"): {"kind": "classic", "license": "Apache-2.0"},
    ("crossplane-contrib/provider-gcp", "v0.21.0"): {"kind": "classic", "license": "Apache-2.0"},
    ("crossplane-contrib/provider-azure", "v0.18.1"): {"kind": "classic", "license": "Apache-2.0"},
    ("crossplane-contrib/provider-jet-azure", "v0.12.0"): {"kind": "upjet", "license": "Apache-2.0"},
    ("upbound/provider-aws", "v0.24.0"): {"kind": "upjet", "license": "Apache-2.0"},
    ("upbound/provider-aws", "v0.47.1"): {"kind": "upjet", "license": "Apache-2.0"},
    ("upbound/provider-gcp", "v0.30.0"): {"kind": "upjet", "license": "Apache-2.0"},
    ("upbound/provider-gcp", "v0.41.1"): {"kind": "upjet", "license": "Apache-2.0"},
    ("upbound/provider-azure", "v0.22.0"): {"kind": "upjet", "license": "Apache-2.0"},
    ("upbound/provider-azure", "v0.42.0"): {"kind": "upjet", "license": "Apache-2.0"},
}

# família de API do MR (pelo grupo do apiVersion) -> (provider neutro do projeto | None, família de pin)
# None = fora dos 4 provedores do projeto (aws, google, azurerm, oci): o par é extraído mas não vira linha SSSOM.
def api_family(group: str):
    g = group.lower()
    if g == "aws.crossplane.io" or g.endswith(".aws.crossplane.io"):
        return "aws", "aws-classic"
    if g == "aws.upbound.io" or g.endswith(".aws.upbound.io"):
        return "aws", "aws-upjet"
    if g == "gcp.crossplane.io" or g.endswith(".gcp.crossplane.io"):
        return "google", "gcp-classic"
    if g == "gcp.upbound.io" or g.endswith(".gcp.upbound.io"):
        return "google", "gcp-upjet"
    if g == "azure.jet.crossplane.io" or g.endswith(".azure.jet.crossplane.io"):
        return "azurerm", "azure-jet"
    if g == "azure.crossplane.io" or g.endswith(".azure.crossplane.io"):
        return "azurerm", "azure-classic"
    if g == "azure.upbound.io" or g.endswith(".azure.upbound.io"):
        return "azurerm", "azure-upjet"
    if g.endswith("oci.upbound.io") or g.endswith(".oci.crossplane.io"):
        return "oci", "oci"
    return None, None


def source_by_id(sid: str) -> dict:
    for s in COMPOSITION_SOURCES:
        if s["id"] == sid:
            return s
    raise KeyError(sid)
