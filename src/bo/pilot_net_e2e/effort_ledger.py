"""Esforço real do agente por passo do brief (relógio de parede, America/Recife), para o PILOT-EXIT recalibrar.

Horas pelos carimbos da sessão de trabalho (saída das ferramentas: criação da lane 09:12, primeiro render 09:18,
ROBOT 09:37, primeiro juiz ~09:55, CLIs 10:04, testes 10:14, segunda passada até 10:29). 'wait' é tempo parado
esperando a dependência (PILOT-NET-MAP em bo/base), fora das horas de trabalho.
"""

LEDGER = {
    "agent": "claude-opus-5-5",
    "started_at": "2026-11-04T09:10:00-03:00",
    "expected_h": 6,
    "steps": [
        {"step": "leitura do brief, plano, contratos, oráculo, harnesses e biblioteca de grão; desenho",
         "start": "09:10", "end": "09:26", "agent_hours": 0.27},
        {"step": "vocabulário de realização, lifting, catálogo de axiomas, gerador OWL/C14 e os 3 controles",
         "start": "09:26", "end": "09:38", "agent_hours": 0.20},
        {"step": "alegações (C09/C21), alegações sintéticas, transporte e tradução para IR de grafo e plano",
         "start": "09:38", "end": "09:52", "agent_hours": 0.23},
        {"step": "lowering nos 4 provedores, render pelos HARNESS-*, releitura para o oráculo, política de perda",
         "start": "09:52", "end": "10:00", "agent_hours": 0.13},
        {"step": "pipeline das 12 direções e comandos run/oracle_eval", "start": "10:00", "end": "10:06",
         "agent_hours": 0.10},
        {"step": "gates grain_check, no_silent_insert, tf_validate", "start": "10:06", "end": "10:11",
         "agent_hours": 0.08},
        {"step": "testes, gate do módulo, achados de contrato, primeiro commit", "start": "10:11", "end": "10:15",
         "agent_hours": 0.07},
        {"step": "segunda passada: guardas C10, traço por valor completo, perfil DL, pista da tabela, defeitos",
         "start": "10:15", "end": "10:29", "agent_hours": 0.23},
        {"step": "integração com o mapeamento real (PILOT-NET-MAP), resultados e rerodada dos gates",
         "start": None, "end": None, "agent_hours": None},
    ],
    "wait": [],
}
