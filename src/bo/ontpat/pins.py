"""Versões fixadas da cadeia de ferramentas e regimes de entailment declarados (S3).

  python -I -m bo.ontpat.pins --write   grava ontology/patterns/toolchain_pins.json a partir do que está instalado
  python -I -m bo.ontpat.pins --check   confere que o ambiente bate com o arquivo (sha do jar, versões embutidas,
                                        Java, pacotes Python, sha das ontologias candidatas e do PROV-O)

As versões do HermiT, do ELK e do OWLAPI são lidas dos pom.properties DENTRO do robot.jar (leitura do zip,
sem executar nada); é o HermiT e o ELK que o ROBOT fixado usa.
"""

from __future__ import annotations

import importlib.metadata as md
import re
import subprocess
import sys
import zipfile
from pathlib import Path

from . import common as c

ROBOT_VERSION = "1.9.11"
ROBOT_URL = f"https://github.com/ontodev/robot/releases/download/v{ROBOT_VERSION}/robot.jar"
JAR = c.data_dir() / "downloads" / "robot" / f"v{ROBOT_VERSION}" / "robot.jar"
JAVA = "/opt/homebrew/opt/openjdk@17/bin/java"
EMBEDDED = {
    "hermit": "net.sourceforge.owlapi/org.semanticweb.hermit",
    "elk": "io.github.liveontologies/elk-reasoner",
    "owlapi": "net.sourceforge.owlapi/owlapi-api",
    "robot_core": "org.obolibrary.robot/robot-core",
}
EXTERNAL = {
    "bfo": ("bfo2020/bfo-core.ttl", "https://raw.githubusercontent.com/BFO-ontology/BFO-2020/release-2024-01-29/src/owl/bfo-core.ttl"),
    "dul": ("dul/DUL.ttl", "http://www.ontologydesignpatterns.org/ont/dul/DUL.owl"),
    "gufo": ("gufo/gufo.ttl", "https://raw.githubusercontent.com/nemo-ufes/gufo/v1.0.0/gufo.ttl"),
    "prov_o": ("prov-o/prov-o.ttl", "https://www.w3.org/ns/prov-o"),
}
PY_PKGS = ("rdflib", "pyshacl", "owlrl")

REGIMES = {
    "owl": "OWL 2 Direct Semantics (OWL 2 DL), checado sobre o fecho de imports pelo ROBOT validate-profile; "
           "raciocínio completo com o HermiT embutido no ROBOT; ELK só sobre o fragmento EL extraído e verificado "
           "(AXIOMS), nunca sobre o fecho inteiro.",
    "sparql": "Consultas SPARQL 1.1 com entailment SIMPLES sobre o grafo materializado: triplas asseridas + tipos "
              "inferidos pelo HermiT para indivíduos nomeados (e sameAs inferido). Não é o regime OWL 2 Direct "
              "Semantics do SPARQL 1.1 Entailment Regimes; o que não foi materializado não é visto. Desigualdade "
              "de IRIs em FILTER só vale para valores declarados distintos (owl:AllDifferent).",
    "shacl": "SHACL Core + SPARQL (pyshacl, inference=none) sobre o grafo de dados tal como dado: só a travessia de "
             "rdfs:subClassOf do próprio SHACL. O ABox validado já traz os tipos bo: materializados e o contexto "
             "TBox de que as formas dependem.",
    "unique_name": "Sem suposição de nomes únicos: igualdade só por owl:hasKey/funcionalidade, diferença só por "
                   "axioma (AllDifferent, irreflexividade, valores funcionais distintos).",
    "closed_world": "Mundo aberto. Negação e ausência só pelo vocabulário de ausência (bo:Absent sob bo:CompleteRead); "
                    "o avaliador devolve UNKNOWN quando nem a afirmação nem a negação são consequência.",
}


def embedded_versions(jar: Path) -> dict:
    out = {}
    with zipfile.ZipFile(jar) as z:
        for k, art in EMBEDDED.items():
            txt = z.read(f"META-INF/maven/{art}/pom.properties").decode("utf-8")
            m = re.search(r"^version=(.+)$", txt, re.M)
            out[k] = m.group(1).strip() if m else None
    return out


def java_version() -> str:
    r = subprocess.run([JAVA, "-version"], capture_output=True, text=True, timeout=60)
    first = (r.stderr or r.stdout).splitlines()[0]
    return first.strip()


def build() -> dict:
    emb = embedded_versions(JAR)
    ext = {}
    for k, (rel, url) in EXTERNAL.items():
        p = c.data_dir() / "downloads" / rel
        ext[k] = {"path": f"$BO_DATA/downloads/{rel}", "url": url, "sha256": c.sha256_file(p)}
    return {
        "schema": "bo.toolchain_pins/1",
        "module": "ONTPAT",
        "written_at": c.now(),
        "robot": {"version": ROBOT_VERSION, "url": ROBOT_URL, "jar_path": f"$BO_DATA/downloads/robot/v{ROBOT_VERSION}/robot.jar", "jar_sha256": c.sha256_file(JAR),
                  "launcher": "~/.local/bin/robot (java -jar do jar acima)", "decision": "D6"},
        "hermit": {"version": emb["hermit"], "source": "embutido no robot.jar"},
        "elk": {"version": emb["elk"], "source": "embutido no robot.jar"},
        "owlapi": {"version": emb["owlapi"], "source": "embutido no robot.jar"},
        "robot_core": {"version": emb["robot_core"]},
        "java": {"path": JAVA, "version": java_version()},
        "python": {k: md.version(k) for k in PY_PKGS},
        "profile": "OWL 2 DL sobre o fecho de imports",
        "entailment_regimes": REGIMES,
        "external_ontologies": ext,
    }


def check(cur: dict, want: dict) -> list[str]:
    bad = []
    for path in (("robot", "version"), ("robot", "jar_sha256"), ("hermit", "version"), ("elk", "version"),
                 ("owlapi", "version"), ("java", "version")):
        a, b = cur, want
        for k in path:
            a, b = a.get(k, {}), b.get(k, {})
        if a != b:
            bad.append(f"{'.'.join(path)}: instalado {a!r}, fixado {b!r}")
    for k, v in want.get("python", {}).items():
        if cur["python"].get(k) != v:
            bad.append(f"python {k}: instalado {cur['python'].get(k)}, fixado {v}")
    for k, v in want.get("external_ontologies", {}).items():
        if cur["external_ontologies"].get(k, {}).get("sha256") != v["sha256"]:
            bad.append(f"ontologia externa {k} mudou (sha256)")
    return bad


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    target = c.patterns_dir() / "toolchain_pins.json"
    cur = build()
    if "--write" in argv:
        c.write_json(target, cur)
        c.emit(f"escrito {target}")
        return 0
    want = c.read_json(target)
    bad = check(cur, want)
    for b in bad:
        c.emit("PIN DIVERGE: " + b)
    if not bad:
        c.emit(f"pins conferem: ROBOT {want['robot']['version']}, HermiT {want['hermit']['version']}, "
               f"ELK {want['elk']['version']}, OWLAPI {want['owlapi']['version']}, {want['java']['version']}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
