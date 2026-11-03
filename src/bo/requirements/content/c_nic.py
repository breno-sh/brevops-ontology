"""Caso adversarial NIC: instância com 1 e com 2 interfaces; identidade estruturada e anexação."""

from ..model import cm, fx, ground

CONS = ["ONTPAT", "GRAIN", "GRAIN-REPRO", "DOMAIN-CONTRACTS", "AXIOMS", "SEMANTIC-REGRESSION", "CQFIX"]

G_NIC = [
    ground("aws", "aws_instance cria a interface primária implícita ou recebe blocos network_interface{device_index}; secundárias por aws_network_interface + aws_network_interface_attachment (standalone)"),
    ground("google", "google_compute_instance só aceita blocos network_interface{} embutidos; o índice (nic0, nic1) vem da ORDEM dos blocos: ali a ordem é campo de identidade"),
    ground("azurerm", "interfaces sempre standalone (azurerm_network_interface); a máquina recebe network_interface_ids, lista ordenada cuja primeira é a primária"),
    ground("oci", "a VNIC primária vem embutida em create_vnic_details de oci_core_instance; secundárias por oci_core_vnic_attachment"),
]


def _vm(fid, summary, n_nics, inline=False, extra=()):
    ents = "vm1:compute_instance sa:subnet " + " ".join(f"nic{i}:network_interface" for i in range(1, n_nics + 1))
    rels = [f"nic{i} attached_to vm1" for i in range(1, n_nics + 1)] + \
           [f"nic{i} in_subnet sa" for i in range(1, n_nics + 1)]
    attrs = ["vm1.local_key=vm_a"] + [f"nic{i}.device_index={i - 1}" for i in range(1, n_nics + 1)] + \
            [f"nic{i}.declared_inline={'true' if inline else 'false'}" for i in range(1, n_nics + 1)] + list(extra)
    return fx(fid, summary, ents, rels, attrs)


C = [
    cm("CMT-NIC-P01", "NIC", "positive", "count",
       "Uma instância com duas interfaces gera três recursos (uma instância e duas interfaces), cada interface "
       "ligada à instância por uma anexação com índice.",
       "COUNT recursos em {compute_instance, network_interface} = 3 AND COUNT anexações(vm1) = 2",
       _vm("FX-NIC-P01", "instância com duas interfaces na mesma sub-rede", 2),
       3, "interface tem identidade própria na API (componente ou entidade, nunca atributo da instância)",
       ["REQ-ENT-01", "REQ-ID-01"], ["F1"], "contagem de indivíduos por identidade, não por bloco",
       grounding=G_NIC, consumers=CONS),
    cm("CMT-NIC-P02", "NIC", "positive", "count",
       "Uma instância com uma interface gera dois recursos e uma anexação.",
       "COUNT recursos em {compute_instance, network_interface} = 2 AND COUNT anexações(vm1) = 1",
       _vm("FX-NIC-P02", "instância com uma interface", 1),
       2, "a interface única não some dentro da instância", ["REQ-ENT-01"], ["F1"],
       "interface única continua indivíduo", grounding=G_NIC[:1], consumers=CONS),
    cm("CMT-NIC-P03", "NIC", "positive", "invariant",
       "Acrescentar a segunda interface acrescenta um indivíduo e uma anexação e não muda o tipo da instância, "
       "o tipo da primeira interface nem a relação entre elas.",
       "relações(base) ⊂ relações(variante) AND tipo(vm1), tipo(nic1), anexação(nic1, vm1) iguais nas duas",
       [_vm("FX-NIC-P03-ONE", "base com uma interface", 1),
        _vm("FX-NIC-P03-TWO", "variante com duas interfaces", 2)],
       "INVARIANT", "invariância entre 1 e 2 NICs (F1)", ["REQ-ENT-01", "REQ-ID-01"], ["F1"],
       "estrutura de relações estável sob acréscimo", consumers=CONS),
    cm("CMT-NIC-P04", "NIC", "positive", "invariant",
       "Interface declarada como bloco embutido na instância e interface declarada como recurso separado com "
       "anexação produzem a mesma decomposição: a interface é indivíduo, anexado à instância, com o mesmo índice.",
       "unidades(embutida) == unidades(separada) a menos da camada Terraform",
       [_vm("FX-NIC-P04-INLINE", "interface secundária embutida", 2, inline=True),
        _vm("FX-NIC-P04-SEPARATE", "interface secundária separada com anexação", 2, inline=False)],
       "INVARIANT", "o grão não depende da embalagem", ["REQ-ENT-01"], ["F1"],
       "decomposição inline x standalone", layer="terraform", grounding=G_NIC, consumers=CONS),
    cm("CMT-NIC-P05", "NIC", "positive", "invariant",
       "Com índice declarado, trocar a ordem textual de dois blocos de interface não muda as identidades de "
       "ocorrência: elas dependem dos campos de identidade normalizados e do pai, não da posição. Onde o "
       "provedor deriva o índice da ordem, a ordem É campo de identidade e esta fixture não se aplica.",
       "occurrence_key(nic1) e occurrence_key(nic2) iguais em base e variante",
       [_vm("FX-NIC-P05-ORDER-A", "dois blocos embutidos na ordem 1, 2", 2, inline=True,
            extra=["nic1.text_position=1", "nic2.text_position=2"]),
        _vm("FX-NIC-P05-ORDER-B", "os mesmos blocos na ordem 2, 1", 2, inline=True,
            extra=["nic1.text_position=2", "nic2.text_position=1"])],
       "INVARIANT", "identidade de elemento anônimo estável sob reordenação (F1)", ["REQ-ID-01"], ["F1", "S2"],
       "identidade de ocorrência sem posição", layer="terraform", axes=["identity"],
       grounding=G_NIC[1:2], consumers=CONS),
    cm("CMT-NIC-N01", "NIC", "negative", "rejects",
       "Nenhum indivíduo é ao mesmo tempo instância de computação e interface de rede.",
       "fixture com x1 de tipo compute_instance e network_interface é inconsistente",
       fx("FX-NIC-N01", "indivíduo declarado instância e interface",
          "x1:compute_instance+network_interface", [], ["x1.local_key=vm_a"]),
       "REJECTED", "o exemplo canônico do F9: o reparo não pode passar a aceitar", ["REQ-ENT-02"], ["F9"],
       "disjunção instância x interface", code="INCONSISTENT", consumers=CONS),
    cm("CMT-NIC-N02", "NIC", "negative", "not_entails",
       "Com duas interfaces em duas sub-redes, a ontologia não pode concluir que as sub-redes são a mesma (o "
       "que aconteceria com uma propriedade funcional \"sub-rede da instância\"), nem que as duas interfaces "
       "são a mesma.",
       "NOT sa = sb AND NOT nic1 = nic2",
       fx("FX-NIC-N02", "duas interfaces em sub-redes distintas",
          "vm1:compute_instance nic1:network_interface nic2:network_interface sa:subnet sb:subnet",
          ["nic1 attached_to vm1", "nic2 attached_to vm1", "nic1 in_subnet sa", "nic2 in_subnet sb"],
          ["nic1.device_index=0", "nic2.device_index=1", "sa.local_key=sub_a", "sb.local_key=sub_b",
           "nic1.local_key=if_a", "nic2.local_key=if_b"]),
       "NOT_ENTAILED", "a sub-rede é da interface; funcionalidade no lugar errado gera igualdade espúria",
       ["REQ-ENT-01", "REQ-ID-01"], ["F1", "F9"], "ausência de igualdade inferida", consumers=CONS),
    cm("CMT-NIC-N03", "NIC", "negative", "not_entails",
       "Uma instância com duas interfaces não é contada como duas instâncias.",
       "NOT COUNT(compute_instance) = 2",
       _vm("FX-NIC-N03", "instância com duas interfaces (contagem de instâncias)", 2),
       "NOT_ENTAILED", "a interface não é unidade de instância", ["REQ-ENT-01"], ["F1"],
       "contagem por tipo correta", consumers=CONS),
    cm("CMT-NIC-U01", "NIC", "unknown", "unknown",
       "Se a anexação de uma interface existente não foi lida, o número de interfaces da instância é UNKNOWN, "
       "não 1.",
       "COUNT anexações(vm1) = UNKNOWN",
       fx("FX-NIC-U01", "segunda interface sem anexação lida",
          "vm1:compute_instance nic1:network_interface nic2:network_interface sa:subnet",
          ["nic1 attached_to vm1", "nic1 in_subnet sa", "nic2 in_subnet sa"],
          ["nic1.device_index=0"], complete=False, not_read=["nic2.attachment"]),
       "UNKNOWN", "negação de anexação só sob leitura completa", ["REQ-ABS-01"], ["F1", "S1"],
       "contagem UNKNOWN sob leitura parcial", code="INCOMPLETE_READ", consumers=CONS),
    cm("CMT-NIC-U02", "NIC", "unknown", "unknown",
       "Interface separada cuja referência de anexação não foi resolvida: a instância a que pertence é UNKNOWN.",
       "attached_to(nic3) = UNKNOWN",
       fx("FX-NIC-U02", "interface separada com referência não resolvida",
          "vm1:compute_instance nic3:network_interface", [], ["nic3.declared_inline=false"],
          complete=False, not_read=["nic3.reference"]),
       "UNKNOWN", "referência simbólica não resolvida não vira anexação", ["REQ-ABS-01", "REQ-ENT-01"],
       ["F1"], "anexação não inventada", code="UNKNOWN_SYMBOLIC_INPUT", consumers=CONS),
]
