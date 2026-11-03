"""Requisitos: o que a ontologia tem de saber, escrito antes de qualquer indução.

Vocabulário independente de provedor e da futura ontologia. Cada requisito é verificado por
compromissos (commitments_*.py) e/ou CQs (cqs.py); a cobertura (bo.requirements.coverage) reprova
requisito sem nenhum dos dois.
"""

from ..model import req

R = [
    req("REQ-ENT-01", "entity",
        "A ontologia distingue unidades com identidade e ciclo de vida independentes (entidades) de "
        "componentes (identidade própria, ciclo de vida preso ao pai), facetas (sem identidade própria, "
        "configuram um aspecto do dono) e vínculos (identidade = tupla de referências a duas ou mais "
        "unidades independentes). A classificação não depende de a configuração vir como bloco embutido "
        "ou como recurso separado no código, nem da cardinalidade do bloco.",
        "F1: o grão da v2 dependia da embalagem do schema (bloco de cardinalidade 1 virava faceta; o resto "
        "virava entidade por exclusão).",
        ["F1", "R1-M3"], consumers=["GRAIN", "GRAIN-REPRO", "DECOMPOSE", "ONTPAT"]),
    req("REQ-ENT-02", "entity",
        "Tipos rígidos de natureza diferente são disjuntos: nenhum indivíduo é ao mesmo tempo instância "
        "de computação e interface de rede, servidor lógico e instância de banco, namespace de "
        "armazenamento e contêiner, principal e conjunto de permissões, conjunto de regras e regra.",
        "F9: sem disjunções protegidas, o reparo pode passar a aceitar uma VM que também é NIC.",
        ["F9", "R1-M3"], consumers=["AXIOMS", "SEMANTIC-REGRESSION", "REPAIR"]),
    req("REQ-TAX-01", "taxonomy",
        "Subsunção só quando toda instância da subclasse é, sempre, instância da superclasse: um registro "
        "DNS não é zona; uma política de posicionamento não é instância de computação; um host dedicado "
        "não é máquina virtual; uma regra sem estado de conexão não é subclasse de regra com estado.",
        "R1-M3: os erros de hierarquia do esqueleto anterior (registro DNS sob zona, PlacementPolicy sob VM, "
        "regra de ACL sem estado sob regra com estado).",
        ["R1-M3"], consumers=["CLASS", "AXIOMS", "ONTQA"]),
    req("REQ-TAX-02", "taxonomy",
        "Papéis antirrígidos (membro de pool de backend, destino de notificação, alvo de evento, réplica) "
        "não ficam acima de tipos rígidos. A regra OntoClean usada é a correta: classe rígida subsumida por "
        "papel antirrígido é erro; papel subsumido por tipo rígido é válido. O teste roda nas duas direções.",
        "R1-M3 e F9: papéis modelados como tipos rígidos; o exemplo OntoClean da v2 estava invertido.",
        ["R1-M3", "F9", "S2"], consumers=["ONTPAT", "AXIOMS"]),
    req("REQ-CFG-01", "desired_vs_observed",
        "Configuração desejada (o que o código declara), estado observado (o que a leitura devolveu) e "
        "observação (o ato datado de ler) são coisas distintas ligadas ao mesmo recurso. Divergência entre "
        "desejado e observado é representável sem inconsistência e pode ser perguntada.",
        "S1: o contrato da v2 não distinguia HCL, state, recurso de API e observação datada.",
        ["S1"], consumers=["ONTPAT", "ABOX-LIFT", "CQ"]),
    req("REQ-CFG-02", "desired_vs_observed",
        "A origem de cada valor é explícita: configurado, inferido, padrão do provedor ou observado. Valor "
        "que veio do padrão não é registrado como configurado; valor computado só depois da criação não é "
        "registrado como vazio.",
        "S1: separar configurado, inferido, default e observado.",
        ["S1"], consumers=["ONTPAT", "ABOX-LIFT"]),
    req("REQ-ABS-01", "absence",
        "Desconhecido, ausente, não lido e retido são estados distintos. Uma pergunta com negação (\"não "
        "tem alarme\", \"não há caminho\") só responde falso/não sob leitura completa declarada do escopo; "
        "sob leitura parcial a resposta é UNKNOWN. Retido (segredo, conteúdo de objeto, variáveis de "
        "ambiente) pode ter presença conhecida, mas o valor nunca é gravado, nem como hash.",
        "R1 (armadilhas de mundo aberto nas CQs 5 e 7 do esqueleto) e S1 (desconhecido/ausente/não lido/retido).",
        ["S1", "R1-M5", "R1-M8"], consumers=["ONTPAT", "CQ", "CQFIX"]),
    req("REQ-ID-01", "identity",
        "A identidade de um recurso é composta: <conta sintética, provedor, localização, tipo, chave local>. "
        "Dois recursos com a mesma chave local em localizações ou contas diferentes são indivíduos distintos. "
        "Elemento anônimo (bloco sem nome) recebe identidade de ocorrência a partir dos campos de identidade "
        "normalizados e do pai, nunca da posição textual.",
        "F1 (identidade de elemento anônimo, estabilidade sob reordenação) e S1 (identidade composta).",
        ["F1", "S1", "S2"], consumers=["ONTPAT", "GRAIN", "GRAIN-REPRO"]),
    req("REQ-ID-02", "identity",
        "Identidade através do tempo: mudança de atributo mutável feita no lugar mantém o indivíduo (nova "
        "versão de configuração); mudança que força substituição (destruir e recriar) gera indivíduo novo, "
        "e o antigo ganha fim de vida; os dois nunca são declarados o mesmo. Quando a evidência não diz se "
        "a mudança força substituição, a identidade depois da mudança é UNKNOWN.",
        "S2: a ontologia de topo tem de ser escolhida pelos casos de identidade e tempo, não por utilidade imediata.",
        ["S2", "F1"], consumers=["ONTPAT"]),
    req("REQ-LC-01", "lifecycle",
        "Todo componente e toda faceta registram o controlador de ciclo de vida. Apagar o pai apaga seus "
        "componentes e facetas; apagar um vínculo não apaga as unidades que ele liga; entidade independente "
        "sobrevive à remoção de unidades que apenas a referenciam.",
        "F1: o C19 passa a registrar controlador de ciclo de vida, dono e alcance.",
        ["F1"], consumers=["GRAIN", "ONTPAT", "DOMAIN-CONTRACTS"]),
    req("REQ-REL-01", "relation",
        "Onde a configuração é declarada, quem é o dono dela (onde a API a guarda) e a que ela se aplica "
        "(alcance efetivo) são três dados separados. Configuração de nível superior (namespace, conta, "
        "escopo) pode valer para muitas unidades abaixo sem virar faceta de nenhuma delas.",
        "F1: separar contêiner, dono da configuração e alcance efetivo; decidir entre nível de conta e de contêiner.",
        ["F1"], consumers=["GRAIN", "PILOT-STO-ORACLE", "DOMAIN-CONTRACTS"]),
    req("REQ-REL-02", "relation",
        "Parte-todo é tipada (componente de x faceta de) e não se confunde com referência. Uma faceta com "
        "vários donos fica no vínculo ou declara a lista de donos; não é copiada em cada dono.",
        "F1 (facetas com vários donos) e R1-M2/M3 (realização sem parte-todo).",
        ["F1", "R1-M3"], consumers=["ONTPAT", "GRAIN"]),
    req("REQ-NET-01", "network",
        "Filtragem de tráfego separa conjunto de regras, regra, alvo, anexação, direção, estado de conexão, "
        "precedência e efeito. O estado de conexão pode ser do conjunto ou de cada regra; a precedência pode "
        "ser numérica ou por ordem; o efeito pode ser só permitir ou permitir e negar. Regra declarada "
        "embutida no conjunto ou como recurso separado produz a mesma decomposição.",
        "F1: filtragem embutida e separada nos 4 provedores; o conjunto de regras de um provedor tem estado por regra e não é intrinsecamente sem estado.",
        ["F1"], consumers=["PILOT-NET-ORACLE", "GRAIN-REPRO", "DOMAIN-CONTRACTS"]),
    req("REQ-NET-02", "network",
        "Caminho de rede é decisão, não cadeia de propriedades: exige contenção de CIDR, rota até o destino, "
        "endereço alcançável, avaliação das regras aplicáveis com precedência e efeito, e estado de conexão "
        "para o tráfego de retorno. Sob leitura parcial de qualquer peça a resposta é UNKNOWN.",
        "R1 (CQ4 de alcançabilidade não se exprime com cadeia de comprimento 2).",
        ["R1-M5", "R1-M8", "S13"], consumers=["DOMAIN-CONTRACTS", "CQ", "PILOT-NET-ORACLE"]),
    req("REQ-AUTH-01", "authorization",
        "Autorização separa principal, permissão, conjunto de permissões, atribuição, escopo, herança de "
        "escopo, condição de contexto, combinação e efeito (permitir/negar). A decisão de acesso é calculada "
        "por avaliador sobre esses elementos, não lida de um campo.",
        "S13: declarar a autorização não portável predefinia o resultado; faltavam efeito, herança, seleção de principal e combinação.",
        ["S13", "F1"], consumers=["DOMAIN-CONTRACTS", "SERVICE-EVIDENCE", "CATEG"]),
    req("REQ-AUTH-02", "authorization",
        "A mesma concessão <principal, conjunto de permissões, escopo> expressa no código como membro "
        "individual, como ligação com lista de membros ou como documento de política inteiro conta uma "
        "única unidade de decisão.",
        "F1: a mesma política gerida por membro, binding ou documento não conta 3 vezes.",
        ["F1", "S13"], consumers=["GRAIN", "METRICSLIB", "DOMAIN-CONTRACTS"]),
    req("REQ-AUTH-03", "authorization",
        "Principal mantido em diretório fora dos providers fixados é OUT_OF_PIN, não ausência; condição sobre "
        "atributo de contexto que o vocabulário não tem é CONDITION_INDETERMINATE; o que o tradutor não "
        "suporta é UNSUPPORTED_BY_TRANSLATOR. Nenhum desses vira \"negado\" nem \"não existe\".",
        "S13: OUT_OF_PIN, UNSUPPORTED_BY_TRANSLATOR, UNRESOLVED e ausência demonstrada; alegação limitada aos pins.",
        ["S13"], consumers=["DOMAIN-CONTRACTS", "CATEG"]),
    req("REQ-LB-01", "load_balancing",
        "Balanceador é um grafo: frontend, listener, regra de roteamento, pool de backend, membro, sonda de "
        "saúde e certificado TLS são unidades distintas com relações tipadas. Balanceador de camada 4 e de "
        "camada 7 são tipos distintos; roteamento por caminho só existe na camada 7. Realização com recursos "
        "separados ou com blocos embutidos produz o mesmo grafo.",
        "F1: grafo de frontend, listener, roteamento, backend, sonda e TLS; LB e gateway de aplicação separados.",
        ["F1", "R1-M3"], consumers=["DOMAIN-CONTRACTS", "GRAIN-REPRO"]),
    req("REQ-DB-01", "database",
        "Banco gerenciado separa serviço (oferta, não recurso implantado), servidor lógico, instância, banco "
        "lógico, réplica, conjunto de parâmetros e cópia de segurança. Servidor lógico não é instância; banco "
        "lógico não é instância; réplica é instância que desempenha um papel.",
        "F1: separar serviço, servidor, banco lógico, instância, réplica, configuração e backup; servidor lógico não é instância.",
        ["F1", "R1-M3"], consumers=["DOMAIN-CONTRACTS", "GRAIN-REPRO"]),
    req("REQ-STO-01", "storage",
        "Armazenamento de objetos separa namespace (quando o provedor o tem como recurso com configuração "
        "própria), contêiner e objeto. Onde o contêiner vive dentro de um namespace com ciclo de vida próprio, "
        "o contêiner é componente dele; onde não vive, o contêiner é entidade.",
        "F1: no armazenamento com conta, decidir entre nível de conta e nível de contêiner.",
        ["F1"], consumers=["PILOT-STO-ORACLE", "GRAIN", "GRAIN-REPRO"]),
    req("REQ-COMP-01", "composition",
        "Unidade implantável completa = recurso + toda dependência obrigatória para ser criado no destino. "
        "Uma tradução 1:N cria N recursos com as referências entre eles; dependência ausente é dita, não "
        "tapada pelo harness.",
        "F3/F6: tradução recurso a recurso não implementa as traduções estruturais; o harness tapava buracos.",
        ["F1", "S4"], consumers=["GRAPH-LOWERING", "CQ", "CQFIX"]),
    req("REQ-LOSS-01", "loss",
        "Toda tradução que não carrega um valor declara a perda com código; nenhum valor padrão é inventado "
        "para preencher ausência (UNKNOWN_INPUT); correspondência só relacionada não transporta valor; "
        "conversão de duração com mês ou ano exige contexto de calendário.",
        "S4 (família perda) e a objeção sobre durações: mês e ano não são segundos.",
        ["S4", "F9"], consumers=["TRANSFORMS", "SEMANTICS", "TRANSLATOR"]),
    req("REQ-NEW-01", "new_provider",
        "Um provedor retirado da construção é acomodado sem classe nova para conceito que já existe; o que for "
        "exclusivo dele fica em módulo próprio, fora do núcleo; atributo sem conceito fica UNGLOSSED, nunca "
        "ligado ao conceito mais próximo por falta de opção. Os nomes e definições do núcleo não dependem de "
        "vocabulário de um provedor.",
        "S5 (leave-one-provider-out) e R1-M7 (construção semeada por um provedor).",
        ["S4", "R1-M8"], consumers=["HOLDOUT", "CQ", "NAMING"]),
    req("REQ-METH-01", "method",
        "As CQs, suas respostas esperadas e suas fixtures conforme, não conforme e incompleta são congeladas "
        "aqui, em vocabulário independente, antes de qualquer indução; vão além do CIS nas 7 famílias; são "
        "compiladas assim que o vocabulário existir e reexecutadas a cada reparo.",
        "R1-M8 (CQs escritas depois do desenho, sem gabarito) e S4 (CQs cobrem interseção fácil e chegam tarde).",
        ["R1-M8", "S4"], consumers=["CQ", "CQFIX", "CQRUN", "PREREG"]),
    req("REQ-METH-02", "method",
        "Compromissos negativos são protegidos: nenhum reparo pode retirar o axioma ou forma que mantém um "
        "contraexemplo rejeitado; reparo que quebra um compromisso vira versão nova, e o que não fecha vai "
        "para candidatos fora da release. Compromissos UNKNOWN também são protegidos: um reparo não pode "
        "transformar UNKNOWN em resposta definida sem evidência nova.",
        "F9: o reparo podia apagar os axiomas que denunciariam erros.",
        ["F9"], consumers=["AXIOMS", "REPAIR", "SEMANTIC-REGRESSION"]),
    req("REQ-METH-03", "method",
        "A decisão da ontologia de topo usa os compromissos marcados com os eixos identidade, tempo e papel; "
        "cada candidata (incluindo \"nenhuma\") tem de reproduzir as respostas esperadas desses compromissos "
        "e declarar o custo; \"nenhuma\" não pode ser escolhida só porque não gerou inferência no tradutor.",
        "S2: o teste da ontologia de topo escolhia por utilidade imediata.",
        ["S2"], consumers=["ONTPAT"]),
]
