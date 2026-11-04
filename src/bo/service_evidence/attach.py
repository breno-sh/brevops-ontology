"""Rodada final dos pilotos: atributos de anexação ligados ao campo da spec que liga o dono a um conjunto de regras.

Cada entrada: (provedor, tipo, atributo, bloco ou None, tipo-alvo, campo da spec). O campo é publicado (citação da
spec fixada); a ligação atributo <-> campo é INTERPRETADA (escolha do modelo, value.basis), porque nenhum nome
casa por regra mecânica (vpc_security_group_ids x Groups).
"""

from __future__ import annotations

from . import apispec as A
from . import common, sources

AZNET = "apispec-azurerm/network-2026-03-01-virtualNetwork.json"
EC2 = "apispec-aws/ec2-2016-11-15.json"
ENTRIES = [
    ("aws", "aws_instance", "vpc_security_group_ids", None, "aws_security_group",
     ("member", EC2, "/shapes/com.amazonaws.ec2#ModifyInstanceAttributeRequest/members/Groups"),
     "ModifyInstanceAttribute"),
    ("oci", "oci_core_instance", "nsg_ids", "create_vnic_details", "oci_core_network_security_group",
     ("model", "core", "create_vnic_details", "nsg_ids"), "CreateVnicDetails"),
    ("oci", "oci_core_vnic_attachment", "nsg_ids", "create_vnic_details", "oci_core_network_security_group",
     ("model", "core", "create_vnic_details", "nsg_ids"), "CreateVnicDetails"),
    ("azurerm", "azurerm_subnet_network_security_group_association", "network_security_group_id", None,
     "azurerm_network_security_group",
     ("def", AZNET, "/definitions/SubnetPropertiesFormat/properties/networkSecurityGroup"), "Subnets_CreateOrUpdate"),
    ("azurerm", "azurerm_network_interface_security_group_association", "network_security_group_id", None,
     "azurerm_network_security_group",
     ("def", AZNET, "/definitions/NetworkInterfacePropertiesFormat/properties/networkSecurityGroup"),
     "NetworkInterfaces_CreateOrUpdate"),
]


def run(ctxs: dict) -> dict:
    st = {"emitidos": 0, "faltando": []}
    for p, T, attr, bp, target, src, opname in ENTRIES:
        ctx = ctxs[p]
        if T not in set(sources.types(p)):
            st["faltando"].append(f"{p}:{T} fora do schema")
            continue
        path = f"{bp}.{attr}" if bp else attr
        if path not in {a[0] for a in sources.atoms(p).get(T, [])}:
            st["faltando"].append(f"{p}:{T}:{path} sem atributo")
            continue
        if src[0] == "model":
            hit = A.oci_model_field(src[1], src[2], src[3])
            if not hit:
                st["faltando"].append(f"{p}:{T} campo da spec não achado")
                continue
            f, ptr, _typ = hit
        else:
            f, ptr = src[1], src[2]
        try:
            cit = A.cite(p, f, ptr)
        except (KeyError, IndexError):
            st["faltando"].append(f"{p}:{T} ponteiro da spec não resolve")
            continue
        svc = {"aws": "ec2", "oci": "core", "azurerm": "Microsoft.Network"}[p]
        fld = src[3] if src[0] == "model" else A.unesc(ptr.split("/")[-1])
        owner_obj = src[2] if src[0] == "model" else A.unesc(ptr.split("/")[-3])
        api = {"service": svc, "resource": f"{owner_obj}.{fld}"}
        fid = ctx.add(T, "identity", f"attachfield:{f}:{ptr}", api, "stated", "published",
                      value={"aspect": "spec_field", "rule": "R-SPEC-OP", "field": api["resource"]}, cit=cit)
        v = {"aspect": "attachment_attribute", "rule": "R-ATTACH-SPEC", "attribute": path, "binds_to": target,
             "spec_field": api["resource"], "spec_operation": opname,
             "basis": "o campo da spec liga o objeto dono a regras de " + target + "; a correspondência com o "
                      "atributo Terraform é leitura do modelo (nomes não casam por regra)"}
        if bp:
            v["block_path"] = bp
        ctx.add(T, "identity", f"attach:{path}", api, "stated", "interpreted", value=v, derived=[fid],
                model=common.MODEL_ID)
        st["emitidos"] += 1
    return st
