"""Esforço real do agente por passo do brief (relógio de parede, America/Recife), para o PILOT-EXIT recalibrar.

Horas medidas pelos carimbos da sessão de trabalho (início e fim de cada passo); 'wait' é tempo parado esperando
dependência (PILOT-NET-MAP), contado à parte e fora das horas de trabalho.
"""

LEDGER = {
    "agent": "claude-opus-5-5",
    "started_at": "2026-11-04T09:10:00-03:00",
    "steps": [
        {"step": "leitura do brief, plano, contratos, oráculo e harnesses", "start": "09:10", "end": "09:20",
         "agent_hours": 0.17},
        {"step": "vocabulário de realização, lifting e catálogo de axiomas", "start": "09:20", "end": "09:32",
         "agent_hours": 0.20},
        {"step": "gerador do módulo OWL (TBox por controle) e tabelas C14", "start": "09:32", "end": "09:36",
         "agent_hours": 0.07},
        {"step": "três controles de raciocínio (owlrl, HermiT pelo ROBOT, SHACL)", "start": "09:36", "end": "09:40",
         "agent_hours": 0.07},
        {"step": "transporte por alegação, alegações sintéticas e tradução (IR de grafo e plano)", "start": "09:40",
         "end": "09:52", "agent_hours": 0.20},
        {"step": "lowering nos 4 provedores, render pelos HARNESS-* e releitura para o oráculo", "start": "09:52",
         "end": "10:02", "agent_hours": 0.17},
        {"step": "pipeline das 12 direções, política de perda e juiz do oráculo", "start": "10:02", "end": "10:06",
         "agent_hours": 0.07},
        {"step": "gates: grain_check, no_silent_insert, tf_validate, oracle_eval", "start": "10:06", "end": "10:11",
         "agent_hours": 0.08},
        {"step": "testes, gate do módulo, resultados e proveniência", "start": "10:11", "end": None,
         "agent_hours": None},
        {"step": "integração com o mapeamento real (PILOT-NET-MAP) e rerodada dos gates", "start": None, "end": None,
         "agent_hours": None},
    ],
    "wait": [],
}
