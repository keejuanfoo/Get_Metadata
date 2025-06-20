import re
import json
import os

def extract_class_and_method(signature):
    # Example: com.site.blog.my.core.controller.admin.AdminController: java.lang.String passwordUpdate(...)
    match = re.match(r'([^:]+):.*? (\w+)\(', signature)
    if match:
        class_name = match.group(1).strip()
        method_name = match.group(2).strip()
        return class_name, method_name
    return None, None

def generate_call_graph():
    edges = []
    cnt = 0

    with open("./helper_data/sootup_output.txt", "r") as file:
        for line in file:
            if "-->" not in line:
                continue
            left, right = line.split("-->")
            left = left.strip()[1:-1]   # remove '<' and '>'
            right = right.strip()[1:-1]

            source_class, source_method = extract_class_and_method(left)
            target_class, target_method = extract_class_and_method(right)

            if all(v is not None for v in [source_class, source_method, target_class, target_method]):
                edges.append({
                    "source": {
                        "class": source_class,
                        "method": source_method
                    },
                    "target": {
                        "class": target_class,
                        "method": target_method
                    }
                })

    return edges

if __name__ == '__main__':
    edges = generate_call_graph()

    os.makedirs('./output_data', exist_ok=True)

    with open("./helper_data/callgraph.json", "w") as out:
        json.dump(edges, out, indent=2)
