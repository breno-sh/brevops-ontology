// Harness do teste de ontologia de topo (ONTPAT). Usa só o OWLAPI e o HermiT embutidos no ROBOT fixado
// (toolchain_pins.json); compilado e rodado por bo.ontpat.upper_trial contra o robot.jar, em $BO_TMP.
//
// Entrada (TSV, uma diretiva por linha):
//   JOB  <id>  <arquivo1>|<arquivo2>|...      carrega os arquivos (e seus imports locais) num só conjunto de axiomas
//   ENT  <check_id>  <arquivo>                verdadeiro se TODOS os axiomas lógicos do arquivo são consequência
//   DUMP <arquivo>                            tipos inferidos de indivíduos nomeados, sameAs e subclasses nomeadas
// Saída (TSV): JOB <id> consistent=<bool> axioms=<n> classes=<n> individuals=<n> load_ms=<n> reason_ms=<n>
//              ENT <check_id> <true|false|inconsistent|error:...> ms=<n>
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import org.semanticweb.HermiT.ReasonerFactory;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.model.*;
import org.semanticweb.owlapi.reasoner.*;

public class TrialReasoner {
    static OWLOntology current;
    static OWLReasoner reasoner;
    static boolean consistent;

    public static void main(String[] args) throws Exception {
        List<String> lines = Files.readAllLines(Paths.get(args[0]), StandardCharsets.UTF_8);
        try (PrintWriter out = new PrintWriter(new OutputStreamWriter(new FileOutputStream(args[1]), StandardCharsets.UTF_8))) {
            for (String line : lines) {
                if (line.isBlank() || line.startsWith("#")) continue;
                String[] f = line.split("\t");
                switch (f[0]) {
                    case "JOB": out.println(job(f[1], f[2])); break;
                    case "ENT": out.println(ent(f[1], f[2])); break;
                    case "DUMP": out.println(dump(f[1])); break;
                    default: throw new IllegalArgumentException("diretiva desconhecida: " + f[0]);
                }
                out.flush();
            }
        }
        if (reasoner != null) reasoner.dispose();
    }

    static String job(String id, String files) throws Exception {
        if (reasoner != null) reasoner.dispose();
        long t0 = System.nanoTime();
        OWLOntologyManager m = OWLManager.createOWLOntologyManager();
        Set<OWLAxiom> ax = new HashSet<>();
        for (String fn : files.split("\\|")) {
            OWLOntology o = m.loadOntologyFromOntologyDocument(new File(fn));
            for (OWLOntology c : o.getImportsClosure()) ax.addAll(c.getAxioms());
        }
        OWLOntologyManager m2 = OWLManager.createOWLOntologyManager();
        current = m2.createOntology(ax);
        long t1 = System.nanoTime();
        reasoner = new ReasonerFactory().createReasoner(current);
        consistent = reasoner.isConsistent();
        if (consistent) reasoner.precomputeInferences(InferenceType.CLASS_HIERARCHY, InferenceType.CLASS_ASSERTIONS);
        long t2 = System.nanoTime();
        return "JOB\t" + id + "\tconsistent=" + consistent + "\taxioms=" + current.getLogicalAxiomCount()
            + "\tclasses=" + current.getClassesInSignature().size()
            + "\tindividuals=" + current.getIndividualsInSignature().size()
            + "\tload_ms=" + (t1 - t0) / 1000000 + "\treason_ms=" + (t2 - t1) / 1000000;
    }

    static String ent(String id, String file) {
        long t0 = System.nanoTime();
        String r;
        try {
            if (!consistent) r = "inconsistent";
            else {
                OWLOntologyManager m = OWLManager.createOWLOntologyManager();
                OWLOntology q = m.loadOntologyFromOntologyDocument(new File(file));
                boolean all = true;
                int n = 0;
                for (OWLAxiom a : q.getLogicalAxioms()) {
                    n++;
                    if (!reasoner.isEntailed(a)) { all = false; break; }
                }
                r = n == 0 ? "error:arquivo sem axioma lógico" : Boolean.toString(all);
            }
        } catch (Exception e) {
            r = "error:" + e.getClass().getSimpleName() + ":" + String.valueOf(e.getMessage()).replace('\t', ' ').replace('\n', ' ');
        }
        return "ENT\t" + id + "\t" + r + "\tms=" + (System.nanoTime() - t0) / 1000000;
    }

    static String dump(String file) throws Exception {
        try (PrintWriter w = new PrintWriter(new OutputStreamWriter(new FileOutputStream(file), StandardCharsets.UTF_8))) {
            if (!consistent) { w.println("INCONSISTENT"); return "DUMP\t" + file + "\tinconsistent"; }
            List<OWLNamedIndividual> inds = new ArrayList<>(current.getIndividualsInSignature());
            inds.sort(Comparator.comparing(i -> i.getIRI().toString()));
            for (OWLNamedIndividual i : inds) {
                for (OWLClass c : reasoner.getTypes(i, false).getFlattened())
                    if (!c.isOWLThing()) w.println("TYPE\t" + i.getIRI() + "\t" + c.getIRI());
                for (OWLNamedIndividual s : reasoner.getSameIndividuals(i).getEntities())
                    if (!s.equals(i)) w.println("SAME\t" + i.getIRI() + "\t" + s.getIRI());
            }
            List<OWLClass> cls = new ArrayList<>(current.getClassesInSignature());
            cls.sort(Comparator.comparing(c -> c.getIRI().toString()));
            for (OWLClass c : cls) {
                if (!reasoner.isSatisfiable(c)) { w.println("UNSAT\t" + c.getIRI()); continue; }
                for (OWLClass d : reasoner.getSuperClasses(c, false).getFlattened())
                    if (!d.isOWLThing()) w.println("SUB\t" + c.getIRI() + "\t" + d.getIRI());
                for (OWLClass d : reasoner.getEquivalentClasses(c).getEntities())
                    if (!d.equals(c)) w.println("SUB\t" + c.getIRI() + "\t" + d.getIRI());
            }
        }
        return "DUMP\t" + file + "\tok";
    }
}
