"""GOLD-XPLANE: ouro externo a partir de composições Crossplane multi-provedor.

Cada patch de composição liga um campo do recurso composto (XR) a um campo do recurso gerenciado (MR). Dois
provedores que implementam o mesmo XR dão, por composição pelo campo do XR, um par MR(a) <-> MR(b). O patch não
prova equivalência: toda linha entra no nível DERIVADO, com evidence_state STRUCTURALLY_VALID (ou UNRESOLVED
quando um lado não resolve no schema do provider fixado).

  python -I -m bo.gold_xplane.fetch     baixa as fontes fixadas para $BO_DATA/downloads/crossplane/ (rede)
  python -I -m bo.gold_xplane.build     gera $BO_DATA/GOLD-XPLANE/* e results/GOLD-XPLANE/* (sem rede)
  python -I -m bo.gold_xplane.resolve   todo campo resolve num campo registrado do schema fixado ou é unresolved
"""
