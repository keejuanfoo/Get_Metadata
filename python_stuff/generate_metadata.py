import json
from collections import defaultdict, deque
import pandas as pd
import ollama
from pydantic import BaseModel, create_model
from typing import List, Dict
import re
import time
import os

def extract_class_and_method(signature):
    # Example: com.site.blog.my.core.controller.admin.AdminController: java.lang.String passwordUpdate(...)
    signature = signature.lstrip('<')
    match = re.match(r'([^:]+):.*? (\w+)\(', signature)
    if match:
        class_name = match.group(1).strip()
        method_name = match.group(2).strip()
        return class_name, method_name
    return None, None

def get_all_methods_and_classes(all_methods_path):
    all_methods_set = set()
    all_classes_set = set()

    with open(all_methods_path) as f:
        for i, line in enumerate(f):
            cur_class, cur_method = extract_class_and_method(line)
            if cur_class and cur_method:
                cur_full_method_name = cur_class + '.' + cur_method
                all_methods_set.add(cur_full_method_name)
                all_classes_set.add(cur_class)

    return all_methods_set, all_classes_set

def get_class_method_relations(all_methods_set):
    all_methods_to_class_map = {}
    all_class_to_methods_map = defaultdict(set)

    for i, cur_method in enumerate(all_methods_set):
        cur_class = cur_method.rsplit('.', 1)[0]

        all_methods_to_class_map[cur_method] = cur_class
        all_class_to_methods_map[cur_class].add(cur_method)

    return all_methods_to_class_map, all_class_to_methods_map

def process_cg(call_graph_path):
    with open(call_graph_path) as f:
        data = json.load(f)

    method_to_class_map = {}
    class_forward_map = defaultdict(set)
    class_reverse_map = defaultdict(set)
    method_forward_map = defaultdict(set)
    method_reverse_map = defaultdict(set)

    for edge in data:
        source_class = edge['source']['class']
        source_method = source_class + '.' + edge['source']['method']
        target_class = edge['target']['class']
        target_method = target_class + '.' + edge['target']['method']
        
        if source_method not in method_to_class_map:
            method_to_class_map[source_method] = source_class
        if target_method not in method_to_class_map:
            method_to_class_map[target_method] = target_class
        class_forward_map[source_class].add(target_class)
        class_reverse_map[target_class].add(source_class)
        method_forward_map[source_method].add(target_method)
        method_reverse_map[target_method].add(source_method)

    return method_to_class_map, class_forward_map, class_reverse_map, method_forward_map, method_reverse_map

def generate_base_prompt_for_documentation(class_name, method_set):
    return f"""
    You are a Java documentation assistant. Given a Java class and a list of its method names, your task is to generate Oracle-style JavaDoc documentation as a **pure JSON object**.

    Follow these formatting rules:

    1. Return only a JSON object with the following structure:
    {{
        "<full class name>": "<JavaDoc for the class>",
        "<full method name>": "<JavaDoc for method 1>",
        "<full method name>": "<JavaDoc for method 2>",
        ...
    }}

    2. Use Oracle JavaDoc formatting in each string:
    - A concise description of what the class or method does.
    - <p> tags for paragraph breaks.
    - @param tags for all method parameters, with clear and helpful explanations.
    - @return if the method returns a value.
    - @throws if exceptions are declared.
    - @see for related classes or methods, if relevant.

    3. For each method:
    - Identify any instance variables used (i.e., fields declared in the class).
    - If used, include their name and type like this:
        > This method uses the instance variable {{@code loader}} of type {{@link com.example.ImageLoader}} to fetch the image.

    4. Do **not** modify or rewrite any Java code.
    5. Maintain correct JavaDoc style and indentation in the output strings.

    ### Example Output Format:
    {{
        "class": "/**\\n * Handles image management and retrieval.\\n */",
        "getImage": "/**\\n * Returns an image from a given URL and relative name.\\n * <p>\\n * This method uses the instance variable {{@code loader}} of type {{@link com.example.ImageLoader}}.\\n *\\n * @param url an absolute base URL\\n * @param name image path relative to the base\\n * @return the requested image\\n * @see Image\\n */"
    }}

    ### Now generate documentation for:

    Class: 
    {class_name}

    Methods (in a Python set): 
    {method_set}
    """

def generate_dynamic_model(class_name_full, method_set):
    # Inputs
    model_name = "Documentation"
    field_list = [class_name_full]
    for method in method_set:
        field_list.append(method)

    # Define fields: each is an optional string
    fields = {name: (str, None) for name in field_list}

    # Create the dynamic model
    return create_model(model_name, **fields)

def generate_documentation(full_prompt, dynamic_model):
    response = ollama.chat(
        model='llama3.2',  # or another model you've pulled
        messages=[{"role": "user", "content": full_prompt}],
        format=dynamic_model.model_json_schema()
    )
    return response.message.content

def chunk_methods(method_set, chunk_size):
    method_list = sorted(list(method_set))
    for i in range(0, len(method_list), chunk_size):
        yield method_list[i:i + chunk_size]

def generate_documentation_for_class(class_name_full, chunk_size):
    class_name = class_name_full.split('.')[-1]
    class_code = class_df[class_df['class_name'] == class_name]['source_code'].squeeze()
    method_set = all_class_to_methods_map[class_name_full]
    
    if len(method_set) > 5:
        documentation = {}
        for chunk in chunk_methods(method_set, chunk_size):
            base_prompt = generate_base_prompt_for_documentation(class_name_full, chunk)
            full_prompt = base_prompt + class_code
            dynamic_model = generate_dynamic_model(class_name_full, chunk)
            documentation.update(json.loads(generate_documentation(full_prompt, dynamic_model)))

    else:
        base_prompt = generate_base_prompt_for_documentation(class_name_full, method_set)
        full_prompt = base_prompt + class_code
        dynamic_model = generate_dynamic_model(class_name_full, method_set)
        documentation = json.loads(generate_documentation(full_prompt, dynamic_model))

    return documentation

def get_docstrings(all_classes_set, chunk_size):
    class_docstring_map = {}
    method_docstring_map = {}
    max_retries = 3
    failed_set = set()

    for _, cur_class in enumerate(all_classes_set):
        success = False
        attempts = 0

        while not success and attempts < max_retries:
            try:
                print(f'Processing {cur_class} (Attempt {attempts + 1})')
                cur_method_list = list(all_class_to_methods_map[cur_class])

                cur_documentation_all = generate_documentation_for_class(cur_class, chunk_size)
                class_docstring_map[cur_class] = cur_documentation_all[cur_class]

                for cur_method in cur_method_list:
                    method_docstring_map[cur_method] = cur_documentation_all[cur_method]

                success = True  # If everything passes, mark as successful

            except Exception as e:
                attempts += 1
                print(f"Failed processing {cur_class}: {e}")
                if attempts < max_retries:
                    time.sleep(1)  # brief pause before retry
                else:
                    failed_set.add(cur_class)
                    print(f"Skipping {cur_class} after {max_retries} failed attempts.")

    return class_docstring_map, method_docstring_map, failed_set

def generate_docstring_for_class(cur_class, class_docstring_map, method_docstring_map, chunk_size):
    try:
        cur_method_list = list(all_class_to_methods_map[cur_class])
        cur_documentation_all = generate_documentation_for_class(cur_class, chunk_size)
        class_docstring_map[cur_class] = cur_documentation_all[cur_class]

        for cur_method in cur_method_list:
            method_docstring_map[cur_method] = cur_documentation_all[cur_method]

        return True
    
    except Exception as e:
        print(e)
        return False
    
def generate_docstring_for_failures(failed_set, class_docstring_map, method_docstring_map):
    max_retries = 3
    give_up_set = set()

    for _, cur_class in enumerate(failed_set):
        success = False
        attempts = 0

        while not success and attempts < max_retries:
            success = generate_docstring_for_class(cur_class, class_docstring_map, method_docstring_map, chunk_size=1)
            attempts += 1

        if not success:
            give_up_set.add(cur_class)

    return give_up_set

def generate_metadata(all_classes_set, all_methods_set, class_docstring_map, method_docstring_map, class_df, method_df):
    class_metadata_map = defaultdict(dict)
    method_metadata_map = defaultdict(dict)

    for cur_class in all_classes_set:
        class_metadata_map[cur_class]['docstring'] = class_docstring_map[cur_class]
        class_metadata_map[cur_class]['code'] = class_df[class_df['class_name'] == cur_class.split('.')[-1]]['source_code'].squeeze()

    for cur_method in all_methods_set:
        method_metadata_map[cur_method]['code'] = method_df[(method_df['name'] == cur_method.split('.')[-1]) & 
                                                            (method_df['class_name'] == cur_method.split('.')[-2])]['source_code'].squeeze()
        if ((method_df['name'] == cur_method.split('.')[-1]) & (method_df['class_name'] == cur_method.split('.')[-2])).any():
            method_metadata_map[cur_method]['code'] = method_df[(method_df['name'] == cur_method.split('.')[-1]) & 
                                                                (method_df['class_name'] == cur_method.split('.')[-2])]['source_code'].squeeze()
        else:
            method_metadata_map[cur_method]['code'] = 'no code parsed'

        if cur_method in method_docstring_map:
            method_metadata_map[cur_method]['docstring'] = method_docstring_map[cur_method]
        else:
            method_metadata_map[cur_method]['docstring'] = 'failed to generate'

            
    return class_metadata_map, method_metadata_map

def save_metadata(class_metadata_map, method_metadata_map):
    os.makedirs('./output_data', exist_ok=True)

    with open('./output_data/class_metadata.json', 'w', encoding='utf-8') as f:
        json.dump(class_metadata_map, f, ensure_ascii=False, indent=4)
    with open('./output_data/method_metadata.json', 'w', encoding='utf-8') as f:
        json.dump(method_metadata_map, f, ensure_ascii=False, indent=4)

def get_class_and_method_flow_map(class_forward_map, method_forward_map):
    class_flow_map = {}
    for cur_class in all_classes_set:
        if cur_class in class_forward_map:
            class_flow_map[cur_class] = list(class_forward_map[cur_class])
        else:
            class_flow_map[cur_class] = []

    method_flow_map = {}
    for cur_method in all_methods_set:
        if cur_method in method_forward_map:
            method_flow_map[cur_method] = list(method_forward_map[cur_method])
        else:
            method_flow_map[cur_method] = []

    return class_flow_map, method_flow_map

def save_flow_maps(class_flow_map, method_flow_map):
    os.makedirs('./output_data', exist_ok=True)

    with open('./output_data/class_flow_map.json', 'w', encoding='utf-8') as f:
        json.dump(class_flow_map, f, ensure_ascii=False, indent=4)
    with open('./output_data/method_flow_map.json', 'w', encoding='utf-8') as f:
        json.dump(method_flow_map, f, ensure_ascii=False, indent=4)

if __name__ == '__main__':
    class_df = pd.read_csv('./helper_data/class_data.csv')
    method_df = pd.read_csv('./helper_data/method_data.csv')

    all_methods_path = './helper_data/all_methods.txt'
    all_methods_set, all_classes_set = get_all_methods_and_classes(all_methods_path)
    all_methods_to_class_map, all_class_to_methods_map = get_class_method_relations(all_methods_set)
    class_docstring_map, method_docstring_map, failed_set = get_docstrings(all_classes_set, chunk_size=5)
    print('--- generated docstrings ---')
    print(f'failed to generate for the set {failed_set}, retrying...')
    give_up_set = generate_docstring_for_failures(failed_set, class_docstring_map, method_docstring_map)
    if len(give_up_set) > 0:
        print('Unable to fully generate docstrings for the class(es):')
        for cur_class in give_up_set:
            print(cur_class)
    
    class_metadata_map, method_metadata_map = generate_metadata(
        all_classes_set, all_methods_set, class_docstring_map, method_docstring_map, class_df, method_df
    )
    save_metadata(class_metadata_map, method_metadata_map)

    call_graph_path = "./helper_data/callgraph.json"
    method_to_class_map, class_forward_map, class_reverse_map, method_forward_map, method_reverse_map = process_cg(call_graph_path)
    class_flow_map, method_flow_map = get_class_and_method_flow_map(class_forward_map, method_forward_map)
    save_flow_maps(class_flow_map, method_flow_map)
