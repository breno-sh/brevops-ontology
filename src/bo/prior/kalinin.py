"""Kalinin e Skvortsov 2026: registro só documental (sem artefato) e notas de método para o KALININ-RECON.

Fonte: texto completo do artigo publicado (PDF local, não redistribuído). Tudo aqui é paráfrase com a página; as
únicas citações literais são nomes de classe, propriedade e tabela, que o texto usa como identificadores. Nada do
PDF é copiado para o repositório além desses nomes.
"""

from __future__ import annotations

import html

from .common import Cls, Extract, Link, Prop

REF = "Kalinin e Skvortsov, Pattern Recognition and Image Analysis 36(2):558-567, 2026, DOI 10.1134/S1054661826700367"
SRC = "kalinin2026.pdf"   # rótulo do arquivo lido (entrada local somente leitura)

# (nome, pais, camada do texto, página, paráfrase)
CLASSES = [
    ("CloudResource", [], "1 (abstrata geral)", 562, "classe de topo de que todo ativo herda; carrega identificador "
     "único e nome legível"),
    ("VirtualMachine", ["CloudResource"], "2 (independente de provedor)", 562, "categoria de serviço que reúne as "
     "máquinas virtuais dos provedores"),
    ("ObjectStorageBucket", ["CloudResource"], "2 (independente de provedor)", 562, "categoria citada na lista da "
     "camada 2"),
    ("RelationalDatabase", ["CloudResource"], "2 (independente de provedor)", 562, "categoria citada na lista da "
     "camada 2"),
    ("NoSQLDatabase", ["CloudResource"], "2 (independente de provedor)", 562, "categoria citada na lista da "
     "camada 2"),
    ("ServerlessFunction", ["CloudResource"], "2 (independente de provedor)", 562, "categoria citada na lista da "
     "camada 2"),
    ("KubernetesCluster", ["CloudResource"], "2 (independente de provedor)", 562, "categoria citada na lista da "
     "camada 2"),
    ("ManagedDatabase", ["CloudResource"], "2 (independente de provedor)", 562, "classe abstrata do agrupamento de "
     "bancos gerenciados; carrega as propriedades alinhadas do agrupamento"),
    ("YandexCloudManagedDatabase", ["ManagedDatabase"], "3 (agrupamento por provedor)", 562, "bancos gerenciados "
     "do Yandex Cloud; pai dos SGBDs específicos desse provedor"),
    ("AwsEc2Instance", ["VirtualMachine"], "4 (atômica, um tipo Terraform)", 562, "folha da hierarquia citada como "
     "subclasse de VirtualMachine"),
    ("AzureVirtualMachine", ["VirtualMachine"], "4 (atômica, um tipo Terraform)", 562, "folha citada como subclasse "
     "de VirtualMachine"),
    ("GoogleComputeInstance", ["VirtualMachine"], "4 (atômica, um tipo Terraform)", 562, "folha citada como "
     "subclasse de VirtualMachine"),
    ("YandexPostgreSQLDatabase", ["YandexCloudManagedDatabase"], "4 (atômica, um tipo Terraform)", 563, "folha "
     "citada como subclasse de YandexCloudManagedDatabase"),
    ("AwsInstance", [], "4 (atômica, um tipo Terraform)", 561, "classe candidata gerada do tipo Terraform "
     "aws_instance na extração; o texto não diz o pai e, na p. 562, chama a folha equivalente de AwsEc2Instance"),
    ("Instance", [], "não dita", 562, "domínio do exemplo de object property isInSubnet"),
    ("Subnet", [], "não dita", 562, "imagem do exemplo de object property isInSubnet"),
    ("PrivateNetwork", [], "não dita", 564, "entidade usada na política SPARQL de segmentação de rede"),
    ("KubernetesMasterNode", [], "não dita", 564, "entidade usada na política SPARQL de segmentação de rede"),
    ("NonCompliant", [], "não dita", 564, "classe de classificação por raciocínio: máquina que viola uma combinação "
     "de regras"),
    ("Account", [], "não dita", 565, "conta usada pela regra SWRL de propagação de comprometimento"),
    ("Compromised", [], "não dita", 565, "classe de estado inferida pela regra SWRL"),
]

# (nome, tipo, domínio, imagem, página, paráfrase)
PROPS = [
    ("instanceSize", "datatype", ["VirtualMachine"], "", 561, "propriedade generalizada que alinha instance_type da "
     "AWS e vm_size da Azure; o texto não declara o domínio, VirtualMachine é a leitura do exemplo"),
    ("engineType", "datatype", ["ManagedDatabase"], "", 562, "propriedade alinhada do agrupamento de bancos"),
    ("databaseVersion", "datatype", ["ManagedDatabase"], "", 562, "propriedade alinhada do agrupamento de bancos"),
    ("storageSize", "datatype", ["ManagedDatabase"], "", 562, "propriedade alinhada do agrupamento de bancos"),
    ("hasHighAvailability", "datatype", ["ManagedDatabase"], "", 562, "propriedade alinhada do agrupamento de "
     "bancos"),
    ("isInSubnet", "object", ["Instance"], "Subnet", 562, "object property que substitui o atributo subnet_id"),
    ("usesAccount", "object", ["VirtualMachine"], "Account", 565, "relação usada na regra SWRL de comprometimento"),
    ("publicIPAddress", "datatype", [], "", 563, "coluna normalizada da view SQL cloud_vms (abordagem relacional)"),
    ("ssh_accessible", "datatype", [], "", 563, "coluna booleana calculada da view cloud_vms (porta 22 aberta à "
     "Internet pelas regras de firewall)"),
    ("is_public", "datatype", [], "", 563, "atributo normalizado da view cloud_storage_buckets"),
]

# (sujeito, objeto, construção, página, frase em paráfrase, provedor)
LINKS = [
    ("kalinin:AwsEc2Instance", "kalinin:VirtualMachine", "text:subclass", 562,
     "AwsEc2Instance é dada como subclasse de VirtualMachine na camada atômica", "aws"),
    ("kalinin:AzureVirtualMachine", "kalinin:VirtualMachine", "text:subclass", 562,
     "AzureVirtualMachine é dada como subclasse de VirtualMachine", "azurerm"),
    ("kalinin:GoogleComputeInstance", "kalinin:VirtualMachine", "text:subclass", 562,
     "GoogleComputeInstance é dada como subclasse de VirtualMachine", "google"),
    ("kalinin:YandexCloudManagedDatabase", "kalinin:ManagedDatabase", "text:subclass", 562,
     "YandexCloudManagedDatabase é subclasse de ManagedDatabase (camada 3)", "other:yandex"),
    ("kalinin:YandexPostgreSQLDatabase", "kalinin:YandexCloudManagedDatabase", "text:subclass", 563,
     "YandexPostgreSQLDatabase é subclasse de YandexCloudManagedDatabase", "other:yandex"),
    ("tf_aws:aws_instance", "kalinin:AwsInstance", "text:atomic_class", 561,
     "cada tipo de recurso Terraform vira classe candidata; aws_instance gera AwsInstance", "aws"),
    ("tfattr_aws:aws_instance.instance_type", "kalinin:instanceSize", "text:property_alignment", 561,
     "instance_type da AWS alinhado à propriedade generalizada instanceSize", "aws"),
    ("tfattr_azurerm:vm_size", "kalinin:instanceSize", "text:property_alignment", 561,
     "vm_size da Azure alinhado a instanceSize (o texto não nomeia o tipo Terraform)", "azurerm"),
    ("tfattr_aws:aws_instance.subnet_id", "kalinin:isInSubnet", "text:id_to_object_property", 562,
     "o atributo subnet_id de uma máquina vira a object property isInSubnet", "aws"),
    ("cqcol:aws_ec2_instances.public_ip", "kalinin:publicIPAddress", "text:property_alignment", 563,
     "a coluna public_ip da tabela CloudQuery aws_ec2_instances é normalizada em publicIPAddress", "aws"),
    ("cqcol:azure_virtual_machines.ip_address", "kalinin:publicIPAddress", "text:property_alignment", 563,
     "a coluna ip_address da tabela CloudQuery azure_virtual_machines é normalizada em publicIPAddress", "azurerm"),
    ("prod_aws:RDS", "kalinin:ManagedDatabase", "text:abstracts_over", 562,
     "ManagedDatabase abstrai implementações como o AWS RDS", "aws"),
    ("prod_azurerm:AzureDatabaseForPostgreSQL", "kalinin:ManagedDatabase", "text:abstracts_over", 562,
     "ManagedDatabase abstrai o Azure Database for PostgreSQL", "azurerm"),
    ("prod_azurerm:AzureDatabaseForMySQL", "kalinin:ManagedDatabase", "text:abstracts_over", 562,
     "ManagedDatabase abstrai o Azure Database for MySQL", "azurerm"),
    ("prod_google:CloudSQL", "kalinin:ManagedDatabase", "text:abstracts_over", 562,
     "ManagedDatabase abstrai o GCP Cloud SQL", "google"),
]

PREFIXES = {"kalinin": "https://doi.org/10.1134/S1054661826700367#",
            "tf_aws": "https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/",
            "tfattr_aws": "https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources#attr/",
            "tfattr_azurerm": "https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs#attr/",
            "cqcol": "https://hub.cloudquery.io/#column/",
            "prod_aws": "https://w3id.org/brevops/prior/product/aws/",
            "prod_azurerm": "https://w3id.org/brevops/prior/product/azurerm/",
            "prod_google": "https://w3id.org/brevops/prior/product/google/"}


def extract(model: str, pdf_label: str, pdf_path, notes_label: str, notes_path) -> Extract:
    ex = Extract(model=model, files=[(pdf_label, pdf_path), (notes_label, notes_path)])
    for name, parents, layer, page, para in CLASSES:
        prov = next((v for k, v in (("Aws", "aws"), ("Azure", "azurerm"), ("Google", "google"),
                                    ("Yandex", "other:yandex")) if name.startswith(k)), "")
        ex.classes.append(Cls(id=f"kalinin:{name}", native=name, label=name,
                              definition=f"{para} (camada {layer}; p. {page})",
                              parents=[f"kalinin:{p}" for p in parents], provider=prov, source=pdf_label,
                              line=page, evidence="DOC_SUPPORTED"))
    for name, kind, dom, rng, page, para in PROPS:
        ex.props.append(Prop(id=f"kalinin:{name}", native=name, label=name, kind=kind,
                             domain=[f"kalinin:{d}" for d in dom], domain_kind="text" if dom else "",
                             range=f"kalinin:{rng}" if rng else "", definition=f"{para} (p. {page})",
                             source=pdf_label, line=page, evidence="DOC_SUPPORTED"))
    for s, o, rel, page, sent, prov in LINKS:
        level = "property" if o.split(":", 1)[1][:1].islower() else "class"
        kind = ("provider_field_to_model_property" if level == "property" else "provider_class_to_model_class")
        ex.links.append(Link(subject=s, object=o, native_relation=rel, link_kind=kind, level=level, provider=prov,
                             source=pdf_label, line=page, sentence=sent + f" (p. {page})",
                             subject_label=s.split(":", 1)[1], object_label=o.split(":", 1)[1], evidence="UNRESOLVED",
                             note="só documental: vínculo afirmado no texto, sem artefato que o mostre"))
    ex.prefixes = dict(PREFIXES)
    ex.counts = {"classes_named_in_text": len(CLASSES), "properties_named_in_text": len(PROPS),
                 "links_stated_in_text": len(LINKS), "artifact": "indisponível"}
    ex.notes.append("a página do PDF ocupa a coluna 'line' (fonte = PDF, linha = página)")
    ex.notes.append("inconsistência do texto: a classe do tipo aws_instance é AwsInstance na p. 561 e a folha "
                    "equivalente é AwsEc2Instance na p. 562")
    return ex


# ------------------------------------------------------------------------------------------- notas de método
STEPS = [
    ("1", "Casamento de propriedades", "Propriedades parecidas entre recursos são casadas por semelhança de nome, "
     "faixa de valores esperada e interpretação de especialista da documentação; o resultado são conjuntos de "
     "atributos equivalentes (ex.: instance_type e vm_size viram instanceSize).", 561,
     "medida de semelhança de nome; limiar; como a faixa de valores entra; o que conta como interpretação de "
     "especialista (sem protocolo, sem segundo avaliador)"),
    ("2", "Clusterização de recursos", "Recursos com alta proporção de atributos alinhados em comum (sobretudo os "
     "do passo 1) são agrupados; o texto compara com Análise Formal de Conceitos (cada grupo como um conceito "
     "formal definido por atributos compartilhados).", 561,
     "algoritmo (FCA de fato ou agrupamento aproximado); proporção mínima de atributos comuns; pesos dos atributos "
     "'chave'; se um recurso pode estar em mais de um grupo"),
    ("3", "Abstração do grupo", "Para cada grupo nasce uma classe pai abstrata com as propriedades alinhadas como "
     "denominador comum; cada recurso do grupo vira subclasse dela (ex.: ManagedDatabase).", 562,
     "nome da classe abstrata; se o denominador comum é interseção estrita ou maioria"),
    ("4", "Generalização global", "Propriedades presentes em quase todos os recursos (identificador, nome, "
     "etiquetas) sobem para classes de topo, como CloudResource.", 562,
     "o que é 'quase todos' (limiar); quais propriedades sobem"),
    ("5", "Object properties", "Atributos que são identificadores ou referências a outros recursos (X_id, nomes de "
     "outros recursos) são analisados e trocados por relações explícitas com a classe certa (subnet_id vira "
     "isInSubnet, de Instance para Subnet).", 562,
     "regra de detecção de identificador (sufixo _id, tipo, documentação); como achar a classe de destino; o que "
     "fazer quando o destino é ambíguo"),
    ("6", "Preservação do local ao provedor", "Classes e propriedades sem par em outra nuvem ficam como locais do "
     "provedor, sob o ramo dele, ainda herdando das classes de topo (ex.: Route53, BigQuery).", 562,
     "o que conta como 'sem par' (depende dos limiares dos passos 1 e 2)"),
]

LAYERS = [
    ("1", "Classes abstratas gerais", "poucas classes universais; ex.: CloudResource", 562),
    ("2", "Classes independentes de provedor", "uma por grupo de serviços equivalentes; ex.: VirtualMachine, "
     "ObjectStorageBucket, RelationalDatabase, NoSQLDatabase, ServerlessFunction, KubernetesCluster, "
     "ManagedDatabase", 562),
    ("3", "Agrupamentos por provedor", "subclasses das da camada 2 dentro de um provedor, criadas só quando o "
     "provedor tem vários recursos na categoria ou restrições comuns; ex.: YandexCloudManagedDatabase", 562),
    ("4", "Classes atômicas", "uma por tipo de recurso Terraform; folhas onde ficam as instâncias; ex.: "
     "AwsEc2Instance, AzureVirtualMachine, GoogleComputeInstance, YandexPostgreSQLDatabase", 562),
]

CQS = [
    ("CQ1", "inventário", "que ativos existem nos vários provedores e como são tipados, agrupados e localizados", 561),
    ("CQ2", "identidade e acesso", "que identidades ou serviços têm controle ou acesso relevante sobre um ativo e, "
     "ao contrário, sobre que ativos um principal pode agir", 561),
    ("CQ3", "caminhos de rede", "que caminhos de conectividade existem entre ativos, inclusive exposição a redes "
     "externas", 561),
    ("CQ4", "desvio de baseline", "que ativos se afastam dos requisitos ou políticas de segurança acordados", 561),
    ("CQ5", "propagação de comprometimento", "supondo um componente comprometido, que outros ativos ficam "
     "alcançáveis, gerenciáveis ou em risco", 561),
]

OPEN = [
    ("versões dos providers Terraform", "não informadas", "fixar as nossas (PINS) e declarar"),
    ("provedores", "AWS, Azure, GCP, Yandex Cloud, Cloud.ru", "aqui saem Yandex e Cloud.ru e entra OCI; declarar "
     "como divergência"),
    ("data sources", "a extração cobre resources e data sources (p. 561)", "eixo: com e sem data sources"),
    ("enriquecimento por documentação", "descrições do Terraform e, quando preciso, da API viram anotações (p. 561)",
     "eixo: com e sem uso do texto da documentação no casamento do passo 1"),
    ("semelhança de nome (passo 1)", "não especificada", "eixo: igualdade normalizada, distância de edição com "
     "limiar, tokens"),
    ("faixa de valores (passo 1)", "citada sem regra", "eixo: exigir tipo igual, tipo compatível, ignorar"),
    ("agrupamento (passo 2)", "'parecido com FCA', sem algoritmo nem limiar", "eixo: reticulado FCA com suporte "
     "mínimo; agrupamento hierárquico por Jaccard com limiares"),
    ("denominador comum (passo 3)", "não especificado", "eixo: interseção estrita; maioria"),
    ("limiar de generalização global (passo 4)", "'quase todos' os recursos", "eixo: limiares de frequência"),
    ("detecção de identificador (passo 5)", "X_id e referências a nomes, 'analisados sistematicamente'", "eixo: só "
     "sufixo _id; sufixo + documentação; referência do schema"),
    ("camada 3", "criada quando o provedor tem vários recursos na categoria", "regra determinística a partir do "
     "agrupamento"),
    ("ontologia de topo", "deliberadamente adiada", "nenhuma; não alinhar a BFO/DOLCE na reconstrução"),
    ("perfil OWL", "OWL DL com owlready2 (p. 563)", "manter OWL DL; conferir perfil"),
    ("ABox", "CloudQuery coleta; (a) views SQL harmonizadas ou (b) indivíduos OWL num repositório RDF (p. 563-564)",
     "gerar a ABox dos mesmos fatos de origem (BENCH-CONTRACT), não da ABox da BrevOps"),
    ("versão do CloudQuery", "não informada; em 2025-26 o plugin AWS já é pago e fechado", "o PRIOR só tem o "
     "CloudQuery aberto até 2024-03-04 (6d350d2); declarar a diferença"),
]


def method_notes_html(edited_at: str, pdf_sha256: str, notes_sha256: str) -> str:
    e = html.escape

    def table(head, rows):
        out = ["<table><thead><tr>" + "".join(f"<th>{e(h)}</th>" for h in head) + "</tr></thead><tbody>"]
        for r in rows:
            out.append("<tr>" + "".join(f"<td>{e(str(c))}</td>" for c in r) + "</tr>")
        out.append("</tbody></table>")
        return "\n".join(out)

    steps = table(["passo", "nome", "o que o texto diz (paráfrase)", "pág.", "o que o texto deixa em aberto"],
                  STEPS)
    layers = table(["camada", "nome", "conteúdo", "pág."], LAYERS)
    cqs = table(["id", "tema", "pergunta (paráfrase)", "pág."], CQS)
    opens = table(["escolha", "o que o texto diz", "como a família de reconstruções trata"], OPEN)
    cls = table(["classe", "pais no texto", "camada", "pág."], [(c[0], ", ".join(c[1]) or "—", c[2], c[3])
                                                               for c in CLASSES])
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kalinin notas de método</title>
<style>
:root {{ --bg:#ffffff; --fg:#1d232a; --muted:#5b6670; --line:#d9dee3; --head:#f3f5f7; --accent:#2457a6; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#14181c; --fg:#e6eaee; --muted:#9aa5ae;
  --line:#2c343b; --head:#1c2227; --accent:#8fb4ff; }} }}
:root[data-theme="dark"] {{ --bg:#14181c; --fg:#e6eaee; --muted:#9aa5ae; --line:#2c343b; --head:#1c2227;
  --accent:#8fb4ff; }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, sans-serif; margin:0 auto; max-width:1100px;
  padding:16px; }}
h1 {{ font-size:1.4em; }} h2 {{ font-size:1.12em; margin-top:1.6em; color:var(--accent); }}
table {{ border-collapse:collapse; width:100%; margin:.6em 0; display:block; overflow-x:auto; }}
th, td {{ border:1px solid var(--line); padding:5px 8px; vertical-align:top; text-align:left; }}
th {{ background:var(--head); }} .muted {{ color:var(--muted); font-size:.9em; }}
</style></head><body>
<h1>Kalinin e Skvortsov 2026: notas de método</h1>
<p class="muted">Módulo PRIOR do BrevOps Ontology. Conteúdo editado em {e(edited_at)} (America/Recife).
Fonte: texto completo do artigo publicado, lido do PDF local (sha256 {e(pdf_sha256)}), que não é redistribuído;
fichamento sha256 {e(notes_sha256)}. Tudo abaixo é paráfrase com a página; nomes de classe, propriedade e tabela
são os do texto. Consumidores: BENCH-CONTRACT e KALININ-RECON.</p>

<h2>1. Estado</h2>
<p>{e(REF)}. O <b>artigo está publicado</b>; o <b>artefato ontológico não está disponível</b> (o texto não traz
link, IRI nem repositório). Eles implementam a ontologia em OWL DL com owlready2 (p. 563), populam uma ABox a partir
do inventário coletado pelo CloudQuery, formulam políticas CSPM em SQL e SPARQL (p. 563-564) e modelam cadeias de
ataque com regras SWRL raciocinadas com HermiT (p. 565). O que falta é avaliação quantitativa: o texto não dá número
de classes, de propriedades, cobertura, precisão dos alinhamentos nem resultado das 5 perguntas de competência.
Por isso o registro deste modelo no PRIOR é <b>só documental</b>.</p>

<h2>2. Os 6 passos de generalização (seção 3.3)</h2>
<p>Antes dos passos: cada tipo de recurso e de data source dos providers Terraform de AWS, Azure, GCP, Yandex Cloud
e Cloud.ru vira classe candidata e cada parâmetro vira propriedade candidata, de início como data property (3.1,
p. 561); descrições da documentação Terraform e, quando preciso, da API entram como anotações e servem de camada
semântica para o alinhamento (3.2, p. 561).</p>
{steps}

<h2>3. As 4 camadas (seção 3.4)</h2>
{layers}

<h2>4. As 5 perguntas de competência, todas de segurança (p. 561)</h2>
{cqs}
<p class="muted">O texto valida o modelo contra estas perguntas, mas não relata como nem com que resultado.</p>

<h2>5. Implementação e uso</h2>
<ul>
<li>Construção em OWL DL com a biblioteca owlready2 (p. 563).</li>
<li>Coleta: o CloudQuery lê as APIs de AWS, Azure, GCP, Yandex Cloud e Cloud.ru e grava tabelas por provedor num
banco relacional (ex.: aws_ec2_instances, azure_virtual_machines), heterogêneas entre si (p. 563).</li>
<li>Abordagem (a), relacional: views ou tabelas novas que correspondem a classes da ontologia (ex.: cloud_vms) com
campos normalizados (public_ip e ip_address viram publicIPAddress) e atributos de segurança calculados
(ssh_accessible); políticas CSPM viram consultas SQL (ex.: buckets públicos em cloud_storage_buckets) (p. 563).</li>
<li>Abordagem (b), grafo: cada ativo vira indivíduo OWL da classe certa num repositório RDF; políticas CSPM viram
consultas SPARQL (ex.: máquinas fora de rede privada que alcançam um nó mestre de Kubernetes); um raciocinador pode
classificar ativos como NonCompliant; requisitos CIS ou GOST viram consultas ou regras (p. 564).</li>
<li>Cadeias de ataque: regras OWL ou SWRL de propagação de comprometimento (ex.: máquina comprometida que usa uma
conta compromete a conta, via usesAccount); HermiT infere as consequências; o texto relata problema de desempenho
em infraestruturas grandes e diz que, após particionar por organização e região, a maioria dos conjuntos fica
abaixo de dez mil recursos (p. 565).</li>
<li>Protótipo: o texto diz que existe um protótipo que usa o CloudQuery e transforma os dados num grafo, sem
número nem artefato (p. 566).</li>
</ul>

<h2>6. Classes e propriedades nomeadas no texto</h2>
{cls}
<p class="muted">Propriedades: instanceSize, engineType, databaseVersion, storageSize, hasHighAvailability,
isInSubnet, usesAccount e as colunas de view publicIPAddress, ssh_accessible, is_public. Lista completa, com página,
em classes.csv, properties.csv e provider_links.sssom.tsv desta pasta. Inconsistência do texto: a classe do tipo
aws_instance chama-se AwsInstance na p. 561 e AwsEc2Instance na p. 562.</p>

<h2>7. Escolhas que o texto não determina (eixos da família de reconstruções)</h2>
{opens}
<p class="muted">Regra para o KALININ-RECON: toda escolha desta tabela é um eixo declarado no kalinin_family.yaml
antes de rodar; o resultado é relatado como faixa e sempre como "reconstrução nossa"; nenhuma variante é escolhida
depois de ver o resultado.</p>

<h2>8. Limitações que os próprios autores declaram (p. 566)</h2>
<ul>
<li>manter e evoluir a ontologia exige esforço contínuo;</li>
<li>regras de propagação podem ganhar dados dinâmicos (logs, alertas);</li>
<li>integração com o desenvolvimento permitiria barrar configuração insegura antes da produção;</li>
<li>escala: raciocinadores OWL padrão sofrem em infraestruturas muito grandes;</li>
<li>falta investigar compatibilidade com ferramentas e práticas existentes;</li>
<li>muitos ativos não estão nos providers Terraform e precisariam vir das APIs (p. 559).</li>
</ul>

<h2>9. Diferenças frente ao nosso estudo</h2>
<ul>
<li>provedores: saem Yandex Cloud e Cloud.ru, entra OCI;</li>
<li>a camada atômica deles é o tipo Terraform (herdam o grão do Terraform);</li>
<li>alinhamento por julgamento, sem tipo de equivalência (exata, ampla, estreita), sem tratamento de 1:N e sem
validação objetiva;</li>
<li>não medem tradução entre provedores, cobertura operacional nem deriva entre versões.</li>
</ul>
</body></html>
"""
