"""Adaptador C25 por aspecto: tradução normativa dos fatos do SERVICE-EVIDENCE (value.aspect) em alegações.

O SERVICE-EVIDENCE grava os fatos de grão por aspecto (identity/resource_identity_schema, import_key/
import_formats, owner/identity_scope, lifecycle_controller/destroy_effect, ...). Esta tabela diz, aspecto a
aspecto, que alegação neutra cada fato vira. É normativa (o GRAIN-REPRO a segue; ela está em GRAIN.html,
gerada de TABLE abaixo). Princípios:
  * nada é inventado: aspecto sem tradução vira alegação UNKNOWN com o motivo, e fato com status unknown
    vira alegação UNKNOWN com o unknown_reason;
  * dono da IDENTIDADE (owner/identity_scope, owner/parent, owner/parent_attribute) não é dono da
    CONFIGURAÇÃO: esses aspectos só alimentam o escopo da identidade, nunca o campo owner;
  * destroy_effect "suspend" num recurso separado é indício de faceta do pai (ciclo de vida = pai, ligação com
    a API = aspecto); "not_deleted" e "state_only" dizem que o destroy não apaga, não quem apaga;
  * bloco aninhado só tem alegações se o SERVICE-EVIDENCE emitiu fato com block_path; sem elas, UNKNOWN (G0),
    nunca FACET por omissão;
  * nenhuma heurística de nome (block_schema.facet_word não é lido).
A fonte de cada alegação é {level: derived, ref: evidence_id, note: "<regra>: <aspecto>"}.
"""

from __future__ import annotations

from collections import defaultdict

GRAIN_FACTS = ("identity", "import_key", "lifecycle_controller", "owner", "effective_scope", "api_bridge")

# campos de identidade que nomeiam o escopo do provedor (conta, região, projeto, assinatura): não são unidades
PROVIDER_SCOPE_FIELDS = {
    "aws": {"account_id", "region"},
    "google": {"project", "project_id"},
    "azurerm": {"subscription_id"},
    "oci": set(),
}
# contenção de NAMESPACE (G4-NS): o contêiner qualifica o nome, mas não compõe a unidade; a marca vem do fato
# owner/parent (scope_kind) ou de um fato explícito namespace_container
NAMESPACE_KINDS = {"resource_group", "compartment"}
# escopos de contenção que são do provedor (não há unidade Terraform para eles na decomposição)
PROVIDER_SCOPE_KINDS = {"account", "region", "project", "organization", "folder", "subscription", "tenancy",
                        "billing_account", "extension_scope"}

# aspecto -> (campo de alegação, regra, tradução em uma linha). Normativo; renderizado no GRAIN.html.
TABLE = [
    ("identity", "resource_identity_schema", "R-GRAIN-T01",
     "identity present; key_fields = required menos os campos de escopo do provedor; escopo within_parent se "
     "algum campo da chave é referência (T02, T21), senão independent; optional não entra"),
    ("identity", "shared_identity_key", "R-GRAIN-T02",
     "se o próprio candidato tem ciclo de vida consolidado self, os campos são chave própria; senão são "
     "referência ao objeto compartilhado: alvo = o único par (peers) com ciclo de vida self; com mais de um, "
     "desempata o parent_resource dos fatos de API do próprio candidato contra a ponte de cada par; nenhum ou mais "
     "de um: alvo não resolvido"),
    ("identity", "id_template", "R-GRAIN-T03",
     "sem tradução: formato do id Terraform, pode incluir atributos opcionais; não é chave natural"),
    ("identity", "api_resource_bridge", "R-GRAIN-T04",
     "api_resource {status: resource, label/resource/service da ponte}; resource UNKNOWN vira UNKNOWN"),
    ("api_bridge", "(qualquer, C25 1.1.0)", "R-GRAIN-T04",
     "como api_resource_bridge: api_resource {status: resource} com value.resource/service ou, sem eles, os do "
     "registro; UNKNOWN vira UNKNOWN"),
    ("identity", "twin_type", "R-GRAIN-T09",
     "o bloco embutido herda a evidência traduzida da camada de API do tipo gêmeo (identidade, chave de "
     "importação, chave de nome, ligação com a API, ciclo de vida, dono, alcance); a referência do gêmeo ao tipo "
     "do bloco vira o pai estrutural ($parent) e sai da chave; a evidência do gêmeo substitui a do bloco "
     "(block_identity, block_config_owner, block_lifecycle são da camada Terraform); fatos com inherited_from não "
     "são lidos de novo; o rótulo de reserva é o do gêmeo"),
    ("identity", "reference_target", "R-GRAIN-T44",
     "o atributo (relativo ao bloco) é referência tipada ao resolved quando target_types é ele só; senão "
     "referência sem alvo; é o que liga chave, dono e pontas do vínculo (endpoints do C19) a unidades"),
    ("identity", "reference_phrase", "R-GRAIN-T46", "sem tradução: frase da doc; o alvo vem de reference_target"),
    ("lifecycle_controller", "terraform_timeouts", "R-GRAIN-T45",
     "o bloco timeouts do tipo é configuração do Terraform, não do recurso: fora do domínio (não vira unidade; "
     "os átomos vão para a lista fora_do_domínio); não dá ciclo de vida"),
    ("effective_scope", "(qualquer outro, com kind)", "R-GRAIN-T43",
     "fato derivado de alcance (CC-1c) com kind self/parent/container/global e via (pai estrutural, campo de "
     "referência): alcance; camada Terraform ou kind ausente: UNKNOWN"),
    ("(qualquer)", "(sem aspect, layer terraform)", "R-GRAIN-T98",
     "lifecycle_controller e effective_scope: UNKNOWN (create/delete do provider, não o objeto na API); owner "
     "de tipo de topo: UNKNOWN (onde o código escreve); owner de bloco aninhado com kind parent: aceito"),
    ("api_resource", "(ponte + ciclo de vida do pai)", "R-GRAIN-T49",
     "objeto de API ligado pela ponte (T04) cujo ciclo de vida consolidado é parent não tem vida própria na API: "
     "a ligação vira {status: aspect} com o rótulo da ponte; a alegação de aspecto sem rótulo do suspend é "
     "absorvida (não há conflito resource × aspect)"),
    ("(ciclo de vida, dono, alcance)", "(via implícito)", "R-GRAIN-T50",
     "num tipo de topo, alegação de kind parent/container sem via e alegação do mesmo kind com um único via "
     "explícito, de outra fonte, dizem o mesmo: a implícita recebe o via explícito"),
    ("(referência)", "(alvo fora da decomposição)", "R-GRAIN-T51",
     "referência tipada a tipo que não está entre os candidatos (ex. pai fora da fatia) continua referência: o "
     "alvo vira CONTÊINER EXTERNO (grão EXTERNAL): resolve identidade, ciclo de vida, dono e alcance; só os guards "
     "que exigem o grão do alvo (G1 pontas, G3 dono) falham, e aí o resultado é UNKNOWN"),
    ("owner", "parent (scope_kind resource_group | compartment)", "R-GRAIN-T52",
     "marca de NAMESPACE: a referência tipada ao contêiner (T21) é marcada namespace; qualifica o nome mas não "
     "compõe a unidade (G4-NS) e vira a relação cascade_delete_by. Também o fato explícito namespace_container "
     "{attribute}. T52b: no filho de um pai de caminho (T54), a referência ao MESMO tipo de contêiner de namespace "
     "do pai também é namespace. Sem a marca, a contenção segue composição (T21) e a regra G4-NS não se aplica"),
    ("owner", "parent (composição, tipo de API aninhado)", "R-GRAIN-T54",
     "marca de PAI DE CAMINHO: contenção que não é namespace, com referência tipada ao pai (T21), cujo tipo de API "
     "da ponte do candidato está aninhado no parent_api_type (…/pai/filho): a referência é marcada path_parent "
     "(G2-CHILD); no bloco gêmeo, o pai estrutural herda a marca. Também o fato explícito path_parent {attribute}"),
    ("(ciclo de vida, dono, alcance)", "(kind parent, sem via, com parent_resource)", "R-GRAIN-T55",
     "o via é o único campo de referência tipada (T44) cujo alvo tem ponte de API para o parent_resource da spec; "
     "nenhum ou mais de um: segue sem via (não resolve)"),
    ("identity", "(layer api, R-ID-SPEC)", "R-GRAIN-T56",
     "identidade afirmada na camada de API prevalece: resource_identity_schema (T01) e import_formats (T10), que são "
     "da camada Terraform, não são traduzidos para o mesmo candidato (nomes de campo diferentes do mesmo objeto não "
     "viram contradição); T56b: referência tipada num campo da chave de API não vale (é o identificador da "
     "própria unidade), salvo na identidade de API relativa ao pai (scope within_parent: o campo nomeia o contêiner) e "
     "no campo marcado como contêiner de namespace (T52, emenda 0.1.10); T56c: o mesmo vale para a identidade de bloco derivada do schema (block_identity)"),
    ("identity", "implicit_facet | spec_facet_member (bloco)", "R-GRAIN-T57",
     "FACETA IMPLÍCITA (emenda 0.1.8): fato da spec, no bloco, que diz que a API só aceita os blocos como membros "
     "de um único objeto-faceta do pai, configurado por uma operação única sobre o pai ({facet, facet_resource, "
     "operation, member, single_operation}); a forma embutida ganha o candidato <pai>:<facet> (id determinístico "
     "por pai e faceta), FACET do pai com implicit=true e a citação, e os blocos passam a pender dele. Sem a "
     "operação citada, ou com operação própria de criar/apagar o bloco (spec_operation), não há faceta implícita"),
    ("(atributo-lista ou seleção)", "reference_target | reference_phrase | attachment_scope", "R-GRAIN-T58",
     "LIGAÇÃO POR ATRIBUTO: atributo lista/conjunto de valores (tipo cty) com referência (T44) ou alcance por "
     "anexação vira o candidato <tipo[.bloco]>:<atributo>; na instância, um nó por elemento. Identidade = (o dono "
     "do atributo, o alvo do elemento): referência tipada resolve o alvo; só a frase da doc deixa o alvo sem tipo "
     "(UNRESOLVED); seleção por valor (rótulo) aponta um seletor externo, que não tem grão (G1 não decide). Ciclo de "
     "vida, dono e alcance da ligação só vêm de fatos com attribute = o atributo; sem eles, UNKNOWN com o que falta"),
    ("(seleção)", "attachment_scope com applies_to | selection | label_selection", "R-GRAIN-T60",
     "SELEÇÃO POR RÓTULO (emenda 0.1.9): atributo que a evidência descreve, com citação, como seleção ou alvo por "
     "rótulo/tag: cada valor é um vínculo (G1) entre o dono e um nó SELECTOR, cuja identidade é o predicado "
     "normalizado (chave do seletor, valor); o seletor não é recurso nem tem ciclo de vida. Referência tipada a tipo "
     "de recurso (T44) no mesmo atributo prevalece: lista de ids de recurso é referência, nunca seletor"),
    ("(ligação por atributo)", "(elemento de atributo-lista)", "R-GRAIN-LISTELEM",
     "DERIVADO: o elemento é um valor escalar do dono; dono da configuração = a própria associação, ciclo de vida = o "
     "do dono (some quando o dono deixa de listá-lo), alcance próprio. A alegação é level derived com ref = o átomo "
     "do schema que prova que o atributo é do dono (provedor:tipo:caminho). Fato do SERVICE-EVIDENCE sobre o "
     "atributo entra junto: igual, o campo fica KNOWN; diferente, CONTRADICTORY (nunca sobrescrita)"),
    ("(ligação por atributo)", "(referência na configuração)", "R-GRAIN-LISTREF",
     "DERIVADO (emenda 0.1.10, T61): sem fato do SERVICE-EVIDENCE sobre o atributo, atributo-lista de escalares do "
     "dono (átomo do schema citado, ref = provedor:tipo:caminho) cujos elementos são, na configuração, referências a "
     "recursos: cada elemento designa o objeto referenciado e vira ligação (T58); ciclo de vida, dono e alcance pela "
     "R-GRAIN-LISTELEM. Elemento literal ou simbólico não cria ligação (UNKNOWN sem ocorrência); fato do SE no "
     "atributo prevalece; sem o átomo citável, nada. A ponta FACET do vínculo é lida como a unidade dona da faceta"),
    ("identity", "item_identity", "R-GRAIN-T64",
     "identidade do item da coleção (emenda 0.1.11). has_id false com lista substituída inteira ou duplicata aceita: "
     "OBJETO-VALOR membro da coleção do pai; identity present within_parent anônima com chave = conteúdo ($content: "
     "valores configurados do item, símbolos como símbolos); duplicata aceita = outro membro (ordinal entre os de "
     "conteúdo igual, independente da posição); com a ponte para o campo-lista (T62), api_resource = carga útil "
     "(item). has_id true: identidade própria (id_field ou id); requires_parent com parent_attribute: a referência "
     "ao pai entra na chave e marca o pai de caminho (G2-CHILD)"),
    ("(qualquer)", "(nível observed)", "R-GRAIN-OBS",
     "OBSERVED (C25 1.4.0) entra com o nível na citação. Disputa: observada repetível (2+ repetições) e com controle "
     "prevalece sobre doc publicada, derivação e interpretação do mesmo campo, se as observadas qualificadas "
     "concordam; a disputa fica registrada (disputes e a citação vencida continua na evidência); sem repetição ou "
     "controle, ou observadas divergentes: CONTRADICTORY"),
    ("identity", "attachment_attribute", "R-GRAIN-T63",
     "campo da spec que liga o dono a objetos do tipo binds_to, casado ao atributo pela leitura do modelo: ligação "
     "por atributo (T58) com alvo tipado; o nível INTERPRETED do fato vai para a citação (com model_id) e não é "
     "promovido; alvo tipado (T44) igual mantém, diferente deixa o alvo sem tipo com o motivo"),
    ("api_resource", "api_resource_bridge com item_model e field_type list[...] (bloco)", "R-GRAIN-T62",
     "ponte para campo-lista de itens do pai: cada bloco é um item da coleção, não o aspecto do pai (T49 não se "
     "aplica); sem identidade do item (nome ou conteúdo) na evidência, FACET e COMPONENT anônimo não se distinguem: "
     "UNKNOWN em api_resource com o motivo"),
    ("api_resource", "(pontes equivalentes)", "R-GRAIN-T53",
     "duas pontes que nomeiam o mesmo recurso só com grafia diferente (caixa, sublinhado, hífen), ainda que o "
     "nome do serviço difira entre a doc e o SDK da spec, são uma alegação só; recursos de fato diferentes "
     "continuam CONTRADICTORY (disputa); par que o SERVICE-EVIDENCE publica como disputa (spec_disputes.json) "
     "nunca é unificado"),
    ("api_bridge", "spec_bridge_candidates", "R-GRAIN-T48",
     "sem tradução: a spec casa com mais de um tipo e o desempate não dá este tipo; UNKNOWN com o motivo"),
    ("identity", "api_reference", "R-GRAIN-T05", "sem tradução: página de referência da API, informativa"),
    ("identity", "cardinality", "R-GRAIN-T06",
     "sem tradução: singular por escopo do provedor; o escopo não é unidade da decomposição"),
    ("identity", "block_identity", "R-GRAIN-T07",
     "schema_identity present com key_fields: identity present within_parent e element_name_key = key_fields; "
     "absent sem element_name_candidates: identity absent; absent com candidatos: UNKNOWN (candidatos não "
     "confirmados)"),
    ("identity", "block_schema", "R-GRAIN-T08", "sem tradução: estrutura do bloco (facet_word não é lido)"),
    ("import_key", "import_formats", "R-GRAIN-T10",
     "supported false: import_key absent; identity.required presente: import_key present com required menos os "
     "campos de escopo do provedor; só placeholders, values ou id_format: UNKNOWN (sem atributos nomeados)"),
    ("owner", "identity_scope", "R-GRAIN-T20",
     "sem tradução para owner: diz quem é dono da IDENTIDADE (conta, região), não da configuração; marca "
     "account_id/region como campos de escopo do provedor para T01"),
    ("owner", "parent", "R-GRAIN-T21",
     "sem tradução para owner (contenção da identidade); se o scope_kind é unidade (não escopo do provedor): "
     "a referência tipada (T44) cujo alvo é um dos parent_terraform_types entra na chave (identidade relativa ao "
     "contêiner); sem ela, a chave ganha uma referência não resolvida ($container) e a identidade fica UNRESOLVED"),
    ("owner", "parent_attribute", "R-GRAIN-T22",
     "sem tradução para owner (atributo de contenção, não dono da configuração)"),
    ("owner", "block_config_owner", "R-GRAIN-T23",
     "owner {kind: parent, via: $parent} quando via é o pai estrutural do bloco; senão UNKNOWN"),
    ("lifecycle_controller", "destroy_effect", "R-GRAIN-T30",
     "suspend: lifecycle_controller {kind: parent} e api_resource {status: aspect} (indício de faceta do pai); "
     "not_deleted e state_only: UNKNOWN (o destroy não apaga; não diz quem apaga)"),
    ("lifecycle_controller", "deletion_policy", "R-GRAIN-T31",
     "values com DELETE: lifecycle_controller {kind: self}; values vazio: UNKNOWN (política sem valores "
     "documentados)"),
    ("lifecycle_controller", "block_lifecycle", "R-GRAIN-T32",
     "lifecycle_controller {kind: parent, via: $parent} quando via é o pai estrutural do bloco; senão UNKNOWN"),
    ("effective_scope", "type_scope", "R-GRAIN-T40",
     "scope de escopo do provedor (account, project, organization, ...): {kind: global}; outro scope: {kind: "
     "parent, via: o campo de referência da chave} se a chave tem uma referência, senão {kind: self}"),
    ("effective_scope", "attachment_scope", "R-GRAIN-T47",
     "effective_scope {kind: self}: a configuração da unidade vale onde ela está anexada, e a anexação é relação "
     "(o atributo vira referência; vínculos de outros tipos), não alcance de outra unidade"),
    ("effective_scope", "attribute_scope", "R-GRAIN-T41",
     "sem tradução: escopo de UM atributo, não da unidade"),
    ("effective_scope", "effective_public_access", "R-GRAIN-T42",
     "sem tradução: avaliação de acesso efetivo (oráculo do piloto), não grão"),
    ("effective_scope", "effective_public_access_prevention", "R-GRAIN-T42",
     "sem tradução: avaliação de acesso efetivo (oráculo do piloto), não grão"),
    ("(qualquer)", "(sem aspect)", "R-GRAIN-T99",
     "fato afirmado sem value.aspect: alegação direta na convenção anterior (identity/import_key como objeto; "
     "lifecycle_controller/owner/effective_scope como string do kind ou {kind, via}); é a porta para o "
     "SERVICE-EVIDENCE emitir fatos derivados de grão já traduzidos"),
    ("(qualquer)", "(status unknown)", "R-GRAIN-UNK", "alegação UNKNOWN com o unknown_reason; contradictory vira "
     "CONTRADICTORY"),
    ("(qualquer)", "(aspecto fora da tabela)", "R-GRAIN-UNK", "alegação UNKNOWN com o motivo 'sem tradução'"),
]
RULE_OF = {(f, a): r for f, a, r, _ in TABLE}
# aspectos cujo nome na tabela é descritivo: chaves de busca explícitas
for _f in GRAIN_FACTS:
    RULE_OF[(_f, "implicit_facet")] = RULE_OF[(_f, "spec_facet_member")] = "R-GRAIN-T57"
RULE_OF[("lifecycle_controller", "spec_operation")] = "R-GRAIN-T57"
for _f in GRAIN_FACTS:
    RULE_OF[(_f, "selection")] = RULE_OF[(_f, "label_selection")] = "R-GRAIN-T60"


def is_aspect_record(r: dict) -> bool:
    v = r.get("value")
    if r.get("fact_kind") not in GRAIN_FACTS:
        return False
    return r.get("fact_kind") == "api_bridge" or bool(r.get("block_path")) or (
        isinstance(v, dict) and ("aspect" in v or "layer" in v))


def _src(r: dict, rule: str, why: str = "") -> dict:
    v = r.get("value") if isinstance(r.get("value"), dict) else {}
    note = f"{rule}: {r['fact_kind']}/{v.get('aspect', 'sem aspecto')}"
    if why:
        note += f" ({why})"
    if r.get("level") == "observed":
        # OBSERVED (C25 1.4.0): experimento na API real; qualificado = 2+ repetições e controle (R-GRAIN-OBS)
        rep, ctl = r.get("repetitions") or 0, r.get("control")
        qual = isinstance(rep, int) and rep >= 2 and bool(ctl)
        dsp = r.get("disputes") or []
        note += (f" [OBSERVED run {r.get('run_id')}, {rep} repetições, controle {'sim' if ctl else 'não'}"
                 + (f", disputa com {', '.join(map(str, dsp))}" if dsp else "") + "]")
        return {"level": "observed", "ref": r["evidence_id"], "note": note, "qualified": qual}
    return {"level": "derived", "ref": r["evidence_id"], "note": note}


def _rel(attr: str, block_path: str | None) -> str:
    """Caminho do atributo relativo ao candidato (sem o prefixo do bloco)."""
    if block_path and attr.startswith(block_path + "."):
        return attr[len(block_path) + 1:]
    return attr


def load_disputes() -> set:
    """(provedor, tipo, campo) das disputas spec × doc publicadas pelo SERVICE-EVIDENCE: nunca unificadas (T53)."""
    import json
    from .common import repo
    p = repo() / "results" / "SERVICE-EVIDENCE" / "spec_disputes.json"
    if not p.is_file():
        return set()
    out = set()
    for d in json.loads(p.read_text(encoding="utf-8")).get("disputes", []):
        fld = "api_resource" if d.get("fact") == "api_bridge" else d.get("fact")
        out.add((d.get("provider"), d.get("terraform_resource_type"), fld))
    return out


def translate(records: list[dict], candidates: set[str] | None = None, disputes: set | None = None) -> tuple[dict, dict]:
    """records: C25 de UM provedor (todos os tipos, para os pares de T02 e os gêmeos de T09). candidates: ids de
    candidato da decomposição (alvos de referência só valem se existem). Devolve ({cid: evidência}, {cid: motivos})."""
    by_cid: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        if r.get("fact_kind") not in GRAIN_FACTS or not r.get("terraform_resource_type"):
            continue
        v = r.get("value")
        # C25 1.1.0: block_path no registro; antes, em value.block_path (as duas formas são lidas)
        bp = r.get("block_path") or (v.get("block_path") if isinstance(v, dict) else None)
        by_cid[r["terraform_resource_type"] + ("." + bp if bp else "")].append(r)
    out: dict[str, dict] = {}
    reasons: dict[str, list] = defaultdict(list)
    provider = next((r["provider"] for r in records), "")
    scope_fields = set(PROVIDER_SCOPE_FIELDS.get(provider, set()))

    def put(cid, fld, claim):
        out.setdefault(cid, {}).setdefault(fld, []).append(claim)

    def aspect_of(r):
        v = r.get("value")
        return v.get("aspect") if isinstance(v, dict) else None

    def unknown(cid, fld, r, why):
        fld = "api_resource" if fld == "api_bridge" else fld
        reasons[cid].append(f"{fld}: {why}")
        put(cid, fld, {"status": "unknown", "source": _src(r, RULE_OF.get((r["fact_kind"], aspect_of(r)),
                                                                          "R-GRAIN-UNK"), why)})

    pending_ids, shared, containers, scopes, twins, timeouts = {}, {}, {}, {}, {}, {}
    ns_fields: dict[str, set] = defaultdict(set)     # cid -> campos de referência ao contêiner de namespace
    api_identity: set = set()                         # cids com identidade afirmada na camada de API (T56)
    own_ops: set = set()                              # blocos com operação própria de criar/apagar (T57, negativo)
    links: dict[str, dict] = defaultdict(dict)       # cid -> atributo -> ligação (T58)
    path_fields: dict[str, set] = defaultdict(set)   # cid -> campos de referência ao pai de caminho (T54)
    list_items: dict[str, dict] = {}                  # cid -> ponte para campo-lista de itens (T62)
    value_objects: dict[str, dict] = {}               # cid -> objeto-valor observado (T64)
    typed: dict[str, dict] = defaultdict(dict)       # cid -> {campo: tipo alvo ou None} (T44 reference_target)
    for cid, rs in sorted(by_cid.items()):
        rt = cid.split(".")[0]
        nested = "." in cid
        bp = cid.split(".", 1)[1] if nested else None
        parent_cid = cid.rsplit(".", 1)[0] if nested else None
        loc_scope = set(scope_fields)
        for r in rs:
            if aspect_of(r) == "identity_scope":
                v = r["value"]
                if v.get("account"):
                    loc_scope.add("account_id")
                if v.get("region"):
                    loc_scope.add("region")
        for r in rs:
            fld, v = r["fact_kind"], r.get("value")
            a = aspect_of(r)
            if r.get("status") == "unknown":
                st = "contradictory" if r.get("unknown_reason") == "contradictory" else "unknown"
                reasons[cid].append(f"{fld}: {r.get('unknown_reason')}")
                put(cid, fld, {"status": st, "source": _src(r, "R-GRAIN-UNK", r.get("unknown_reason") or "")})
                continue
            if isinstance(v, dict) and v.get("inherited_from"):
                # fato herdado do gêmeo (R-TWIN): coberto por twin_type (T09), que copia a evidência traduzida
                reasons[cid].append(f"{fld}: herdado de {v['inherited_from']} (coberto por twin_type)")
                continue
            if fld == "api_bridge" and a in (None, "api_resource_bridge"):
                res_ = (v or {}).get("resource") if isinstance(v, dict) else None
                res_ = res_ or (r.get("api_resource") or {}).get("resource")
                if res_ in (None, "", "UNKNOWN"):
                    unknown(cid, "api_resource", r, "ponte sem recurso de API")
                elif nested and isinstance(v, dict) and v.get("item_model") and \
                        str(v.get("field_type") or "").startswith("list["):
                    # T62: ponte para campo-lista de itens do pai: cada bloco é UM item da coleção, não o aspecto
                    # (T49 não se aplica); decidido depois do laço: com identidade do item (T64) é carga útil (item);
                    # sem ela, FACET e COMPONENT anônimo ficam indistintos: UNKNOWN com o motivo
                    list_items[cid] = r
                else:
                    svc = (v.get("service") if isinstance(v, dict) else None) or (r.get("api_resource") or {}).get(
                        "service") or "UNKNOWN"
                    put(cid, "api_resource", {"status": "resource", "label": res_, "service": svc, "resource": res_,
                                              "source": _src(r, "R-GRAIN-T04")})
                continue
            if a is None and isinstance(v, dict) and v.get("attribute") and fld in (
                    "lifecycle_controller", "owner", "effective_scope", "identity"):
                # T58: fato direto sobre UM atributo (ligação por atributo-lista ou seleção): vai para o candidato
                # da ligação <tipo[.bloco]>:<atributo>
                cid_l = f"{cid}:{_rel(v['attribute'], bp)}"
                if v.get("layer") == "terraform":
                    unknown(cid_l, fld, r, "camada Terraform")
                    continue
                cl = {k: x for k, x in v.items() if k not in ("attribute", "layer", "rule", "note", "block_path")}
                cl["source"] = _src(r, "R-GRAIN-T58", "fato da ligação")
                put(cid_l, fld, cl)
                continue
            if a is None:
                # fato sem aspecto: alegação direta na convenção anterior (T99), salvo camada Terraform (T98)
                if isinstance(v, dict) and v.get("layer") == "terraform":
                    if fld == "lifecycle_controller":
                        unknown(cid, fld, r, "camada Terraform: create/delete do provider, não o objeto na API")
                        continue
                    if fld == "owner" and not nested:
                        unknown(cid, fld, r, "camada Terraform: onde o código escreve, não o dono da configuração")
                        continue
                    if fld == "effective_scope":
                        unknown(cid, fld, r, "camada Terraform: não é o alcance na API")
                        continue
                claim = {"kind": v} if isinstance(v, str) else {k: x for k, x in (v or {}).items()
                                                                 if k not in ("block_path", "references",
                                                                              "field_map", "parent_role", "layer",
                                                                              "rule", "note")}
                if isinstance(v, dict):
                    ent = out.setdefault(cid, {})
                    ent.setdefault("references", {}).update(v.get("references") or {})
                    ent.setdefault("field_map", {}).update(v.get("field_map") or {})
                    if v.get("parent_role"):
                        ent["parent_role"] = v["parent_role"]
                    if claim.get("via") == parent_cid and nested:
                        claim["via"] = "$parent"
                    if claim.get("via") == []:
                        claim.pop("via")
                claim["source"] = _src(r, "R-GRAIN-T99", "alegação direta")
                if fld == "identity" and isinstance(v, dict) and v.get("layer") == "api":
                    api_identity.add(cid)
                put(cid, fld, claim)
                continue
            rule = RULE_OF.get((fld, a))
            if rule is None and fld == "effective_scope" and "kind" in v:
                rule = "R-GRAIN-T43"
            if rule is None:
                unknown(cid, fld, r, f"aspecto {a} sem tradução na tabela")
            elif a == "resource_identity_schema":
                pending_ids[cid] = (r, [f for f in v.get("required", []) if f not in loc_scope])
            elif a == "shared_identity_key":
                shared[cid] = (r, [f for f in v.get("fields", []) if f not in loc_scope], list(v.get("peers", [])))
            elif a in ("implicit_facet", "spec_facet_member"):
                # T57: a API só aceita os blocos como membros de UM objeto-faceta do pai, configurado por UMA
                # operação sobre o pai (fato da spec com a operação citada)
                if nested and v.get("operation") and v.get("facet") and v.get("single_operation", True) is True:
                    out.setdefault(cid, {})["implicit_facet"] = {
                        "facet": v["facet"], "label": str(v.get("facet_resource") or v["facet"]).split(":")[-1],
                        "operation": v["operation"], "member": v.get("member"),
                        "parent_resource": v.get("parent_resource"), "source": _src(r, rule, "faceta implícita")}
                else:
                    reasons[cid].append("identity: fato de faceta implícita sem operação única citada (T57)")
            elif a == "spec_operation" and nested and v.get("role") in ("create", "delete"):
                own_ops.add(cid)
            elif a in ("selection", "label_selection"):
                # T60: fato explícito de seleção por rótulo/tag (predicado), com citação
                if v.get("attribute"):
                    attr = _rel(v["attribute"], bp)
                    if not links[cid].get(attr, {}).get("target"):
                        links[cid][attr] = {"kind": "selection", "target": None, "selector_kind":
                                            v.get("selector_kind") or attr, "source": _src(r, rule)}
            elif a == "path_parent":
                if v.get("attribute"):
                    path_fields[cid].add(_rel(v["attribute"], bp))
            elif a == "namespace_container":
                # fato explícito: o atributo referencia um contêiner de namespace (T52)
                if v.get("attribute"):
                    ns_fields[cid].add(_rel(v["attribute"], bp))
            elif a == "twin_type":
                # o gêmeo pode ser um bloco do tipo gêmeo (twin_block_path): o par desce ao bloco correspondente
                tw = v.get("twin")
                twins[cid] = (r, f"{tw}.{v['twin_block_path']}" if tw and v.get("twin_block_path") else tw)
            elif a == "reference_target":
                attr = _rel(v.get("attribute", ""), bp)
                tt = v.get("target_types") or []
                res_t = v.get("resolved")
                if attr and res_t and (not tt or tt == [res_t]):
                    typed[cid][attr] = res_t
                else:
                    typed[cid][attr] = None
                    reasons[cid].append(f"identity: referência {attr} com alvo ambíguo {tt}")
                prev = links[cid].get(attr, {})
                if prev.get("target") and typed[cid][attr] and prev["target"] != typed[cid][attr]:
                    # T63 x T44 divergentes: alvo sem tipo, independente da ordem dos registros
                    reasons[cid].append(f"identity: anexação {attr} diverge do alvo tipado")
                    links[cid][attr] = dict(prev, target=None, why="alvos divergentes")
                elif not (prev.get("target") and prev["target"] == typed[cid][attr]):
                    links[cid][attr] = {"kind": "reference", "target": typed[cid][attr], "source": _src(r, rule)}
            elif a == "item_identity":
                # T64: identidade do item (fato do experimento ou da doc). Sem id, lista substituída inteira e/ou
                # duplicata aceita: objeto-valor membro da coleção do pai, identidade = conteúdo (anônima), cada
                # duplicata é um membro. Com id: identidade própria; requires_parent marca o pai de caminho.
                src = _src(r, "R-GRAIN-T64")
                if v.get("has_id") is False and nested and (v.get("replaced_whole") or v.get("duplicates_accepted")):
                    put(cid, "identity", {"status": "present", "scope": "within_parent", "key_fields": ["$content"],
                                          "anonymous": True, "source": src})
                    put(cid, "element_name_key", {"status": "absent", "source": src})
                    value_objects[cid] = {"duplicates": bool(v.get("duplicates_accepted")),
                                          "replaced_whole": bool(v.get("replaced_whole")), "source": src}
                elif v.get("has_id") is True:
                    kf = [v.get("id_field") or "id"]
                    pa = _rel(v.get("parent_attribute") or "", bp) if v.get("requires_parent") else ""
                    if pa:
                        kf.append(pa)
                        path_fields[cid].add(pa)
                        if v.get("parent_type") and not typed[cid].get(pa):
                            typed[cid][pa] = v["parent_type"]
                    put(cid, "identity", {"status": "present", "scope": "within_parent" if (pa or nested)
                                          else "independent", "key_fields": kf, "source": src})
                else:
                    unknown(cid, "identity", r, "identidade do item sem forma traduzível (T64)")
            elif a == "attachment_attribute":
                # T63: campo da spec que liga o dono a objetos do tipo binds_to, casado ao atributo Terraform por
                # leitura do modelo: ligação por atributo com alvo tipado, nível INTERPRETED (nunca promovido)
                attr = _rel(v.get("attribute", ""), bp)
                if not attr or not v.get("binds_to"):
                    unknown(cid, fld, r, "anexação sem atributo ou sem alvo")
                else:
                    src = _src(r, "R-GRAIN-T63", f"{v.get('spec_operation')}/{v.get('spec_field')}")
                    if r.get("level") == "interpreted":
                        src = dict(src, level="interpreted", model_id=r.get("model_id") or "UNKNOWN")
                    prev = links[cid].get(attr, {}).get("target")
                    if prev and prev != v["binds_to"]:
                        reasons[cid].append(f"identity: anexação {attr} diverge do alvo tipado ({prev} x "
                                            f"{v['binds_to']})")
                        links[cid][attr] = {"kind": "reference", "target": None, "why": "alvos divergentes",
                                            "source": src}
                    elif not prev:
                        links[cid][attr] = {"kind": "reference", "target": v["binds_to"], "source": src}
            elif a == "reference_phrase":
                reasons[cid].append("identity: reference_phrase é frase da doc; o alvo vem de reference_target")
                if v.get("attribute"):
                    links[cid].setdefault(_rel(v["attribute"], bp), {
                        "kind": "reference", "target": None, "why": "só reference_phrase (sem alvo tipado)",
                        "source": _src(r, "R-GRAIN-T46")})
            elif a == "terraform_timeouts":
                timeouts[rt] = r
                reasons[cid].append("lifecycle_controller: terraform_timeouts é configuração do Terraform (fora do "
                                    "domínio)")
            elif a == "api_resource_bridge":
                if v.get("resource") in (None, "", "UNKNOWN"):
                    unknown(cid, "api_resource", r, "ponte sem recurso de API")

                else:
                    put(cid, "api_resource", {"status": "resource", "label": v["resource"], "service": v.get("service")
                                              or "UNKNOWN", "resource": v["resource"], "source": _src(r, rule)})
            elif a == "block_identity":
                si, kf, cands = v.get("schema_identity"), list(v.get("key_fields") or []), v.get("element_name_candidates")
                if si == "present" and kf:
                    put(cid, "identity", {"status": "present", "scope": "within_parent", "key_fields": kf,
                                          "source": _src(r, rule)})
                    put(cid, "element_name_key", {"status": "present", "fields": kf, "source": _src(r, rule)})
                elif si == "absent" and not cands:
                    put(cid, "identity", {"status": "absent", "source": _src(r, rule)})
                else:
                    unknown(cid, "identity", r, "candidatos a nome não confirmados")
            elif a == "import_formats":
                if v.get("supported") is False:
                    put(cid, "import_key", {"status": "absent", "source": _src(r, rule)})
                elif isinstance(v.get("identity"), dict) and v["identity"].get("required") is not None:
                    pending_ids.setdefault(cid + "#import", (r, [f for f in v["identity"]["required"]
                                                                 if f not in loc_scope]))
                else:
                    unknown(cid, "import_key", r, "formato de importação sem atributos nomeados")
            elif a == "parent":
                sk, types = v.get("scope_kind"), v.get("parent_terraform_types") or []
                if sk not in PROVIDER_SCOPE_KINDS:
                    containers[cid] = (r, types)
                reasons[cid].append("owner: owner/parent é contenção da identidade, não dono da configuração")
                put(cid, "owner", {"status": "unknown", "source": _src(r, rule, "contenção da identidade")})
            elif a in ("block_config_owner", "block_lifecycle"):
                tgt = "owner" if a == "block_config_owner" else "lifecycle_controller"
                if nested and v.get("via") == parent_cid and v.get("kind") == "parent":
                    put(cid, tgt, {"kind": "parent", "via": "$parent", "source": _src(r, rule)})
                else:
                    unknown(cid, tgt, r, "via não é o pai estrutural")
            elif a == "destroy_effect":
                eff = v.get("effect")
                if eff == "suspend":
                    put(cid, "lifecycle_controller", {"kind": "parent", "source": _src(r, rule, "suspend")})
                    put(cid, "api_resource", {"status": "aspect", "label": None, "source": _src(r, rule, "suspend")})
                else:
                    unknown(cid, "lifecycle_controller", r, f"destroy_effect {eff}: não diz quem apaga")
            elif a == "deletion_policy":
                vals = [str(x).upper() for x in v.get("values") or []]
                if "DELETE" in vals:
                    put(cid, "lifecycle_controller", {"kind": "self", "source": _src(r, rule)})
                else:
                    unknown(cid, "lifecycle_controller", r, "política de remoção sem valores documentados")
            elif a == "type_scope":
                scopes[cid] = (r, v.get("scope"))
            elif a == "attachment_scope":
                # T47: a configuração vale onde a unidade está anexada; a anexação é relação (atributo de
                # referência ou vínculo de outro tipo), não alcance de outra unidade: o alcance da unidade é ela mesma
                put(cid, "effective_scope", {"kind": "self", "source": _src(r, rule, "aplica-se onde está anexado")})
                if v.get("attribute"):
                    attr = _rel(v["attribute"], bp)
                    typed[cid].setdefault(attr, None)
                    reasons[cid].append(f"effective_scope: anexação por {attr} (alvo: {v.get('applies_to')})")
                    if not links[cid].get(attr, {}).get("target"):
                        links[cid][attr] = {"kind": "selection" if v.get("applies_to") and not v.get("attach_to")
                                            else "reference", "target": None, "applies_to": v.get("applies_to")
                                            or v.get("attach_to"), "source": _src(r, rule)}
            elif rule == "R-GRAIN-T43":
                if v.get("layer") == "terraform" or v.get("kind") not in ("self", "parent", "container", "global"):
                    unknown(cid, fld, r, "alcance derivado sem kind de API")
                else:
                    claim = {"kind": v["kind"], "source": _src(r, rule)}
                    via = v.get("via")
                    if via:
                        claim["via"] = "$parent" if (nested and via == parent_cid) else via
                    put(cid, "effective_scope", claim)
            else:
                unknown(cid, fld, r, f"aspecto {a}: sem tradução ({rule})")

    from .evidence import consolidate

    def lc_self(cid):
        f = consolidate("lifecycle_controller", out.get(cid, {}).get("lifecycle_controller", []))
        return f.known and f.value["kind"] == "self"

    def ok_target(tgt):
        # alvo fora da decomposição continua alvo: contêiner externo referenciado (T51), decidido na camada de schema
        return tgt is not None

    key_refs: dict[str, dict] = defaultdict(dict)   # referências que ENTRAM na chave (T02, T21)
    for cid, (r, fields, peers) in sorted(shared.items()):
        if lc_self(cid):
            continue                                          # tem ciclo de vida próprio: a chave é própria
        roots = [p for p in sorted(set(peers)) if lc_self(p)]
        # desempate pela spec (T02b): o fato de API do próprio candidato nomeia o recurso pai (parent_resource);
        # vale o par cuja ponte (T04) liga a esse recurso
        parents = {c.get("parent_resource") for fld_ in ("lifecycle_controller", "owner")
                   for c in out.get(cid, {}).get(fld_, []) if c.get("parent_resource")}
        if len(roots) > 1 and len(parents) == 1:
            pr = next(iter(parents))
            roots = [p for p in roots if any(c.get("resource") == pr and c.get("status") == "resource"
                                             for c in out.get(p, {}).get("api_resource", []))]
        tgt = roots[0] if len(roots) == 1 else None
        for f in fields:
            if f in typed.get(cid, {}):
                continue                                      # alvo tipado explícito (T44) prevalece
            key_refs[cid][f] = tgt if ok_target(tgt) else None
        if tgt is None:
            reasons[cid].append(f"identity: chave compartilhada {fields} sem raiz única com ciclo de vida self "
                                f"entre os pares ({len(roots)} raiz(es))")
    for cid, (r, types) in sorted(containers.items()):
        via_typed = [f for f, tt in typed.get(cid, {}).items() if tt and tt in types]
        if len(via_typed) == 1:
            # o contêiner da identidade é o alvo de uma referência tipada: a identidade é relativa a ele (T21)
            f = via_typed[0]
            key_refs[cid][f] = typed[cid][f] if ok_target(typed[cid][f]) else None
            if r["value"].get("scope_kind") in NAMESPACE_KINDS:
                ns_fields[cid].add(f)                     # T52: contêiner de namespace, não composição
            else:
                # T54: pai de composição como segmento de caminho acima da unidade: o tipo de API da ponte está
                # aninhado no tipo de API do pai (…/pai/filho)
                pat = r["value"].get("parent_api_type") or ""
                for c in out.get(cid, {}).get("api_resource", []):
                    full = f"{c.get('service')}/{c.get('resource')}"
                    if pat and c.get("status") == "resource" and full.lower().startswith(pat.lower() + "/"):
                        path_fields[cid].add(f)
            continue
        key_refs[cid]["$container"] = None
        reasons[cid].append(f"identity: contido em {r['value'].get('scope_kind')} ({types or 'sem tipo Terraform'}) "
                            "sem atributo de referência ao contêiner na identidade")
    # referências tipadas e da chave no mapa de campos
    for cid in set(typed) | set(key_refs):
        ent = out.setdefault(cid, {})
        fm = ent.setdefault("field_map", {})
        for f, tgt in list(typed.get(cid, {}).items()) + list(key_refs.get(cid, {}).items()):
            fm[f] = {"path": f, "ref": True}
            if ok_target(tgt):
                ent.setdefault("references", {})[f] = tgt
    # T52b: o namespace do pai de caminho também qualifica o filho: a referência da chave do filho ao MESMO tipo de
    # contêiner de namespace que qualifica o pai é namespace (herança ao longo do caminho)
    for cid, pfs in list(path_fields.items()):
        for pf in pfs:
            ptype = typed.get(cid, {}).get(pf)
            if not ptype:
                continue
            ns_types = {typed.get(ptype, {}).get(g) for g in ns_fields.get(ptype, set())}
            for f, tt in typed.get(cid, {}).items():
                if f != pf and tt and tt in ns_types:
                    ns_fields[cid].add(f)
                    reasons[cid].append(f"identity: {f} herda do pai de caminho {ptype} a marca de namespace (T52b)")
    for cid, fs in path_fields.items():
        fm = out.setdefault(cid, {}).setdefault("field_map", {})
        for f in fs:
            fm.setdefault(f, {"path": f, "ref": True})["path_parent"] = True
        reasons[cid].append(f"identity: {sorted(fs)} referencia o pai de caminho da spec (G2-CHILD)")
    for cid, fs in ns_fields.items():
        fm = out.setdefault(cid, {}).setdefault("field_map", {})
        for f in fs:
            fm.setdefault(f, {"path": f, "ref": True})["namespace"] = True
        reasons[cid].append(f"identity: {sorted(fs)} referencia contêiner de namespace (cascade_delete_by)")
    # identidade e chave de importação
    for key, (r, fields) in sorted(pending_ids.items()):
        cid = key.split("#")[0]
        if cid in api_identity:
            # T56: a identidade da camada de API prevalece sobre a identidade de recurso e o formato de importação
            # do Terraform (campos de nome diferentes do mesmo objeto não viram contradição)
            reasons[cid].append(f"identity: {'import_key' if key.endswith('#import') else 'resource_identity_schema'} "
                                "da camada Terraform substituída pela identidade de API (T56)")
            continue
        kr = key_refs.get(cid, {})
        kf = list(fields) + [f for f in kr if f not in fields]
        is_ref = {f for f, m in out.get(cid, {}).get("field_map", {}).items() if m.get("ref")}
        if key.endswith("#import"):
            put(cid, "import_key", {"status": "present", "fields": kf, "source": _src(r, RULE_OF[("import_key",
                                                                                                   "import_formats")])})
        else:
            rel = any(f in is_ref for f in kf)
            put(cid, "identity", {"status": "present", "scope": "within_parent" if rel else "independent",
                                  "key_fields": kf, "source": _src(r, RULE_OF[("identity", "resource_identity_schema")])})
    for cid, (r, scope) in sorted(scopes.items()):
        rule = RULE_OF[("effective_scope", "type_scope")]
        if scope in PROVIDER_SCOPE_KINDS:
            put(cid, "effective_scope", {"kind": "global", "source": _src(r, rule)})
        else:
            rf = [f for f in key_refs.get(cid, {}) if not f.startswith("$")]
            put(cid, "effective_scope", {"kind": "parent", "via": rf[0], "source": _src(r, rule)} if len(rf) == 1
                else {"kind": "self", "source": _src(r, rule)})
    # T56c: identidade de API prevalece também sobre a identidade de bloco derivada do schema (block_identity, T07)
    for cid in api_identity:
        ent = out.get(cid, {})
        for fld_ in ("identity", "element_name_key"):
            cl = ent.get(fld_, [])
            keep = [c for c in cl if "R-GRAIN-T07" not in str((c.get("source") or {}).get("note", ""))]
            if len(keep) != len(cl):
                ent[fld_] = keep
                reasons[cid].append(f"{fld_}: block_identity (schema) substituída pela identidade de API (T56c)")
    # T56b: campo da chave de identidade de API é o identificador da própria unidade: referência tipada nele (alvo
    # de outro tipo pela frase da doc) não vale para a chave
    for cid in api_identity:
        ent = out.get(cid, {})
        # identidade de API relativa ao pai (scope within_parent): campos com referência tipada nomeiam o contêiner
        # (são o pai na chave), não o identificador da unidade; e campo marcado como contêiner de namespace (T52)
        # continua referência ao contêiner. T56b só vale para os demais campos da identidade independente
        keyf = {f for c in ent.get("identity", []) if c.get("scope") != "within_parent"
                for f in (c.get("key_fields") or [])} - set(ns_fields.get(cid, set()))
        fm = ent.get("field_map", {})
        for f in sorted(keyf):
            if fm.get(f, {}).get("ref"):
                fm[f] = {"path": fm[f].get("path", f), "norm": "str"}
                ent.get("references", {}).pop(f, None)
                typed.get(cid, {}).pop(f, None)
                reasons[cid].append(f"identity: {f} é o identificador de API da unidade; a referência tipada nele "
                                    "não vale para a chave (T56b)")
    # T55: alegação de kind parent/container sem via, com parent_resource da spec: o via é o único campo de
    # referência tipada cujo alvo tem ponte (T04) para esse recurso
    for cid, ent in out.items():
        for fld_ in ("lifecycle_controller", "owner", "effective_scope"):
            for c in ent.get(fld_, []):
                pr = c.get("parent_resource")
                if not pr or c.get("kind") not in ("parent", "container") or c.get("via") not in (None, []):
                    continue
                hits = [f for f, tt in typed.get(cid, {}).items() if tt and any(
                    str(b.get("resource", "")).lower() == str(pr).lower() and b.get("status") == "resource"
                    for b in out.get(tt, {}).get("api_resource", []))]
                if len(hits) == 1:
                    c["via"] = hits[0]
                    reasons[cid].append(f"{fld_}: pai {pr} resolvido pela referência {hits[0]} (T55)")
    # T53: pontes que nomeiam o mesmo recurso com grafia diferente (caixa, sublinhado) são a mesma alegação; fica a
    # primeira (as divergências de verdade continuam CONTRADICTORY)
    def _k(c):
        # o nome do serviço varia entre a doc e o SDK da spec (ex. iaas × core); o recurso é o que identifica
        return "".join(ch for ch in str(c.get("resource") or "").lower() if ch.isalnum())
    for cid, ent in out.items():
        br = [c for c in ent.get("api_resource", []) if c.get("status") == "resource" and c.get("resource")]
        if (provider, cid, "api_resource") in (disputes or set()):
            if len(br) > 1:
                reasons[cid].append("api_resource: disputa spec × doc publicada pelo SERVICE-EVIDENCE: CONTRADICTORY")
            continue
        if len(br) > 1 and len({_k(c) for c in br}) == 1 and len({(c.get("service"), c.get("resource")) for c in br}) > 1:
            spec = [c for c in br if "R-BRIDGE-SPEC" in str((c.get("source") or {}).get("note", "")) or
                    "SPEC" in str((c.get("source") or {}).get("ref", ""))]
            first = br[0]
            ent["api_resource"] = [c for c in ent["api_resource"] if c not in br[1:]]
            reasons[cid].append(f"api_resource: pontes equivalentes (grafia) unificadas em {first.get('service')}/"
                                f"{first.get('resource')} (T53)")
    # T50: via implícito (ausente) e via explícito do mesmo kind, de fontes diferentes, dizem a mesma coisa quando
    # só há um via explícito: o implícito recebe o explícito (sem isso, suspend sem via contradiria a spec)
    for cid, ent in out.items():
        for fld_ in ("lifecycle_controller", "owner", "effective_scope"):
            cl = ent.get(fld_, [])
            for kind in ("parent", "container"):
                explicit = {tuple(c["via"]) if isinstance(c.get("via"), list) else (c["via"],)
                            for c in cl if c.get("kind") == kind and c.get("via") not in (None, [], "$parent")}
                if len(explicit) != 1:
                    continue
                v = list(next(iter(explicit)))
                for c in cl:
                    if c.get("kind") == kind and c.get("via") in (None, []) and "." not in cid:
                        c["via"] = v if len(v) > 1 else v[0]
    # T49: objeto de API ligado pela ponte cujo ciclo de vida consolidado é o pai não tem vida própria na API:
    # é aspecto do pai. A ponte dá rótulo/serviço/recurso e o status vira aspect (uma alegação só, sem conflito
    # com a de suspend, que não tem rótulo)
    for cid, ent in out.items():
        lc = consolidate("lifecycle_controller", ent.get("lifecycle_controller", []))
        if not (lc.known and lc.value["kind"] == "parent"):
            continue
        apis = ent.get("api_resource", [])
        bridged = [c for c in apis if c.get("status") == "resource" and c.get("label")]
        if not bridged:
            continue
        keep = []
        for c in apis:
            if c.get("status") == "aspect" and not c.get("label"):
                continue                                          # o suspend sem rótulo é absorvido
            if c in bridged:
                c = dict(c, status="aspect")
                c["source"] = dict(c["source"], note=c["source"].get("note", "") + " (T49: ciclo de vida do pai)")
            keep.append(c)
        ent["api_resource"] = keep
        reasons[cid].append("api_resource: objeto da ponte com ciclo de vida do pai: aspecto (T49)")
    # T09: bloco embutido herda a evidência da camada de API do gêmeo; a referência do gêmeo ao tipo do bloco
    # vira o pai estrutural ($parent)
    for cid, (r, twin) in sorted(twins.items()):
        top = cid.split(".")[0]
        if twin and "." in twin and twin not in out:
            out.setdefault(twin, {})                  # bloco gêmeo sem fato próprio: herda vazio (UNKNOWN), não erro
        src_ev = out.get(twin)
        if not twin or src_ev is None:
            reasons[cid].append(f"identity: gêmeo {twin} sem evidência traduzida")
            continue
        to_parent = {f for f, m in src_ev.get("field_map", {}).items()
                     if m.get("ref") and src_ev.get("references", {}).get(f) == top}
        ent = out.setdefault(cid, {})
        ent["twin"] = twin
        if any(src_ev.get("field_map", {}).get(f, {}).get("path_parent") for f in to_parent):
            ent["parent_is_path_parent"] = True
        # a evidência do gêmeo SUBSTITUI a do próprio bloco (fatos block_* são da camada Terraform): sem isso o
        # bloco e o recurso separado divergiriam por construção (E2)
        for fld in ("identity", "import_key", "element_name_key", "api_resource", "lifecycle_controller", "owner",
                    "effective_scope"):
            if ent.pop(fld, None):
                reasons[cid].append(f"{fld}: fatos do bloco substituídos pela evidência do gêmeo {twin}")
        for f, m in src_ev.get("field_map", {}).items():
            if f not in to_parent:
                ent.setdefault("field_map", {}).setdefault(f, dict(m))
        for f, tgt in src_ev.get("references", {}).items():
            if f not in to_parent:
                ent.setdefault("references", {}).setdefault(f, tgt)
        note = f"R-GRAIN-T09: herdado do gêmeo {twin}"
        for fld in ("identity", "import_key", "element_name_key", "api_resource", "lifecycle_controller", "owner",
                    "effective_scope"):
            for c in src_ev.get(fld, []):
                c2 = {k: (list(x) if isinstance(x, list) else x) for k, x in c.items() if k != "source"}
                for kk in ("key_fields", "fields"):
                    if kk in c2:
                        c2[kk] = [f for f in c2[kk] if f not in to_parent]
                via = c2.get("via")
                vias = set(via) if isinstance(via, list) else ({via} if isinstance(via, str) else set())
                if vias & to_parent:
                    # CC-1d: via pode ser lista; só as entradas que apontam para o tipo do bloco viram o pai
                    rest = sorted(vias - to_parent)
                    c2["via"] = "$parent" if not rest else ["$parent"] + rest
                if fld == "identity" and c2.get("status") == "present" and to_parent & set(c.get("key_fields", [])):
                    c2["scope"] = "within_parent"
                s = dict(c.get("source") or {"level": "derived", "ref": r["evidence_id"]})
                s["note"] = note + (" / " + s.get("note", "") if s.get("note") else "")
                c2["source"] = s
                put(cid, fld, c2)
    for cid, r in sorted(list_items.items()):
        v = r["value"]
        if cid in value_objects:
            put(cid, "api_resource", {"status": "payload", "label": v.get("item_model"),
                                      "source": _src(r, "R-GRAIN-T62", "item da coleção do pai (T64)")})
        else:
            unknown(cid, "api_resource", r, f"ponte para campo-lista de itens ({v.get('field_type')}): o item não "
                    "é aspecto do pai e a identidade do item não tem evidência (T62)")
    for cid, vo in sorted(value_objects.items()):
        ent = out.setdefault(cid, {})
        ent["value_object"] = {k: x for k, x in vo.items() if k != "source"}
        ent.setdefault("field_map", {})["$content"] = {"path": "$content", "norm": "content"}
        reasons[cid].append("identity: objeto-valor (sem id; conteúdo é a chave; duplicata é outro membro) (T64)")
    for cid, ls in links.items():
        if ls:
            out.setdefault(cid, {})["links"] = {k: dict(x) for k, x in ls.items()}
    # T57, controle: bloco que a API aceita sozinho, por operação própria, não ganha faceta implícita
    for cid in own_ops:
        if out.get(cid, {}).pop("implicit_facet", None):
            reasons[cid].append("identity: bloco com operação própria na API: sem faceta implícita (T57)")
    # T45: bloco timeouts é configuração do Terraform: fora do domínio
    for rt, r in sorted(timeouts.items()):
        out.setdefault(f"{rt}.timeouts", {})["out_of_domain"] = "terraform_timeouts"
    # campos citados nas chaves sem mapa: nome canônico = caminho
    for cid, ent in out.items():
        fm = ent.setdefault("field_map", {})
        for fld in ("identity", "import_key", "element_name_key"):
            for cl in ent.get(fld, []):
                for f in list(cl.get("key_fields", []) or []) + list(cl.get("fields", []) or []):
                    fm.setdefault(f, {"path": f, "norm": "str"})
    return out, dict(reasons)
