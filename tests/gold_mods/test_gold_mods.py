"""Testes do GOLD-MODS: leitura de termos, pares de variantes, linhas C09 e mutações que o gate de resolução pega."""
from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from bo.contracts import sssom as CSSSOM
from bo.gold_mods import build as B
from bo.gold_mods import resolve as R
from bo.gold_mods import scan as S
from bo.gold_mods import terms as T
from bo.gold_mods.paths import data_dir, results_dir, tmp_dir


def var(s):
    return {"kind": "symbol", "name_class": "variable", "scope": "repo", "symbol_id": s}


def lit(v, dt="string"):
    return {"kind": "literal", "datatype": dt, "value": v}


def ex(op, *a):
    return {"kind": "expression", "op": op, "args": list(a)}


class NormAttr(unittest.TestCase):
    def test_cases(self):
        cases = {
            "instance_type": ("attribute", "instance_type"),
            "ingress[0].from_port": ("attribute", "ingress.from_port"),
            'dynamic["ingress"][0].content.to_port': ("attribute", "ingress.to_port"),
            'node_config[0].dynamic["taint"][0].content.key': ("attribute", "node_config.taint.key"),
            'dynamic["ingress"][0].for_each': ("dynamic_iter", None),
            "count": ("meta", None),
            "lifecycle[0].ignore_changes": ("meta", None),
            "depends_on": ("meta", None),
            'tags["SYM-0123456789ab"]': ("unresolved", None),
            'dynamic["SYM-0123456789ab"][0].content.x': ("unresolved", None),
        }
        for path, want in cases.items():
            self.assertEqual(T.norm_attr(path), want, path)


class VarUses(unittest.TestCase):
    def test_direct_is_identity(self):
        self.assertEqual(T.var_uses(var("SYM-aaaaaaaaaaaa")), [("SYM-aaaaaaaaaaaa", ())])
        self.assertEqual(T.mode_of(()), "identity")

    def test_template_is_expr(self):
        t = ex("hcl_template", var("SYM-aaaaaaaaaaaa"), lit("-vpc"))
        self.assertEqual(T.var_uses(t), [("SYM-aaaaaaaaaaaa", ("hcl_template",))])
        self.assertEqual(T.mode_of(("hcl_template",)), "expr")

    def test_field_chain_is_pivot(self):
        f = {"kind": "symbol", "name_class": "unknown", "scope": "repo", "symbol_id": "SYM-bbbbbbbbbbbb"}
        t = ex("hcl_getattr", var("SYM-aaaaaaaaaaaa"), f)
        self.assertEqual(T.var_uses(t), [("SYM-aaaaaaaaaaaa.SYM-bbbbbbbbbbbb", ())])
        t2 = ex("hcl_index", var("SYM-aaaaaaaaaaaa"), lit(0, "number"))
        self.assertEqual(T.var_uses(t2), [("SYM-aaaaaaaaaaaa[0]", ())])

    def test_function_and_object(self):
        t = ex("lookup", var("SYM-aaaaaaaaaaaa"), lit("k"))
        self.assertEqual(T.var_uses(t), [("SYM-aaaaaaaaaaaa", ("lookup",))])
        t = ex("hcl_object", lit("Name"), var("SYM-cccccccccccc"))
        self.assertEqual(T.var_uses(t), [("SYM-cccccccccccc", ("hcl_object",))])

    def test_no_var(self):
        ref = {"kind": "reference", "target_type": "aws_vpc", "target_address": "aws_vpc.SYM-aaaaaaaaaaaa",
               "attribute": "id"}
        self.assertEqual(T.var_uses(ref), [])


class RepoScan(unittest.TestCase):
    def line(self, addr, rtype, apath, term, file="mods/aws/main.tf"):
        rec = {"attr_path": apath, "family_id": "F-0123456789ab", "file": file, "provider": "aws",
               "repo_id": "R-0123456789ab", "resource_address": addr, "resource_type": rtype, "term": term}
        return json.dumps(rec, sort_keys=True, separators=(",", ":")).encode()

    def test_resource_data_and_meta(self):
        v = var("SYM-aaaaaaaaaaaa")
        lines = [self.line("aws_instance.SYM-bbbbbbbbbbbb", "aws_instance", "instance_type", v),
                 self.line("data.aws_ami.SYM-cccccccccccc", "aws_ami", "filter[0].values", ex("hcl_tuple", v)),
                 self.line("module.SYM-dddddddddddd.aws_instance.SYM-bbbbbbbbbbbb", "aws_instance", "count",
                           ex("?:", v, lit(1, "number"), lit(0, "number"))),
                 self.line("aws_instance.SYM-bbbbbbbbbbbb", "aws_instance", "ami", lit("x"))]
        rid, fid, dirs, uses, atoms = S.repo_scan(lines)
        self.assertEqual((rid, fid), ("R-0123456789ab", "F-0123456789ab"))
        self.assertEqual(atoms, {"aws_instance:instance_type", "aws_instance:ami"})
        cats = sorted((u[5], u[6]) for u in uses["mods/aws"])
        self.assertEqual(cats, [("attribute", "instance_type"), ("data_source", None), ("meta", None)])
        self.assertEqual(dirs["mods/aws"]["vars"], {"SYM-aaaaaaaaaaaa"})
        self.assertEqual(dirs["mods/aws"]["n_records"], 4)


def _dirs(spec):
    """spec: {dir: (provider, {var: [(rtype, attr_path, mode)]})} -> (dirs, uses) como o repo_scan."""
    dirs, uses = {}, {}
    for d, (prov, vs) in spec.items():
        dirs[d] = {"providers": Counter({prov: 1}), "n_records": 1, "vars": set(vs)}
        uses[d] = []
        for v, feeds in vs.items():
            for rtype, apath, mode in feeds:
                cat, atom = T.norm_attr(apath)
                uses[d].append((v, prov, rtype, f"{rtype}.SYM-dddddddddddd", apath, cat, atom,
                                [] if mode == "identity" else ["hcl_template"], f"{d}/main.tf"))
    return dirs, uses


class Pairs(unittest.TestCase):
    def test_mutual_counterpart_by_prefix(self):
        iface = {"SYM-v1aaaaaaaaaa": [("aws_instance", "instance_type", "identity")],
                 "SYM-v2aaaaaaaaaa": [("aws_instance", "ami", "identity")]}
        giface = {"SYM-v1aaaaaaaaaa": [("google_compute_instance", "machine_type", "identity")],
                  "SYM-v2aaaaaaaaaa": [("google_compute_instance", "boot_disk.initialize_params.image", "identity")]}
        dirs, uses = _dirs({"x/aws": ("aws", iface), "x/gcp": ("google", giface),
                            "y/aws": ("aws", iface), "y/gcp": ("google", giface)})
        _v, mixed, pairs, n_cand = S.find_pairs(dirs, uses, 2, 0.5)
        self.assertEqual(n_cand, 4)       # V3 sozinho cruzaria x com y
        self.assertEqual(sorted((p["dir_a"], p["dir_b"]) for p in pairs), [("x/aws", "x/gcp"), ("y/aws", "y/gcp")])
        self.assertEqual(mixed, 0)

    def test_threshold_same_provider_and_mixed(self):
        dirs, uses = _dirs({"a": ("aws", {"SYM-v1aaaaaaaaaa": [("aws_s3_bucket", "bucket", "identity")],
                                          "SYM-v2aaaaaaaaaa": [("aws_s3_bucket", "acl", "identity")]}),
                            "b": ("aws", {"SYM-v1aaaaaaaaaa": [("aws_s3_bucket", "bucket", "identity")],
                                          "SYM-v2aaaaaaaaaa": [("aws_s3_bucket", "acl", "identity")]}),
                            "c": ("google", {"SYM-v1aaaaaaaaaa": [("google_storage_bucket", "name", "identity")],
                                             "SYM-v9aaaaaaaaaa": [("google_storage_bucket", "x", "identity")],
                                             "SYM-v8aaaaaaaaaa": [("google_storage_bucket", "y", "identity")]})})
        dirs["m"] = {"providers": Counter({"aws": 1, "google": 1}), "n_records": 2, "vars": {"SYM-v1aaaaaaaaaa"}}
        uses["m"] = []
        _v, mixed, pairs, _n = S.find_pairs(dirs, uses, 2, 0.5)
        self.assertEqual(pairs, [])       # a-b mesmo provedor; c compartilha 1 só variável; m misto
        self.assertEqual(mixed, 1)


def _repo(spec, rid="R-0123456789ab", fid="F-0123456789ab"):
    dirs, uses = _dirs(spec)
    variants, mixed, pairs, n = S.find_pairs(dirs, uses, 2, 0.5)
    comps = S.components(pairs)
    return {"repo_id": rid, "family_id": fid, "pairs": pairs, "families": comps, "n_threshold_pairs": n,
            "variants": {d: variants[d] for c in comps for d in c}, "multi_provider_variants": True}


class Rows(unittest.TestCase):
    def rows(self, spec, atom_fams=None):
        r = _repo(spec)
        d_acc, g_acc, traces, _ts, fams = B.collect([r], {r["repo_id"]: "MIT"})
        af = atom_fams if atom_fams is not None else Counter()
        if atom_fams is None:
            for a in list(d_acc.values()) + list(g_acc.values()):
                for x in a.sids + a.oids:
                    af[B.corpus_key(x)] = 5
        rows = [B.to_row(a, af) for a in d_acc.values()] + [B.to_row(a, af) for a in g_acc.values()]
        return {x["claim_id"]: x for x in rows}, traces, fams

    def validate(self, rows):
        tsv = CSSSOM.write_tsv(list(rows.values()), B.MAPPING_SET_ID, B.PREFIXES)
        d = tempfile.mkdtemp(dir=tmp_dir())
        try:
            p = Path(d) / "t.sssom.tsv"
            p.write_text(tsv, encoding="utf-8")
            from bo.contracts import validate as V
            return V.main(["correspondences", str(p)])
        finally:
            shutil.rmtree(d)

    def test_one_to_one_close_and_group_one_to_n(self):
        spec = {"m/aws": ("aws", {"SYM-v1aaaaaaaaaa": [("aws_instance", "instance_type", "identity")],
                                  "SYM-v2aaaaaaaaaa": [("aws_eks_node_group", "scaling_config.min_size", "identity")]}),
                "m/azure": ("azurerm", {"SYM-v1aaaaaaaaaa": [("azurerm_linux_virtual_machine", "size", "identity")],
                                        "SYM-v2aaaaaaaaaa": [("azurerm_kubernetes_cluster_node_pool", "min_count",
                                                              "identity"),
                                                             ("azurerm_kubernetes_cluster_node_pool", "node_count",
                                                              "identity")]})}
        rows, traces, fams = self.rows(spec)
        d = [r for r in rows.values() if r["claim_id"].startswith("MOD-D-")]
        g = [r for r in rows.values() if r["claim_id"].startswith("MOD-G-")]
        self.assertEqual(len(d), 1)
        self.assertEqual((d[0]["subject_id"], d[0]["object_id"], d[0]["semantic_relation"]),
                         ("aws:aws_instance:instance_type", "azurerm:azurerm_linux_virtual_machine:size", "close"))
        self.assertEqual(d[0]["translation_fn"], {"name": "identity", "params": {}})
        self.assertEqual(len(g), 1)
        self.assertEqual(g[0]["group"]["cardinality"], "1:N")
        self.assertEqual(len(g[0]["group"]["steps"]), 2)
        self.assertEqual(g[0]["evidence_state"], "STRUCTURALLY_VALID")
        self.assertEqual(len(fams), 1)
        self.assertEqual(len(traces), 2)
        self.assertEqual(self.validate(rows), 0)

    def test_nm_with_expression_unfolds_unresolved(self):
        spec = {"aws": ("aws", {"SYM-v1aaaaaaaaaa": [("aws_vpc", "tags", "expr"), ("aws_subnet", "tags", "expr")],
                                "SYM-v2aaaaaaaaaa": [("aws_vpc", "cidr_block", "identity")]}),
                "gcp": ("google", {"SYM-v1aaaaaaaaaa": [("google_compute_network", "name", "expr"),
                                                        ("google_compute_subnetwork", "name", "expr")],
                                   "SYM-v2aaaaaaaaaa": [("google_compute_subnetwork", "ip_cidr_range", "identity")]})}
        rows, _t, _f = self.rows(spec)
        nm = [r for r in rows.values() if "N:M" in (r.get("mapping_cardinality") or "")]
        self.assertEqual(len(nm), 4)
        for r in nm:
            self.assertEqual(r["semantic_relation"], "related")
            self.assertEqual(r["transport_fidelity"], "none")
            self.assertIsNone(r["translation_fn"])
            self.assertEqual(r["evidence_state"], "UNRESOLVED")
            self.assertIn("nm_unfolded", json.loads(r["other"])["unresolved_reasons"])
        self.assertEqual(self.validate(rows), 0)

    def test_unattested_atom_is_unresolved(self):
        spec = {"aws": ("aws", {"SYM-v1aaaaaaaaaa": [("aws_instance", "instance_tipe", "identity")],
                                "SYM-v2aaaaaaaaaa": [("aws_instance", "ami", "identity")]}),
                "gcp": ("google", {"SYM-v1aaaaaaaaaa": [("google_compute_instance", "machine_type", "identity")],
                                   "SYM-v2aaaaaaaaaa": [("google_compute_instance", "boot_disk.initialize_params.image",
                                                         "identity")]})}
        af = Counter({"aws_instance:instance_tipe": 1, "aws_instance:ami": 9,
                      "google_compute_instance:machine_type": 9,
                      "google_compute_instance:boot_disk.initialize_params.image": 9})
        rows, _t, _f = self.rows(spec, af)
        by = {r["subject_id"]: r for r in rows.values()}
        self.assertEqual(by["aws:aws_instance:instance_tipe"]["evidence_state"], "UNRESOLVED")
        self.assertEqual(by["aws:aws_instance:ami"]["evidence_state"], "STRUCTURALLY_VALID")

    def test_no_exact_and_derived_level(self):
        spec = {"aws": ("aws", {"SYM-v1aaaaaaaaaa": [("aws_instance", "instance_type", "identity")],
                                "SYM-v2aaaaaaaaaa": [("aws_instance", "ami", "expr")]}),
                "gcp": ("google", {"SYM-v1aaaaaaaaaa": [("google_compute_instance", "machine_type", "identity")],
                                   "SYM-v2aaaaaaaaaa": [("google_compute_instance", "boot_disk.initialize_params.image",
                                                         "identity")]})}
        rows, _t, _f = self.rows(spec)
        for r in rows.values():
            self.assertNotEqual(r["predicate_id"], "skos:exactMatch")
            self.assertEqual(r["curation_rule"], B.LEVEL_RULE)
            self.assertTrue(all(e["level"] == "derived" for e in r["proof"]["evidence"]))
        rel = {r["subject_id"]: r["semantic_relation"] for r in rows.values()}
        self.assertEqual(rel, {"aws:aws_instance:instance_type": "close", "aws:aws_instance:ami": "related"})


@unittest.skipUnless((data_dir() / "mods.sssom.tsv").is_file() and (results_dir() / "families.json").is_file(),
                     "saídas do GOLD-MODS ainda não geradas")
class ResolveMutations(unittest.TestCase):
    """O gate de resolução reprova quando a saída é adulterada (controle: a saída real passa)."""

    @classmethod
    def setUpClass(cls):
        cls.d = Path(tempfile.mkdtemp(dir=tmp_dir()))
        for n in ("mods.sssom.tsv", "traces.jsonl", "resolution.json"):
            shutil.copy(data_dir() / n, cls.d / n)
        shutil.copy(results_dir() / "families.json", cls.d / "families.json")
        res = json.loads((cls.d / "resolution.json").read_text(encoding="utf-8"))
        cls.af = Counter({B.corpus_key(a): n for a, n in res["atoms"].items()})
        meta, rows, _ = CSSSOM.read_tsv((cls.d / "mods.sssom.tsv").read_text(encoding="utf-8"))
        cls.rows = rows

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d)

    def run_with(self, rows):
        p = self.d / "mods.sssom.tsv"
        orig = p.read_text(encoding="utf-8")
        try:
            p.write_text(CSSSOM.write_tsv(rows, B.MAPPING_SET_ID, B.PREFIXES), encoding="utf-8")
            return R.check(self.d, self.d, self.af)[0]
        finally:
            p.write_text(orig, encoding="utf-8")

    def first_d(self):
        return next(i for i, r in enumerate(self.rows) if r["claim_id"].startswith("MOD-D-"))

    def test_control_passes(self):
        self.assertEqual(R.check(self.d, self.d, self.af)[0], [])

    def test_wrong_pivot_fails_r1(self):
        rows = copy.deepcopy(self.rows)
        i = self.first_d()
        rows[i]["proof"]["evidence"][0]["pivot"] = "SYM-ffffffffffff"
        self.assertTrue(any(f.startswith("R1") for f in self.run_with(rows)))

    def test_flipped_state_fails_r3(self):
        rows = copy.deepcopy(self.rows)
        i = self.first_d()
        rows[i]["evidence_state"] = "DOC_SUPPORTED"
        self.assertTrue(any(f.startswith("R3") for f in self.run_with(rows)))

    def test_exact_fails_r4(self):
        rows = copy.deepcopy(self.rows)
        i = self.first_d()
        rows[i]["predicate_id"], rows[i]["semantic_relation"] = "skos:exactMatch", "exact"
        self.assertTrue(any(f.startswith("R4") for f in self.run_with(rows)))

    def test_swapped_object_fails_r2(self):
        rows = copy.deepcopy(self.rows)
        i = self.first_d()
        rows[i]["object_id"] = "azurerm:azurerm_resource_group:name" \
            if rows[i]["object_id"] != "azurerm:azurerm_resource_group:name" else "azurerm:azurerm_subnet:name"
        self.assertTrue(any(f.startswith("R2") for f in self.run_with(rows)))


if __name__ == "__main__":
    unittest.main()
