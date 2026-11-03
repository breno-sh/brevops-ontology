"""PINS: data de corte única, versão estável de cada provider nessa data e lista histórica (C13).

  python -I -m bo.pins.fetch    instantâneo bruto do Terraform Registry e dos releases da HashiCorp (rede, uma vez)
  python -I -m bo.pins.build    universe/pins.json e universe/history_versions.json a partir do instantâneo (offline)
  python -I -m bo.pins.check    gate: 4 providers, mesma data de corte, toda versão com data e sha do índice

Metadado público apenas; nenhuma conta de nuvem, nenhuma credencial.
"""
