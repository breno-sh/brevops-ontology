"""ROLES: papel de cada átomo C01 (CONFIG, IDENTIFIER, NAME, TAG, REFERENCE, TIMESTAMP, SECRET) -> C04.

  python -I -m bo.roles.build [--check]   gera (ou confere) $BO_DATA/ROLES/roles.jsonl e results/ROLES/by_provider.json
  python -I -m bo.roles.symmetry          higiene: mesma regra nos 4, nenhuma regra cita provedor, permutação
  python -I -m bo.roles.manifest [--check]
"""
