"""Gate G2 do LIT: toda linha da matriz tem fonte verificada; Kalinin marcado artigo=publicado e
artefato=indisponível, descrito como está.

  python -I -m bo.lit.matrix_check [CSV] [--bib ARQ] [--html ARQ] [--ledger ARQ]

Confere:
- cabeçalho igual ao contrato (data.COLUMNS), nenhuma célula vazia, valores dentro dos conjuntos fechados;
- cada linha cita entradas que existem no .bib e passam no check_ids; a coluna source é um identificador
  dessas entradas, verificado no livro de resolução;
- cobertura: todo trabalho exigido pelo brief do LIT tem linha;
- Kalinin: artigo publicado, artefato indisponível, referência PRIA 36(2):558-567 e DOI iguais no .bib, no
  Crossref e na matriz; provedores AWS, Azure, GCP, Yandex Cloud e Cloud.ru; a descrição cita a implementação
  (OWL DL, owlready2, ABox, CSPM em SQL/SPARQL, SWRL, HermiT) e só falta avaliação quantitativa e artefato
  inspecionável; saem Yandex e Cloud.ru e entra OCI; nenhuma frase de "não publicado" em lugar nenhum;
- WebMedia 2025 em terceira pessoa (linha e seção do RELATED_WORK.html);
- o RELATED_WORK.html tem uma linha para cada linha da matriz.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from bo.repo import core

from . import bib, data, ids, verify

# trabalhos exigidos pelo brief: rótulo -> chaves do .bib (todas têm de estar em alguma linha)
REQUIRED = {
    "Kalinin & Skvortsov 2026": ["kalinin2026unified"],
    "CPG": ["banse2021cpg"],
    "Cartography": ["cartography2026ontology"],
    "Fix": ["fixinventory2025"],
    "CertGraph": ["schoberl2024certgraph"],
    "DevOps-Infra": ["corcho2021devopsinfra"],
    "mOSAIC / Moscato 2011": ["moscato2011mosaic"],
    "Cloud Services Ontology / Di Martino 2014": ["dimartino2014openstack"],
    "CoCoOn": ["zhang2012cocoon", "zhang2019cocoon"],
    "TOSCA / EDMM": ["oasis2025tosca", "wurster2020edmm"],
    "DMTF CIMI": ["dmtf2016cimi"],
    "OCSF": ["ocsf2026schema"],
    "SSSOM": ["matentzoglu2022sssom"],
    "EDOAL": ["david2011alignapi"],
    "ECO": ["giglio2019eco"],
    "Zodiac": ["qiu2024zodiac"],
    "TerraMod": ["gupta2026terramod"],
    "KGSecConfig": ["ulhaque2022kgsecconfig"],
    "CNOnt": ["kosinska2023cnont"],
    "Haller & Polleres": ["haller2020oneontology"],
    "BFO": ["arp2015bfo"],
    "DOLCE": ["borgo2022dolce"],
    "gUFO": ["gufo2026"],
    "WebMedia 2025": ["paulo2025webmedia"],
}
ANSWERS = {"R4-W1", "R4-W6", "R1-M6", "V1", "S12"}
FIRST_PERSON = re.compile(r"\b(nosso|nossa|nossos|nossas|nós|our|ours|we|us|my|meu|minha|meus|minhas)\b", re.I)


def html_section(text: str, sec_id: str) -> str:
    m = re.search(r'<h2 id="' + re.escape(sec_id) + r'">(.*?)(?=<h2 |</main>)', text, flags=re.S)
    return m.group(1) if m else ""


def plain(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def check(csv_path: Path, bib_path: Path, html_path: Path, led_path: Path) -> list[str]:
    errs: list[str] = []
    E = errs.append
    entries = {e["key"]: e for e in bib.parse(bib_path.read_text(encoding="utf-8"))}
    ledger = json.loads(led_path.read_text(encoding="utf-8"))
    verdicts = {k: verify.check_entry(e, ledger) for k, e in entries.items()}
    html_text = html_path.read_text(encoding="utf-8")

    with open(csv_path, encoding="utf-8", newline="") as fh:
        rd = csv.DictReader(fh)
        header = rd.fieldnames or []
        rows = list(rd)
    if header != data.COLUMNS:
        E(f"cabeçalho difere do contrato: faltam {sorted(set(data.COLUMNS) - set(header))}, "
          f"sobram {sorted(set(header) - set(data.COLUMNS))}")
        return errs
    if not rows:
        E("matriz sem linhas")
        return errs

    seen, covered, answered = set(), set(), set()
    for n, r in enumerate(rows, 2):
        rid = r["row_id"] or f"linha {n}"
        if rid in seen:
            E(f"{rid}: row_id repetido")
        seen.add(rid)
        for c in data.COLUMNS:
            if not (r.get(c) or "").strip():
                E(f"{rid}: coluna {c} vazia")
        for c, allowed in data.ENUMS.items():
            if r.get(c) and r[c] not in allowed:
                E(f"{rid}: {c}={r[c]!r} fora de {sorted(allowed)}")
        axes = [x for x in (r.get("comparison_axes") or "").split(";") if x]
        if not axes or any(x not in data.AXES for x in axes) or ("NOT_APPLICABLE" in axes and len(axes) > 1):
            E(f"{rid}: comparison_axes inválido: {r.get('comparison_axes')!r}")
        keys = [k for k in (r.get("bibkeys") or "").split(";") if k]
        row_ids: set[str] = set()
        verified: set[str] = set()
        for k in keys:
            if k not in entries:
                E(f"{rid}: bibkey {k} não existe no .bib")
                continue
            vd = verdicts[k]
            if not vd.ok:
                E(f"{rid}: entrada {k} não passa no check_ids: {'; '.join(vd.problems)[:200]}")
            row_ids |= verify.entry_ids(entries[k])
            verified |= set(vd.verified_ids)
            covered.add(k)
        src = (r.get("source") or "").strip()
        scheme, sep, val = src.partition(":")
        if not sep or scheme not in ({"doi"} | ids.ALT_SCHEMES):
            E(f"{rid}: source sem esquema conhecido: {src!r}")
        else:
            sk = ids.id_key(scheme, val)
            if sk not in row_ids:
                E(f"{rid}: source {src[:80]!r} não é identificador das entradas da linha ({';'.join(keys)})")
            elif sk not in verified:
                E(f"{rid}: source {src[:80]!r} não está verificado no livro de resolução")
        if r.get("artifact_status") == "disponivel" and r.get("artifact_ref") == "NOT_APPLICABLE":
            E(f"{rid}: artefato disponível sem artifact_ref")
        if r.get("artifact_status") in ("indisponivel", "nao_localizado", "nao_se_aplica") \
                and r.get("artifact_ref") != "NOT_APPLICABLE":
            E(f"{rid}: artifact_ref preenchido com artefato {r['artifact_status']}")
        if r.get("article_status") == "publicado" and not any(
                entries.get(k, {}).get("fields", {}).get("doi") or entries.get(k, {}).get("fields", {}).get("isbn")
                for k in keys):
            E(f"{rid}: article_status=publicado sem DOI nem ISBN nas entradas")
        if f'id="row-{rid}"' not in html_text:
            E(f"{rid}: linha ausente no RELATED_WORK.html")
        answered |= {x for x in (r.get("answers") or "").split(";") if x}

    for label, keys in REQUIRED.items():
        miss = [k for k in keys if k not in covered]
        if miss:
            E(f"trabalho exigido sem linha na matriz: {label} ({', '.join(miss)})")
    if ANSWERS - answered:
        E(f"objeções do brief sem linha que responda: {sorted(ANSWERS - answered)}")

    # --- Kalinin descrito como está
    K = data.KALININ
    krows = [r for r in rows if K["bibkey"] in (r.get("bibkeys") or "").split(";")]
    if len(krows) != 1:
        E(f"Kalinin: esperada 1 linha, achadas {len(krows)}")
    else:
        kr = krows[0]
        if kr["article_status"] != "publicado":
            E(f"Kalinin: article_status={kr['article_status']!r}, devia ser 'publicado'")
        if kr["artifact_status"] != "indisponivel":
            E(f"Kalinin: artifact_status={kr['artifact_status']!r}, devia ser 'indisponivel'")
        if kr["source"] != "doi:" + K["doi"]:
            E(f"Kalinin: source devia ser doi:{K['doi']}")
        if set(kr["providers"].split(";")) != set(K["providers"]):
            E(f"Kalinin: provedores {kr['providers']!r} diferem de {';'.join(K['providers'])}")
        for t in K["implements"]:
            if t.lower() not in kr["what_it_does"].lower():
                E(f"Kalinin: what_it_does não cita {t!r}")
        for t in K["missing"]:
            if t.lower() not in kr["gap_or_limit"].lower():
                E(f"Kalinin: gap_or_limit não diz que falta {t!r}")
        mw = kr["what_we_must_show"]
        if not all(p in mw for p in K["leave"] + K["enter"]) or "saem" not in mw or "entra" not in mw:
            E("Kalinin: what_we_must_show não diz que saem Yandex Cloud e Cloud.ru e entra OCI")
    kb = entries.get(K["bibkey"])
    if not kb:
        E("Kalinin: entrada ausente no .bib")
    else:
        f = kb["fields"]
        for fld in ("journal", "volume", "number", "pages", "year"):
            if f.get(fld) != K[fld]:
                E(f"Kalinin: .bib {fld}={f.get(fld)!r}, devia ser {K[fld]!r}")
        if ids.norm_doi(f.get("doi", "")) != ids.norm_doi(K["doi"]):
            E("Kalinin: DOI do .bib difere")
        rec = ledger.get("records", {}).get(ids.id_key("doi", K["doi"]), {})
        if rec.get("status") != "ok" or rec.get("volume") != K["volume"] or rec.get("issue") != K["number"] \
                or (rec.get("page") or "").replace("–", "-") != K["pages"].replace("--", "-") \
                or int(K["year"]) not in rec.get("years", []):
            E("Kalinin: registro do Crossref não confirma PRIA 36(2):558-567, 2026")
    ksec = plain(html_section(html_text, "kalinin"))
    if not ksec:
        E("RELATED_WORK.html sem a seção id=kalinin")
    else:
        for t in ["publicado", "indisponível", K["doi"]] + K["implements"] + K["missing"] + K["providers"] + K["enter"]:
            if t.lower() not in ksec.lower():
                E(f"RELATED_WORK.html, seção Kalinin, não contém {t!r}")
    corpus = {"positioning_matrix.csv": csv_path.read_text(encoding="utf-8"),
              "RELATED_WORK.html": plain(html_text), "related.bib": bib_path.read_text(encoding="utf-8")}
    for name, text in corpus.items():
        low = text.lower()
        for ph in K["forbidden"]:
            if ph.lower() in low:
                E(f"{name}: frase proibida sobre Kalinin ({ph!r})")

    # --- WebMedia 2025 em terceira pessoa
    wrows = [r for r in rows if "paulo2025webmedia" in (r.get("bibkeys") or "").split(";")]
    for r in wrows:
        for c in ("work", "what_it_does", "gap_or_limit", "what_we_must_show", "evidence_detail"):
            m = FIRST_PERSON.search(r[c])
            if m:
                E(f"WebMedia 2025: primeira pessoa ({m.group(0)!r}) na coluna {c}")
    wsec = plain(html_section(html_text, "webmedia2025"))
    if not wsec:
        E("RELATED_WORK.html sem a seção id=webmedia2025")
    else:
        m = FIRST_PERSON.search(wsec)
        if m:
            E(f"WebMedia 2025: primeira pessoa ({m.group(0)!r}) na seção do RELATED_WORK.html")
        if "terceira pessoa" not in wsec or "Paulo, Vasconcelos e Ferraz" not in wsec:
            E("WebMedia 2025: seção não cita os autores em terceira pessoa")
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -I -m bo.lit.matrix_check")
    ap.add_argument("csv", nargs="?", default=None)
    ap.add_argument("--bib", default=None)
    ap.add_argument("--html", default=None)
    ap.add_argument("--ledger", default=None)
    a = ap.parse_args(argv)
    root = ids.repo_root()
    paths = {
        "csv": Path(a.csv) if a.csv else root / "lit" / "positioning_matrix.csv",
        "bib": Path(a.bib) if a.bib else root / "lit" / "related.bib",
        "html": Path(a.html) if a.html else root / "lit" / "RELATED_WORK.html",
        "ledger": Path(a.ledger) if a.ledger else root / ids.LEDGER_REL,
    }
    for k, p in paths.items():
        if not p.is_file():
            raise core.BoError(f"{k} ausente: {p}")
    errs = check(paths["csv"], paths["bib"], paths["html"], paths["ledger"])
    for e in errs:
        core.emit(f"FALHA {e}")
    with open(paths["csv"], encoding="utf-8", newline="") as fh:
        n = sum(1 for _ in csv.DictReader(fh))
    core.emit(f"[{core.now()}] matriz: {n} linhas, {len(errs)} problema(s); Kalinin artigo=publicado, "
              f"artefato=indisponivel" + ("" if not errs else " (ver falhas)"))
    return 1 if errs else 0


if __name__ == "__main__":
    core.run_main(main)
