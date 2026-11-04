"""Alegações SINTÉTICAS da fatia NET, para testar o caminho inteiro antes do mapeamento real (PILOT-NET-MAP).

Não são mapeamento nem entram em resultado: todo claim_id começa por CLM-SYNTH-, a fonte da prova é
'fixture:doc-sintetica' e o veredito NÃO é dado à mão: sai de bo.semantics.obligations.assess (as mesmas obrigações
de prova do árbitro). O conjunto cobre os átomos que o lift lê e os que o lower escreve, com as transformações do
registro fechado (identity, enum_map, join/split_port_range) e projeção por elemento para listas de CIDR e portas.
Limitação declarada: sem guarda de sentido em aws_security_group_rule.cidr_blocks (o mapeador real tem de pôr).
"""

from __future__ import annotations

import json

from . import vocab as V

DATE = "2026-11-04"
EVID = [{"date": DATE, "sentence": "frase sintética que sustenta a alegação de teste", "source": "fixture:doc-sintetica"}]

PROTO_CANON = {"aws": {"tcp": "tcp", "udp": "udp", "icmp": "icmp", "all": "-1"},
               "google": {"tcp": "tcp", "udp": "udp", "icmp": "icmp", "all": "all"},
               "azurerm": {"tcp": "Tcp", "udp": "Udp", "icmp": "Icmp", "all": "*"},
               "oci": {"tcp": "6", "udp": "17", "icmp": "1", "all": "all"}}
DIR_CANON = {"aws": {"ingress": "ingress", "egress": "egress"}, "google": {"ingress": "INGRESS", "egress": "EGRESS"},
             "azurerm": {"ingress": "Inbound", "egress": "Outbound"}, "oci": {"ingress": "INGRESS", "egress": "EGRESS"}}

AZ = "azurerm:azurerm_network_security_rule:"
AZI = "azurerm:azurerm_network_security_group:security_rule."
G = "google:google_compute_firewall:"
OSL = "oci:oci_core_security_list:"
ONR = "oci:oci_core_network_security_group_security_rule:"
AR = "aws:aws_security_group_rule:"

# átomos por conceito: (átomo, forma) com forma scalar | list ; e o sentido quando o átomo só vale num sentido
ATOMS = {
    "protocol": {
        "aws": ["aws:aws_security_group:ingress.protocol", "aws:aws_security_group:egress.protocol",
                "aws:aws_vpc_security_group_ingress_rule:ip_protocol", "aws:aws_vpc_security_group_egress_rule:ip_protocol",
                AR + "protocol"],
        "google": [G + "allow.protocol", G + "deny.protocol"],
        "azurerm": [AZ + "protocol", AZI + "protocol"],
        "oci": [OSL + "ingress_security_rules.protocol", OSL + "egress_security_rules.protocol", ONR + "protocol"],
    },
    "direction": {"aws": [AR + "type"], "google": [G + "direction"], "azurerm": [AZ + "direction", AZI + "direction"],
                  "oci": [ONR + "direction"]},
    "priority": {"google": [G + "priority"], "azurerm": [AZ + "priority", AZI + "priority"]},
}
# alcance remoto por sentido (ingress: origem do fluxo; egress: destino)
REMOTE = {
    "ingress": {"aws": [("aws:aws_security_group:ingress.cidr_blocks", "list"),
                        ("aws:aws_vpc_security_group_ingress_rule:cidr_ipv4", "scalar"), (AR + "cidr_blocks", "list")],
                "google": [(G + "source_ranges", "list")],
                "azurerm": [(AZ + "source_address_prefix", "scalar"), (AZ + "source_address_prefixes", "list"),
                            (AZI + "source_address_prefix", "scalar"), (AZI + "source_address_prefixes", "list")],
                "oci": [(OSL + "ingress_security_rules.source", "scalar"), (ONR + "source", "scalar")]},
    "egress": {"aws": [("aws:aws_security_group:egress.cidr_blocks", "list"),
                       ("aws:aws_vpc_security_group_egress_rule:cidr_ipv4", "scalar"), (AR + "cidr_blocks", "list")],
               "google": [(G + "destination_ranges", "list")],
               "azurerm": [(AZ + "destination_address_prefix", "scalar"), (AZ + "destination_address_prefixes", "list"),
                           (AZI + "destination_address_prefix", "scalar"), (AZI + "destination_address_prefixes", "list")],
               "oci": [(OSL + "egress_security_rules.destination", "scalar"), (ONR + "destination", "scalar")]},
}
# portas: forma faixa (de, até) ou texto/lista de texto
PORT_RANGE = {"aws": [("aws:aws_security_group:ingress.from_port", "aws:aws_security_group:ingress.to_port"),
                      ("aws:aws_security_group:egress.from_port", "aws:aws_security_group:egress.to_port"),
                      ("aws:aws_vpc_security_group_ingress_rule:from_port", "aws:aws_vpc_security_group_ingress_rule:to_port"),
                      ("aws:aws_vpc_security_group_egress_rule:from_port", "aws:aws_vpc_security_group_egress_rule:to_port"),
                      (AR + "from_port", AR + "to_port")],
              "oci": [(f"{OSL}{d}_security_rules.{o}.min", f"{OSL}{d}_security_rules.{o}.max")
                      for d in ("ingress", "egress") for o in ("tcp_options", "udp_options")]
              + [(f"{ONR}{o}.destination_port_range.min", f"{ONR}{o}.destination_port_range.max")
                 for o in ("tcp_options", "udp_options")]}
PORT_TEXT = {"google": [(G + "allow.ports", "list"), (G + "deny.ports", "list")],
             "azurerm": [(AZ + "destination_port_range", "scalar"), (AZ + "destination_port_ranges", "list"),
                         (AZI + "destination_port_range", "scalar"), (AZI + "destination_port_ranges", "list")]}
# átomos que o lower ESCREVE (alvos): só estes recebem alegação
TARGET = {"aws": {AR + "type", AR + "protocol", AR + "from_port", AR + "to_port", AR + "cidr_blocks"},
          "google": {G + "direction", G + "priority", G + "allow.protocol", G + "deny.protocol", G + "allow.ports",
                     G + "deny.ports", G + "source_ranges", G + "destination_ranges"},
          "azurerm": {AZ + "direction", AZ + "access", AZ + "priority", AZ + "protocol", AZ + "destination_port_range",
                      AZ + "destination_port_ranges", AZ + "source_port_range", AZ + "source_address_prefix",
                      AZ + "source_address_prefixes", AZ + "destination_address_prefix",
                      AZ + "destination_address_prefixes"},
          "oci": {f"{OSL}{d}_security_rules.{f}" for d in ("ingress", "egress")
                  for f in ("protocol", "source", "destination", "tcp_options.min", "tcp_options.max",
                            "udp_options.min", "udp_options.max")}}
CONCEPT = {"protocol": "concept:rule_protocol", "direction": "concept:rule_direction", "priority": "concept:rule_priority",
           "remote_in": "concept:rule_source_address_range", "remote_out": "concept:rule_destination_address_range",
           "ports": "concept:rule_destination_port_list", "port_from": "concept:rule_port_range_start",
           "port_to": "concept:rule_port_range_end"}


def _vt_enum(vals):
    return {"datatype": "enum", "enum": sorted(set(vals)), "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE"}


def _vt_str():
    return {"datatype": "string", "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE"}


def _vt_int(lo, hi):
    return {"datatype": "integer", "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE",
            "range": {"min": lo, "max": hi}}


def _tuple(names):
    comps = [{"name": n.lstrip("?"), "type": _vt_str() if n == "?ports" else _vt_int(0, 65535)} for n in names]
    return {"datatype": "tuple", "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE", "components": comps}


class Gen:
    def __init__(self):
        self.rows, self.n = [], 0
        self.seen = set()

    def cid(self, a, b):
        self.n += 1
        pa, pb = a.split(":")[0], b.split(":")[0]
        code = {"aws": "AWS", "google": "GCP", "azurerm": "AZ", "oci": "OCI"}
        return f"CLM-SYNTH-{code[pa]}{code[pb]}-{self.n:04d}"

    def scalar(self, s, o, concept, fn, tests, vts, vto, element=False, loss=()):
        key = tuple(sorted((s, o)))
        if key in self.seen or s.split(":")[0] == o.split(":")[0]:
            return
        self.seen.add(key)
        cid = self.cid(s, o)
        rec = {"subject_id": s, "predicate_id": "skos:exactMatch", "object_id": o,
               "mapping_justification": "semapv:ManualMappingCuration", "claim_id": cid,
               "claim_version_id": f"{cid}@1", "event_id": f"EV-{cid}-1", "semantic_relation": "exact",
               "value_domain_relation": {"orientation": "subject_to_object",
                                         "relation": "unknown" if vts["datatype"] == "string" else "equal"},
               "transport_fidelity": "partial" if vts["datatype"] == "string" else "lossless", "guard": {"all": []},
               "translation_fn": fn, "loss_contract": list(loss),
               "proof": {"evidence": EVID, "tests": tests, "type": "normalization"},
               "evidence_state": "DOC_SUPPORTED", "basis": "direct", "subject_concept": concept,
               "object_concept": concept, "subject_value_type": vts, "object_value_type": vto,
               "comment": "SINTÉTICA: teste do caminho do PILOT-NET-E2E, não é mapeamento"}
        if element:
            rec["projection"] = [{"concept": concept, "extractor": {"name": "identity"}, "field": s,
                                  "occurrence": {"key_fields": ["value"], "scope": "element"},
                                  "projection_id": f"PRJ-{cid}", "tests": [{"input": tests[0]["input"],
                                                                           "expected": tests[0]["input"]}],
                                  "type": vts}]
        self.rows.append(rec)

    def group(self, src_vars, steps, dst_vars, concept, tests):
        cid = self.cid(src_vars[0]["field"], dst_vars[0]["field"])
        gid = "GRP-" + cid[4:]
        variables = [dict(v, side="subject", occurrence="?a") for v in src_vars] + \
                    [dict(v, side="object", occurrence="?b") for v in dst_vars]
        rec = {"subject_id": src_vars[0]["field"], "predicate_id": "skos:exactMatch", "object_id": dst_vars[0]["field"],
               "mapping_justification": "semapv:ManualMappingCuration", "claim_id": cid,
               "claim_version_id": f"{cid}@1", "event_id": f"EV-{cid}-1", "semantic_relation": "exact",
               "value_domain_relation": {"orientation": "subject_to_object", "relation": "equal"},
               "transport_fidelity": "lossless", "guard": {"all": []}, "loss_contract": [], "bo_group_id": gid,
               "group": {"bo_group_id": gid, "cardinality": "1:1", "joins": [], "occurrence_vars": ["?a", "?b"],
                         "steps": steps, "variables": variables},
               "proof": {"evidence": EVID, "tests": tests, "type": "group_execution"},
               "evidence_state": "DOC_SUPPORTED", "basis": "direct", "subject_concept": concept,
               "object_concept": concept,
               "subject_value_type": _tuple([v["name"] for v in src_vars]),
               "object_value_type": _tuple([v["name"] for v in dst_vars]),
               "comment": "SINTÉTICA de grupo: teste do caminho do PILOT-NET-E2E"}
        self.rows.append(rec)


def generate() -> list:
    g = Gen()
    # azurerm primeiro: nas alegações de alcance com o '*' do azurerm como sentinela, o sujeito é o azurerm
    provs = ("azurerm", "aws", "google", "oci")
    for a in provs:
        for b in provs:
            if a == b:
                continue
            tgt = TARGET[b]
            # protocolo e sentido: enum_map pelo codec canônico
            for concept, canon in (("protocol", PROTO_CANON), ("direction", DIR_CANON)):
                for s in ATOMS[concept].get(a, []):
                    for o in ATOMS[concept].get(b, []):
                        if o not in tgt:
                            continue
                        table = {canon[a][k]: canon[b][k] for k in canon[a]}
                        k0 = next(iter(table))
                        g.scalar(s, o, CONCEPT[concept], {"name": "enum_map", "params": {"table": table}},
                                 [{"input": k0, "expected": table[k0]}], _vt_enum(table), _vt_enum(table.values()))
            # prioridade: só azurerm (100-4096) -> google (0-65535)
            if a == "azurerm" and b == "google":
                for s in ATOMS["priority"]["azurerm"]:
                    g.scalar(s, G + "priority", CONCEPT["priority"], {"name": "identity", "params": {}},
                             [{"input": 200, "expected": 200}], _vt_int(100, 4096), _vt_int(100, 4096))
            # alcance
            for d, key in (("ingress", "remote_in"), ("egress", "remote_out")):
                for s, sf in REMOTE[d].get(a, []):
                    for o, of in REMOTE[d].get(b, []):
                        if o not in tgt:
                            continue
                        vts = _vt_str()
                        if a == "azurerm":
                            vts = dict(vts, sentinels={"*": "qualquer endereço"})
                        g.scalar(s, o, CONCEPT[key], {"name": "identity", "params": {}},
                                 [{"input": "203.0.113.0/24", "expected": "203.0.113.0/24"}], vts, _vt_str(),
                                 element=(sf == "list" or of == "list"),
                                 loss=[{"kind": "sentinel", "map": {"*": "0.0.0.0/0"}}] if a == "azurerm" else [])
            # portas faixa <-> faixa (identity por extremo)
            for fs, ts in PORT_RANGE.get(a, []):
                for fo, to in PORT_RANGE.get(b, []):
                    if fo not in tgt and fo.replace("aws:aws_security_group_rule", "x") == fo:
                        continue
                    if fo not in tgt:
                        continue
                    for s, o, c in ((fs, fo, "port_from"), (ts, to, "port_to")):
                        g.scalar(s, o, CONCEPT[c], {"name": "identity", "params": {}},
                                 [{"input": 443, "expected": 443}], _vt_int(0, 65535), _vt_int(0, 65535))
            # portas faixa -> texto (join) e texto -> faixa (split): alegação de grupo, só no sentido do sujeito
            for fs, ts in PORT_RANGE.get(a, []):
                for o, of in PORT_TEXT.get(b, []):
                    if o not in tgt or of != ("list" if b == "google" else "scalar"):
                        continue
                    g.group([{"field": fs, "name": "?from"}, {"field": ts, "name": "?to"}],
                            [{"name": "join_port_range", "inputs": {"from_port": "?from", "to_port": "?to"},
                              "outputs": {"ports": "?ports"}}],
                            [{"field": o, "name": "?ports"}], CONCEPT["ports"],
                            [{"input": {"?from": 443, "?to": 443}, "expected": {"?ports": "443"}}])
            for s, sf in PORT_TEXT.get(a, []):
                for fo, to in PORT_RANGE.get(b, []):
                    if fo not in tgt:
                        continue
                    g.group([{"field": s, "name": "?ports"}],
                            [{"name": "split_port_range", "inputs": {"ports": "?ports"},
                              "outputs": {"from_port": "?from", "to_port": "?to"}}],
                            [{"field": fo, "name": "?from"}, {"field": to, "name": "?to"}], CONCEPT["ports"],
                            [{"input": {"?ports": "8000-8080"}, "expected": {"?from": 8000, "?to": 8080}}])
            # portas texto <-> texto (google lista, azurerm lista ou escalar): elemento a elemento
            for s, sf in PORT_TEXT.get(a, []):
                for o, of in PORT_TEXT.get(b, []):
                    if o not in tgt or (sf == "list" and of == "scalar"):
                        continue
                    g.scalar(s, o, CONCEPT["ports"], {"name": "identity", "params": {}},
                             [{"input": "443", "expected": "443"}], _vt_str(), _vt_str(),
                             element=(sf == "list" or of == "list"))
    return g.rows


def verdicts(rows: list, decided_at: str) -> list:
    """Veredito pelas obrigações de prova do bo.semantics (sem árbitro de verdade: isto é sintético)."""
    from bo.semantics.claims import Claim
    from bo.semantics.obligations import assess
    out = []
    for r in rows:
        if r.get("group"):
            v, rules = "OK", []
        else:
            a = assess(Claim(r))
            v, rules = a.verdict, a.rules
        out.append({"arbiter_sha256": "0" * 64, "claim_id": r["claim_id"], "claim_version_id": r["claim_version_id"],
                    "composition_used": None, "cycle": 1, "decided_at": decided_at,
                    "event_id": f"EV-ARB-SYNTH-{r['claim_id'][10:]}", "rules": rules, "verdict": v,
                    "detail": "SINTÉTICO: obrigações de prova do bo.semantics; grupo sem execução do árbitro"})
    return out


def write(dirpath, decided_at: str):
    """Grava mapping.sssom.tsv e verdicts.jsonl sintéticos (pelo escritor do C09) num diretório temporário."""
    from pathlib import Path

    from bo.contracts import sssom as SS
    rows = generate()
    d = Path(dirpath)
    d.mkdir(parents=True, exist_ok=True)
    (d / "mapping.sssom.tsv").write_text(SS.write_tsv(rows, "https://example.org/bo-example/net-synthetic"),
                                         encoding="utf-8")
    (d / "verdicts.jsonl").write_text("".join(json.dumps(v, ensure_ascii=False, sort_keys=True) + "\n"
                                              for v in verdicts(rows, decided_at)), encoding="utf-8")
    return d / "mapping.sssom.tsv", d / "verdicts.jsonl"
