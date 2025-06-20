import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Set;
import java.util.HashSet;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.PrintStream;
import java.util.Optional;
import java.util.stream.Stream;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

import sootup.callgraph.CallGraph;
import sootup.callgraph.CallGraphAlgorithm;
import sootup.callgraph.ClassHierarchyAnalysisAlgorithm;
import sootup.core.inputlocation.AnalysisInputLocation;
import sootup.core.signatures.MethodSignature;
import sootup.core.typehierarchy.ViewTypeHierarchy;
import sootup.core.types.ClassType;
// import sootup.core.types.VoidType;
import sootup.java.bytecode.frontend.inputlocation.JavaClassPathAnalysisInputLocation;
import sootup.java.core.JavaIdentifierFactory;
// import sootup.java.core.JavaSootClass;
// import sootup.java.core.language.JavaLanguage;
import sootup.java.core.views.JavaView;
import sootup.java.core.JavaSootClass;
import sootup.java.core.JavaSootMethod;

public class CallGraphGenerator {
    public static void main(String[] args) {
        if (args.length < 2) {
            System.err.println("Needs the folder and output folder codepath!");
            System.exit(1);
        }

        String inputPath = args[0];
        System.out.println("inputPath: " + inputPath);
        String outputPath = args[1];
    
        List<AnalysisInputLocation> inputLocations = new ArrayList<>();
        inputLocations.add(new JavaClassPathAnalysisInputLocation(inputPath));
        // inputLocations.add(
        //     new JavaClassPathAnalysisInputLocation(
        //         System.getProperty("java.home") + "/lib/rt.jar")); // add rt.jar

        JavaView view = new JavaView(inputLocations);
        List<MethodSignature> controllerMethods = getControllerMethods(view, "com.site.blog.my.core.controller");

        // Create type hierarchy and CHA
        final ViewTypeHierarchy typeHierarchy = new ViewTypeHierarchy(view);
        // System.out.println(typeHierarchy.subclassesOf(controllerType));
        CallGraphAlgorithm cha = new ClassHierarchyAnalysisAlgorithm(view);

        // Create CG by initializing CHA with entry method(s)
        CallGraph cg = cha.initialize(controllerMethods);

        Set<MethodSignature> visited = new HashSet<>();

        Path outputDir = Paths.get(outputPath);

        try {
            Files.createDirectories(outputDir);  // creates all non-existent directories
            System.out.println("Directory created or already exists: " + outputDir);
        } catch (IOException e) {
            e.printStackTrace();
        }

        try (PrintStream fileStream = new PrintStream(outputPath + "/sootup_output.txt")) {
            // cg.callsFrom(entryMethodSignature).forEach(fileStream::println);
            for (MethodSignature entryMethodSignature : controllerMethods) {
                dfsCallGraph(cg, view, entryMethodSignature, visited, fileStream);
            }
        } catch (FileNotFoundException fnf) {
            fnf.printStackTrace();
        }

        System.out.println("# of Methods:" + visited.size());

        try (FileOutputStream fos = new FileOutputStream(outputPath + "/all_methods.txt")) {
            for (MethodSignature method : visited) {
                fos.write((method + System.lineSeparator()).getBytes());
            }
            System.out.println("Set written to file successfully.");
        } catch (IOException e) {
            e.printStackTrace();
        }
    }

    private static List<MethodSignature> getControllerMethods(JavaView view, String controllerPackagePrefix) {
        List<MethodSignature> methods = new ArrayList<>();
        Stream<JavaSootClass> classStream = view.getClasses();
        classStream.forEach(cls -> {
            if (cls.getType().getFullyQualifiedName().startsWith(controllerPackagePrefix)) {
                for (JavaSootMethod method : cls.getMethods()) {
                    if (method.isPublic() && !method.getName().equals("<init>")) {
                        MethodSignature curMethodSignature = JavaIdentifierFactory.getInstance().getMethodSignature(
                            cls.getType(), // class name
                            method.getSubSignature()
                        );
                        methods.add(curMethodSignature);
                    }
                }
            }
        });

        // classStream = view.getClasses();
        // long streamSize = classStream.count();
        // System.out.println("# of Controller Classes: " + streamSize);
        // System.out.println("# of Controller Methods: " + methods.size());

        return methods;
    }

    private static void dfsCallGraph(CallGraph cg, JavaView view, MethodSignature current,
                                     Set<MethodSignature> visited, PrintStream out) {
        if (visited.contains(current)) return;
        visited.add(current);

        cg.callTargetsFrom(current).forEach(target -> {
            Optional<JavaSootClass> curClass = view.getClass(target.getDeclClassType());
            if (curClass.isPresent() && curClass.get().isApplicationClass()) {
                out.println(current + " --> " + target);
                dfsCallGraph(cg, view, target, visited, out);
            }
        });
    }
}
