"""G1: roda o código CONGELADO dos dois E2E nas fixtures RETIDAS; sha do código = sha do E2E.

  python -I -m bo.pilot.heldout_run --slices sto,net        (despacha para bo.pilot_exit.heldout_run)
      sem execução registrada para este código congelado: executa (uma TENTATIVA do E8) e grava o registro;
      com execução registrada para o mesmo código e o mesmo selo: só confere (não decifra de novo, não conta
      tentativa) e sai 0 se o registro, a evidência e o sha do código continuam batendo.
  --reproduce   executa de novo o MESMO código (reprodução, não é tentativa nova; o registro guarda as duas)

Por fatia: (1) identifica o código congelado (frozen.identify) e para se ele mudou depois da entrega;
(2) exporta a árvore do commit avaliado para $BO_TMP; (3) decifra as retidas pela VM (unseal) e confere com o
índice; (4) põe as retidas no leiaute da calibração (materialize); (5) roda os gates do próprio E2E (runner);
(6) extrai a evidência dos critérios (collect) e (7) apaga a árvore temporária. Grava:
  results/PILOT-EXIT/heldout_run.json                       registro (shas, comandos, contagens; sem conteúdo)
  $BO_DATA/PILOT-EXIT/.staging/heldout/<fatia>/evidence.json  evidência por fatia (ids e códigos, sem valores)
  $BO_DATA/PILOT-EXIT/.staging/heldout/attempts.jsonl         livro das tentativas (E8)
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

from . import collect, common as C, frozen, materialize, runner, unseal

RECORD = "heldout_run.json"


def record_path(root: Path | None = None) -> Path:
    return C.results_dir(root) / RECORD


def attempts_path() -> Path:
    return C.run_data_dir() / "attempts.jsonl"


def key_of(ids: dict, seals: dict) -> str:
    return C.sha_bytes(C.canon({s: [ids[s]["code_sha256"], seals[s]["ciphertext_sha256"]] for s in sorted(ids)}))


def seal_lineage(slice_: str, root: Path) -> set:
    """Envelopes do MESMO conjunto retido: o atual e os que ele substituiu por re-selagem declarada (o índice
    ativo aponta o texto claro anterior em revision.of_plaintext_sha256; o índice aposentado dá o envelope).
    Conjunto novo (ciclo novo, PREREG 3b3d4cb) não tem esse elo e começa a contagem do zero."""
    idx = unseal.index_of(slice_, root)
    out = {unseal.envelope_sha(slice_, idx)}
    sealed = C.expand(C.SLICES[slice_]["index"], root).parent
    retired = {}
    for p in list(sealed.parent.glob("retired/*/SEALED_INDEX.json")) + list(sealed.glob("sealed_index_*retired*.json")):
        r = C.read_json(p) or {}
        if r.get("plaintext_sha256"):
            retired[r["plaintext_sha256"]] = r
    cur = idx
    for _ in range(20):
        rev = cur.get("revision")
        prev = rev.get("of_plaintext_sha256") if isinstance(rev, dict) else None
        if not prev or prev not in retired:
            break
        cur = retired[prev]
        out.add(unseal.envelope_sha(slice_, cur))
    return out


def load_attempts() -> list:
    p = attempts_path()
    return C.read_jsonl(p) if p.is_file() else []


def verify_existing(rec: dict, ids: dict, seals: dict) -> list[str]:
    errs = []
    if rec.get("status") != "COMPLETE":
        errs.append(f"registro com status {rec.get('status')}")
    if rec.get("key") != key_of(ids, seals):
        errs.append("registro é de outro código ou outro selo")
    for s, ev in (rec.get("evidence") or {}).items():
        p = C.run_data_dir() / s / "evidence.json"
        if not p.is_file():
            errs.append(f"evidência ausente: {C.portable(p)}")
        elif C.sha_file(p) != ev.get("sha256"):
            errs.append(f"evidência {s} mudou depois da execução")
    return errs


def calib_bundle(slice_: str) -> dict:
    """Pacote da calibração PÚBLICA no formato do selo (ensaio do avaliador; nunca as retidas)."""
    if slice_ == "sto":
        from bo.pilot_sto_oracle import cases
        g = cases.generate("calib")
        return {"fixtures": g.fixtures, "entries": g.entries}
    from bo.pilot_net_oracle import calib
    return {"fixtures": calib.fixtures(), "translations": calib.translations()}


def run_slice(slice_: str, ident: dict, root: Path, workdir: Path, decrypt_argv=C.VM_DECRYPT_ARGV,
              rehearsal: bool = False) -> dict:
    s = C.SLICES[slice_]
    mid = s["e2e"]
    t0 = time.monotonic()
    rdir = workdir / slice_
    if rdir.exists():
        shutil.rmtree(rdir)
    frozen_repo = frozen.export(root, ident["base_head"], rdir / "repo")
    check = frozen.tree_files(root, ident["base_head"], s["code"])
    if frozen.digest(check) != ident["code_sha256"]:
        raise frozen.FrozenError("cópia exportada ≠ sha do código congelado")
    # BO_DATA sobreposto em caminho curto: o STO exige BO_TMP = $BO_DATA/tmp/<ID> e o soquete unix do provider
    # Terraform não cabe nos 104 caracteres do macOS com caminho longo
    data_root = runner.overlay(C.data(), C.tmp() / "d", mid)
    if rehearsal:
        opened = {"bundle": calib_bundle(slice_), "ciphertext_sha256": None, "plaintext_sha256": None,
                  "plaintext_bytes": None, "n_items": None}
    else:
        opened = unseal.open_slice(slice_, decrypt_argv=decrypt_argv, root=root)
    counts = materialize.materialize(slice_, opened["bundle"], frozen_repo)
    out = rdir / "out"
    cmds = collect.commands(slice_, runner.catalog_gates(mid), frozen_repo, out)
    res = runner.run_commands(cmds, frozen_repo, data_root, mid, rdir / "logs",
                              tmp_root=data_root / "tmp" / mid if slice_ == "sto" else None)
    ev = collect.collect(slice_, opened["bundle"], frozen_repo, data_root, res, rdir / "logs", out=out)
    del opened["bundle"]
    return {"slice": slice_, "module": mid, "commands": res, "materialized": counts,
            "seal": {k: opened[k] for k in ("ciphertext_sha256", "plaintext_sha256", "plaintext_bytes", "n_items")},
            "evidence": ev, "seconds": round(time.monotonic() - t0, 1)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.pilot_exit.heldout_run")
    ap.add_argument("--slices", default="sto,net")
    ap.add_argument("--reproduce", action="store_true")
    ap.add_argument("--verify-only", action="store_true", help="nunca executa: só confere o registro (gate do módulo)")
    ap.add_argument("--rehearsal", action="store_true",
                    help="ensaio na CALIBRAÇÃO pública (sem decifrar, sem tentativa, nada gravado fora de $BO_TMP)")
    ap.add_argument("--keep-workdir", action="store_true", help="não apaga $BO_TMP/run (só para depurar o avaliador)")
    ap.add_argument("ids", nargs="*")
    a = ap.parse_args(argv)
    root = C.repo()
    slices = [x for x in a.slices.split(",") if x]
    if sorted(slices) != ["net", "sto"]:
        C.say("heldout_run: o critério pede as duas fatias (sto,net)")
        return 2
    import yaml
    crit_p = root / "prereg" / "pilot_exit.yaml"
    crit = yaml.safe_load(crit_p.read_text(encoding="utf-8"))
    ids, seals = {}, {}
    for s in slices:
        try:
            ids[s] = frozen.identify(s, root)
            seals[s] = unseal.check_envelope(s, root)
        except (frozen.FrozenError, unseal.SealError) as e:
            C.say(f"heldout_run: {s}: {e}")
            return 2
        if not ids[s]["match"]:
            C.say(f"heldout_run: {s}: código avaliado ≠ código congelado do {ids[s]['module']}: "
                  + "; ".join(ids[s]["problems"]) + " (V1: pare e relate)")
            return 2
    key = key_of(ids, seals)
    if a.rehearsal:
        workdir = C.tmp() / "rehearsal"
        out = {}
        for s in slices:
            out[s] = run_slice(s, ids[s], root, workdir, rehearsal=True)
            C.say(f"heldout_run --rehearsal: {s}: saídas {[c['rc'] for c in out[s]['commands']]}, {out[s]['seconds']} s")
            C.write_json(workdir / f"{s}_evidence.json", out[s]["evidence"])
        shutil.rmtree(C.tmp() / "d", ignore_errors=True)
        shutil.rmtree(C.tmp() / "t", ignore_errors=True)
        C.say(f"heldout_run --rehearsal: evidência do ensaio em {C.portable(workdir)} (não é tentativa)")
        return 0
    rec = C.read_json(record_path(root))
    if rec and rec.get("key") == key and not a.reproduce:
        errs = verify_existing(rec, ids, seals)
        for e in errs:
            C.say("heldout_run: " + e)
        if not errs:
            C.say(f"heldout_run: execução registrada confere (tentativa {rec['attempt']}, código sto "
                  f"{ids['sto']['code_sha256'][:12]} net {ids['net']['code_sha256'][:12]}); nada decifrado de novo")
        return 1 if errs else 0
    if a.verify_only:
        C.say("heldout_run: nenhuma execução registrada para este código congelado e este selo" if not rec or
              rec.get("key") != key else "heldout_run: --verify-only com --reproduce não executa")
        return 1
    # Limite de tentativas POR conjunto retido (PREREG, ciclo v4, 3b3d4cb): um conjunto novo abre ciclo novo.
    # Linha antiga sem 'seals' pertence ao primeiro conjunto (selos STO 572f1333…, NET 99f53463…).
    seal_now = {s: seals[s]["ciphertext_sha256"] for s in slices}
    first_set = {"sto": "572f133361bc21d79ae225ba98c42d3f7fa5eba0b6a472c6292264ea735a8ce0",
                 "net": "99f53463cbeaeb38b5206344bef56b467c362d359ba85b6c5da58f7190816c29"}
    attempts = load_attempts()
    lineage = {s: seal_lineage(s, root) for s in slices}
    keys, keys_all = [], []
    for x in attempts:
        if x["key"] not in keys_all:
            keys_all.append(x["key"])
        xs = x.get("seals") or first_set
        if all(xs.get(s) in lineage[s] for s in slices) and x["key"] not in keys:
            keys.append(x["key"])
    attempt = keys.index(key) + 1 if key in keys else len(keys) + 1
    attempt_global = keys_all.index(key) + 1 if key in keys_all else len(keys_all) + 1
    kind = "reproduction" if key in keys else "attempt"
    if attempt > int(crit.get("attempts_max", 2)):
        C.say(f"heldout_run: tentativa {attempt} neste conjunto retido > {crit.get('attempts_max')} (E8): "
              "a expansão fica bloqueada; nada roda")
        return 1
    started = C.now()
    workdir = C.tmp() / "run"
    out = {}
    try:
        for s in slices:
            C.say(f"heldout_run: {s}: rodando {ids[s]['module']} congelado ({ids[s]['code_sha256'][:12]}) nas retidas")
            out[s] = run_slice(s, ids[s], root, workdir)
            rcs = [c["rc"] for c in out[s]["commands"]]
            C.say(f"heldout_run: {s}: {len(rcs)} comando(s), saídas {rcs}, {out[s]['seconds']} s")
    except (frozen.FrozenError, unseal.SealError, collect.CollectError) as e:
        C.say(f"heldout_run: falhou: {e}")
        return 2
    finally:
        if not a.keep_workdir:
            for d in (workdir, C.tmp() / "t", C.tmp() / "d"):   # t, d = BO_TMP e BO_DATA do código avaliado
                if d.exists():
                    shutil.rmtree(d, ignore_errors=True)
    stage = C.staging_dir() / "heldout"
    evid = {}
    for s in slices:
        p = stage / s / "evidence.json"
        C.write_json(p, out[s]["evidence"])
        evid[s] = {"path": f"$BO_DATA/{C.MODULE}/heldout/{s}/evidence.json", "sha256": C.sha_file(p)}
    finished = C.now()
    row = {"key": key, "kind": kind, "attempt": attempt, "attempt_global": attempt_global, "seals": seal_now,
           "started_at": started, "finished_at": finished,
           "code": {s: ids[s]["code_sha256"] for s in slices}}
    prev = attempts                      # lido ANTES de gravar a evidência no .staging (senão o livro some)
    ap_ = stage / "attempts.jsonl"
    ap_.parent.mkdir(parents=True, exist_ok=True)
    ap_.write_text("".join(C.canon(x).decode() + "\n" for x in prev + [row]), encoding="utf-8")
    record = {"schema": "bo.pilot_exit.heldout_run/1", "module": C.MODULE, "status": "COMPLETE", "key": key,
              "attempt": attempt, "attempt_global": attempt_global, "attempt_scope": "por conjunto retido (PREREG ciclo v4)",
              "kind": kind, "started_at": started, "finished_at": finished,
              "criteria": {"path": "$BO_REPO/prereg/pilot_exit.yaml", "sha256": C.sha_file(crit_p)},
              "decryption": {"where": "VM Oracle do Breno (D15), pipe ssh; chave privada nunca saiu de lá",
                             "command": C.REMOTE_DECRYPT},
              "frozen_code": ids, "seal": {s: dict(seals[s], **out[s]["seal"]) for s in slices},
              "runs": {s: {k: out[s][k] for k in ("module", "commands", "materialized", "seconds")} for s in slices},
              "evidence": evid,
              "isolation": "cópia congelada em $BO_TMP/run; BO_DATA sobreposto; sandbox-exec sem escrita fora de "
                           "$BO_TMP e sem rede; árvore apagada no fim (texto claro nunca gravado fora dela)"}
    C.write_json(record_path(root), record)
    C.say(f"heldout_run: tentativa {attempt} neste conjunto retido (global {attempt_global}, {kind}) gravada em "
          f"{C.portable(record_path(root))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
