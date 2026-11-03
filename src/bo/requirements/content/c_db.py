"""Caso adversarial DB: serviço, servidor lógico, instância, banco lógico, réplica, parâmetros e backup."""

from ..model import cm, fx, ground

CONS = ["DOMAIN-CONTRACTS", "GRAIN", "GRAIN-REPRO", "AXIOMS", "SEMANTIC-REGRESSION", "CQFIX"]

G_SERVER = [
    ground("azurerm", "azurerm_mssql_server é servidor lógico (contêiner administrativo, sem computação exposta); azurerm_mssql_database é banco lógico com SKU próprio. azurerm_postgresql_flexible_server, ao contrário, é instância"),
    ground("aws", "aws_rds_cluster é o servidor lógico do cluster; aws_rds_cluster_instance são as instâncias; aws_db_instance é instância isolada"),
    ground("google", "google_sql_database_instance é instância; google_sql_database é banco lógico; não há servidor lógico"),
    ground("oci", "oci_database_autonomous_database é serviço gerido sem instância exposta; oci_mysql_mysql_db_system é instância"),
]
G_PARTS = [
    ground("aws", "aws_db_parameter_group é compartilhável por várias instâncias; aws_db_snapshot é cópia manual com ciclo de vida próprio; backup_retention_period é atributo da instância; réplica por replicate_source_db"),
    ground("google", "database_flags{} embutidos em settings{}: parâmetros não compartilháveis; backup_configuration{} embutido; réplica por master_instance_name"),
    ground("azurerm", "parâmetros por azurerm_postgresql_flexible_server_configuration (um por parâmetro, preso ao servidor)"),
    ground("oci", "configuração do MySQL por oci_mysql_mysql_configuration, referenciável por vários sistemas"),
]


C = [
    cm("CMT-DB-P01", "DB", "positive", "count",
       "Servidor lógico com dois bancos lógicos e sem instância exposta: a ABox tem um servidor lógico, dois "
       "bancos e nenhuma instância de banco.",
       "COUNT db_instance = 0 AND COUNT logical_database = 2 AND COUNT logical_server = 1",
       fx("FX-DB-P01", "servidor lógico com dois bancos",
          "srv1:logical_server db1:logical_database db2:logical_database",
          ["db1 database_on srv1", "db2 database_on srv1"],
          ["srv1.engine=engine_a", "srv1.local_key=srv_a", "db1.local_key=sales", "db2.local_key=stock"]),
       0, "servidor lógico não é instância (F1)", ["REQ-DB-01"], ["F1"], "servidor lógico != instância",
       grounding=G_SERVER, consumers=CONS),
    cm("CMT-DB-P02", "DB", "positive", "count",
       "Instância primária com uma réplica de leitura: duas instâncias; a réplica é instância (tipo rígido) que "
       "desempenha o papel de réplica da primária.",
       "COUNT db_instance = 2 AND replica_of(i2, i1) AND type(i2) = db_instance",
       fx("FX-DB-P02", "primária e réplica", "i1:db_instance i2:db_instance", ["i2 replica_of i1"],
          ["i1.engine=engine_b", "i2.engine=engine_b"]),
       2, "réplica é papel sobre instância", ["REQ-DB-01", "REQ-TAX-02"], ["F1", "R1-M3"], "réplica como papel",
       axes=["role"], grounding=G_PARTS[:2], consumers=CONS),
    cm("CMT-DB-P03", "DB", "positive", "entails",
       "Conjunto de parâmetros usado por duas instâncias é entidade independente referenciada por elas, não "
       "faceta de nenhuma.",
       "kind(ps1) = ENTITY AND NOT facet_of(ps1, i1) AND NOT facet_of(ps1, i3)",
       fx("FX-DB-P03", "conjunto de parâmetros compartilhado",
          "ps1:db_parameter_set i1:db_instance i3:db_instance",
          ["i1 uses_parameter_set ps1", "i3 uses_parameter_set ps1"], ["ps1.lifecycle_controller=self"]),
       "ENTAILED", "faceta com vários donos não é copiada (REQ-REL-02)", ["REQ-DB-01", "REQ-REL-02"], ["F1"],
       "compartilhamento x faceta", grounding=G_PARTS, consumers=CONS),
    cm("CMT-DB-P04", "DB", "positive", "entails",
       "A retenção de backup automático é faceta da instância; a cópia de segurança manual é entidade com ciclo "
       "de vida próprio, que sobrevive à remoção da instância onde o provedor a retém.",
       "facet_of(retenção, i1) AND kind(b1) = ENTITY AND lifecycle_controller(b1) = self",
       fx("FX-DB-P04", "backup automático e cópia manual",
          "i1:db_instance b1:db_backup", ["b1 backup_of i1"],
          ["i1.backup_retention_days=7", "b1.lifecycle_controller=self"]),
       "ENTAILED", "backup separado em faceta e entidade (F1)", ["REQ-DB-01", "REQ-LC-01"], ["F1"],
       "backup como faceta x entidade", grounding=G_PARTS[:1], consumers=CONS),
    cm("CMT-DB-N01", "DB", "negative", "rejects",
       "Nenhum indivíduo é ao mesmo tempo servidor lógico e instância de banco.",
       "fixture com x1 de tipo logical_server e db_instance é inconsistente",
       fx("FX-DB-N01", "indivíduo declarado servidor lógico e instância",
          "x1:logical_server+db_instance", [], ["x1.local_key=srv_a"]),
       "REJECTED", "servidor lógico não é instância (F1)", ["REQ-ENT-02", "REQ-DB-01"], ["F1", "F9"],
       "disjunção servidor lógico x instância", code="INCONSISTENT", grounding=G_SERVER[:1], consumers=CONS),
    cm("CMT-DB-N02", "DB", "negative", "not_entails",
       "Banco lógico não é instância: uma instância com três bancos lógicos não é contada como três instâncias.",
       "NOT COUNT(db_instance) = 3",
       fx("FX-DB-N02", "instância com três bancos lógicos",
          "i1:db_instance db1:logical_database db2:logical_database db3:logical_database",
          ["db1 database_on i1", "db2 database_on i1", "db3 database_on i1"], ["i1.engine=engine_b"]),
       "NOT_ENTAILED", "banco lógico e instância são tipos distintos", ["REQ-DB-01"], ["F1"],
       "contagem de instâncias", consumers=CONS),
    cm("CMT-DB-N03", "DB", "negative", "not_entails",
       "A oferta de serviço de banco é classificação, não recurso implantado: nenhuma fixture cria um indivíduo "
       "\"serviço de banco\" ao lado da instância.",
       "NOT EXISTS x: x é recurso implantado do tipo serviço de banco",
       fx("FX-DB-N03", "instância isolada", "i1:db_instance", [], ["i1.engine=engine_a"]),
       "NOT_ENTAILED", "serviço != recurso (F1)", ["REQ-DB-01", "REQ-TAX-01"], ["F1", "R1-M3"],
       "serviço fora da ABox", consumers=CONS),
    cm("CMT-DB-U01", "DB", "unknown", "unknown",
       "Servidor gerido com alta disponibilidade sem instâncias expostas: quantas instâncias de computação o "
       "sustentam é UNKNOWN (nem 0 nem 1); a ABox continua sem indivíduo de instância (CMT-DB-P01).",
       "COUNT instâncias que sustentam srv2 = UNKNOWN",
       fx("FX-DB-U01", "servidor gerido com alta disponibilidade",
          "srv2:logical_server", [], ["srv2.ha_managed=true"], complete=False, not_read=["srv2.instance_count"]),
       "UNKNOWN", "zero indivíduos na ABox não é zero instâncias no mundo", ["REQ-DB-01", "REQ-ABS-01"], ["F1"],
       "UNKNOWN x 0", code="MISSING_EVIDENCE", grounding=G_SERVER[3:], consumers=CONS),
    cm("CMT-DB-U02", "DB", "unknown", "unknown",
       "Retenção de backup não declarada e padrão do provedor sem evidência: a retenção é UNKNOWN, não 0 e não "
       "um padrão inventado.",
       "backup_retention(i1) = UNKNOWN",
       fx("FX-DB-U02", "instância sem retenção declarada", "i1:db_instance", [], ["i1.engine=engine_b"],
          complete=False, not_read=["i1.default"]),
       "UNKNOWN", "default não inventado (REQ-CFG-02)", ["REQ-CFG-02", "REQ-ABS-01"], ["F1", "S1"],
       "default não assumido", code="MISSING_EVIDENCE", consumers=CONS),
]
