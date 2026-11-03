"""Extração dos pontos finais: cada patch de uma composição de topo vira um ou mais pontos finais
(campo do XR de topo -> campo do MR), atravessando XRs aninhados pelas composições das configurações de que o
topo depende. Nada é executado; só leitura dos YAML exportados."""
from __future__ import annotations

from pathlib import Path

from . import compose, sources
from .compose import join_path, split_path
from .schema import ProviderIndex, classify_mr_path, classify_xr_path, tf_bridge, value_type, walk_schema

MAX_DEPTH = 4


def load_corpus(root: Path) -> dict:
    """{'xrds': {(group, kind): {...}}, 'compositions': [...]} de todas as fontes exportadas."""
    xrds, comps, unread = {}, [], []
    for s in sources.COMPOSITION_SOURCES:
        for f in s["files"]:
            p = root / "compositions" / s["id"] / f
            parsed = compose.parse_file(p.read_text(encoding="utf-8"))
            for x in parsed["xrds"]:
                x = dict(x, source=s["id"], file=f)
                xrds[(x["group"], x["kind"])] = x
            for c in parsed["compositions"]:
                c = dict(c, source=s["id"], file=f, role=s["role"])
                comps.append(c)
                unread.extend({"source": s["id"], "file": f, "composition": c["name"], **u}
                              for u in c["unread_steps"])
    return {"xrds": xrds, "compositions": comps, "unread_steps": unread}


def _rel(a: str, b: str):
    """Relação de caminhos: igual, a é prefixo de b, ou b é prefixo de a (por segmento)."""
    sa, sb = split_path(a), split_path(b)
    if sa == sb:
        return "eq", []
    if len(sa) < len(sb) and sb[:len(sa)] == sa:
        return "a_prefix", sb[len(sa):]
    if len(sb) < len(sa) and sa[:len(sb)] == sb:
        return "b_prefix", sa[len(sb):]
    return None, None


class Extractor:
    def __init__(self, root: Path):
        self.root = root
        self.corpus = load_corpus(root)
        self.prov = ProviderIndex(root)
        self.by_xr = {}
        for c in self.corpus["compositions"]:
            self.by_xr.setdefault((c["xr"]["group"], c["xr"]["kind"]), []).append(c)

    # ------------------------------------------------------------------------------------- resolução
    def xr_resolve(self, group, version, kind, path) -> dict:
        cat = classify_xr_path(path)
        if cat != "xr_field":
            return {"status": "runtime", "category": cat, "reason": "campo de máquina do Crossplane no XR"}
        x = self.corpus["xrds"].get((group, kind))
        if x is None:
            return {"status": "unresolved", "category": cat, "reason": "XRD ausente nas fontes"}
        sch = x["versions"].get(version)
        if sch is None:
            return {"status": "unresolved", "category": cat, "reason": f"versão {version} ausente no XRD"}
        ok, node, why = walk_schema(sch, split_path(path))
        r = {"status": "resolved" if ok else "unresolved", "category": cat, "reason": why,
             "xrd": f"{x['source']}:{x['file']}"}
        if ok:
            r["value_type"] = value_type(node)
        return r

    def mr_resolve(self, pin, group, version, kind, path) -> dict:
        cat = classify_mr_path(path)
        out = {"category": cat}
        if pin is None:
            out.update(status="unresolved", reason="sem provider fixado para a família de API", bridge={
                "status": "unresolved", "reason": "sem provider fixado"})
            return out
        repo, tag = pin
        segs = split_path(path)
        if cat in ("external_name", "runtime"):
            out.update(status="runtime", reason="campo de máquina do Crossplane (metadata/spec de controle)")
        else:
            sch, crd = self.prov.crd_schema(repo, tag, group, version, kind)
            if sch is None:
                out.update(status="unresolved", reason=f"CRD de {group}/{version} {kind} ausente em {repo}@{tag}")
            else:
                ok, node, why = walk_schema(sch, segs)
                out.update(status="resolved" if ok else "unresolved", reason=why, crd=crd)
                if ok:
                    out["value_type"] = value_type(node)
        if cat in ("param", "observed"):
            out["bridge"] = tf_bridge(self.prov.go(repo, tag, group, version, kind), kind, segs)
        elif cat == "external_name":
            out["bridge"] = {"status": "unresolved",
                             "reason": "external-name: identidade externa; o atributo Terraform depende da "
                                       "configuração de nome do provider"}
        else:
            out["bridge"] = {"status": "unresolved", "reason": f"categoria {cat} não é atributo do provider"}
        out["pin"] = f"{repo}@{tag}"
        return out

    # ------------------------------------------------------------------------------------- pontos finais
    def endpoints(self) -> list[dict]:
        out = []
        for c in self.corpus["compositions"]:
            if c["role"] != "top":
                continue
            src = sources.source_by_id(c["source"])
            for r in c["resources"]:
                for p in r["patches"]:
                    if p["status"] != "ok":
                        continue
                    hop = self._hop(c, r, p)
                    for e in self._follow(src, r["mr"], p, [hop], depth=0):
                        e.update(top_source=c["source"], top_file=c["file"], composition=c["name"],
                                 xr=dict(c["xr"]), top_condition=r.get("condition"),
                                 top_resource=r["resource_name"])
                        out.append(e)
        return out

    @staticmethod
    def _hop(c, r, p):
        return {"source": c["source"], "file": c["file"], "composition": c["name"], "resource": r["resource_name"],
                "condition": r.get("condition"), "line": p.get("line"), "type": p["type"],
                "from": p.get("from_field_path") or p.get("from_field_paths"), "to": p.get("to_field_path"),
                "transforms": p.get("transforms") or [], "combine": p.get("combine"),
                "patch_set": p.get("patch_set"), "mr": dict(r["mr"])}

    def _follow(self, src, mr, p, trail, depth):
        """Patch p (no recurso mr) -> pontos finais. Se mr é um XR aninhado, segue pelas composições dele."""
        direction = compose.XR_SIDE[p["type"]]
        combine = p["type"].startswith("Combine")
        if direction == "to_mr":
            xr_paths = p.get("from_field_paths") if combine else [p.get("from_field_path")]
            mr_paths = [p.get("to_field_path")]
        else:
            mr_paths = p.get("from_field_paths") if combine else [p.get("from_field_path")]
            xr_paths = [p.get("to_field_path")]
        if any(x is None for x in xr_paths + mr_paths):
            return []
        nested = self.by_xr.get((mr["group"], mr["kind"]))
        if nested and (mr["group"], mr["kind"]) in self.corpus["xrds"]:
            if depth >= MAX_DEPTH or combine and direction == "to_xr":
                return [self._dead(src, mr, p, trail, xr_paths, mr_paths, direction, "profundidade/combinação")]
            res = []
            for nc in nested:
                nsrc = sources.source_by_id(nc["source"])
                for nr in nc["resources"]:
                    for np_ in nr["patches"]:
                        if np_["status"] != "ok" or compose.XR_SIDE[np_["type"]] != direction:
                            continue
                        res.extend(self._link(src, nsrc, mr, nc, nr, np_, p, trail, direction, depth,
                                              xr_paths, mr_paths, combine))
            if not res:
                return [self._dead(src, mr, p, trail, xr_paths, mr_paths, direction,
                                   "nenhum patch da composição aninhada lê/escreve este campo")]
            return res
        fam_provider, fam = sources.api_family(mr["group"])
        pin = src["provider_pins"].get(fam) if fam else None
        out = []
        for mp in mr_paths:
            out.append({"direction": direction, "xr_paths": xr_paths, "mr_path": mp, "mr": dict(mr),
                        "provider": fam_provider, "family": fam, "trail": trail, "combine": combine,
                        "combine_mr_paths": mr_paths if combine and direction == "to_xr" else None,
                        "mr_resolution": self.mr_resolve(pin, mr["group"], mr["version"], mr["kind"], mp),
                        "nested_status": "ok"})
        return out

    def _link(self, src, nsrc, mr, nc, nr, np_, p, trail, direction, depth, xr_paths, mr_paths, combine):
        """Liga o patch de topo p (que escreve/lê o campo T do XR aninhado) a um patch np_ da composição dele.
        Devolve os pontos finais do patch sintético resultante (caminho do XR de topo -> caminho no recurso
        da composição aninhada)."""
        ncombine = np_["type"].startswith("Combine")
        comb = combine or ncombine
        if direction == "to_mr":
            T = mr_paths[0]
            n_from = np_.get("from_field_paths") if ncombine else [np_.get("from_field_path")]
            new_from, new_to = None, None
            for F in n_from:
                rel, tail = _rel(T, F) if F else (None, None)
                if rel == "eq":
                    new_from, new_to = list(xr_paths), np_.get("to_field_path")
                elif rel == "a_prefix" and not combine:       # o aninhado lê um subcampo do que o topo escreveu
                    new_from, new_to = [join_path(split_path(xr_paths[0]) + tail)], np_.get("to_field_path")
                elif rel == "b_prefix" and not ncombine:      # o aninhado lê um pai: o valor desce no destino
                    new_from, new_to = list(xr_paths), join_path(split_path(np_.get("to_field_path")) + tail)
                if new_from:
                    break
            if not new_from or not new_to:
                return []
            new = {"type": "CombineFromComposite" if comb else "FromCompositeFieldPath",
                   "from_field_paths": new_from, "from_field_path": new_from[0], "to_field_path": new_to}
        else:
            if combine:
                return []
            S, X = xr_paths[0], p.get("to_field_path")
            n_to = np_.get("to_field_path")
            rel, tail = _rel(S, n_to) if n_to else (None, None)
            n_from = np_.get("from_field_paths") if ncombine else [np_.get("from_field_path")]
            if rel == "eq":
                new_from, new_to = n_from, X
            elif rel == "a_prefix":       # o topo lê um pai do que o aninhado escreveu
                new_from, new_to = n_from, join_path(split_path(X) + tail)
            elif rel == "b_prefix" and not ncombine:   # o topo lê um subcampo do que o aninhado escreveu
                new_from, new_to = [join_path(split_path(n_from[0]) + tail)], X
            else:
                return []
            if any(f is None for f in new_from):
                return []
            new = {"type": "CombineToComposite" if ncombine else "ToCompositeFieldPath",
                   "from_field_paths": new_from, "from_field_path": new_from[0], "to_field_path": new_to}
        hop = self._hop(nc, nr, np_)
        hop["nested_link"] = {"nested_field": mr_paths[0] if direction == "to_mr" else xr_paths[0],
                              "nested_xr": f"{mr['group']}/{mr['kind']}"}
        return self._follow(nsrc, nr["mr"], new, trail + [hop], depth + 1)

    def _dead(self, src, mr, p, trail, xr_paths, mr_paths, direction, why):
        return {"direction": direction, "xr_paths": xr_paths, "mr_path": mr_paths[0], "mr": dict(mr),
                "provider": None, "family": "nested-xr", "trail": trail, "combine": p["type"].startswith("Combine"),
                "combine_mr_paths": None,
                "mr_resolution": {"category": "nested_dead_end", "status": "unresolved", "reason": why,
                                  "bridge": {"status": "unresolved", "reason": "XR aninhado sem continuação"}},
                "nested_status": "dead_end"}
