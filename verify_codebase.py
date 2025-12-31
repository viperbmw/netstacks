import os
import ast
import re
import collections
import json

PROJECT_ROOT = '/home/cwdavis/netstacks'
SKIP_DIRS = {'.git', '__pycache__', 'venv', 'env', 'node_modules', '.pytest_cache', 'migrations', 'postgres-init'}
SKIP_FILES = {'verify_codebase.py', 'requirements.txt', '.DS_Store'}

class DefinitionVisitor(ast.NodeVisitor):
    def __init__(self, filename):
        self.filename = filename
        self.definitions = []

    def visit_FunctionDef(self, node):
        self.definitions.append({
            'type': 'function',
            'name': node.name,
            'file': self.filename,
            'lineno': node.lineno,
            'args': [a.arg for a in node.args.args]
        })
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self.definitions.append({
            'type': 'async_function',
            'name': node.name,
            'file': self.filename,
            'lineno': node.lineno,
            'args': [a.arg for a in node.args.args]
        })
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        # We also want to track class names to see if they are instantiated
        self.definitions.append({
            'type': 'class',
            'name': node.name,
            'file': self.filename,
            'lineno': node.lineno,
            'args': []
        })
        self.generic_visit(node)

def get_definitions(root_path):
    definitions = []
    for root, dirs, files in os.walk(root_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for file in files:
            if file.endswith('.py') and file not in SKIP_FILES:
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        tree = ast.parse(f.read(), filename=path)
                    visitor = DefinitionVisitor(path)
                    visitor.visit(tree)
                    definitions.extend(visitor.definitions)
                except Exception as e:
                    print(f"Error parsing {path}: {e}")
    return definitions

def count_usages(root_path, definitions):
    # Create a counter for all names
    # specific_counts tracks exact matches
    counts = collections.defaultdict(int)
    
    # Pre-compute a set of names to search for faster lookup
    names_to_find = {d['name'] for d in definitions}
    
    # Regex for finding words
    word_pattern = re.compile(r'\b\w+\b')

    for root, dirs, files in os.walk(root_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for file in files:
            if file in SKIP_FILES: continue
            # Check relevant extensions
            if not file.endswith(('.py', '.js', '.html', '.css', '.md', '.txt')):
                continue
            
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    words = word_pattern.findall(content)
                    for word in words:
                        if word in names_to_find:
                            counts[word] += 1
            except Exception as e:
                print(f"Error reading {path}: {e}")
                
    return counts

def main():
    print(f"Scanning {PROJECT_ROOT}...")
    definitions = get_definitions(PROJECT_ROOT)
    print(f"Found {len(definitions)} definitions.")
    
    print("Counting usages...")
    usage_counts = count_usages(PROJECT_ROOT, definitions)
    
    report = {
        'total_definitions': len(definitions),
        'unused': [],
        'low_usage': [], # usage found but might be definition only (count=1)
        'good_usage': []
    }
    
    for d in definitions:
        name = d['name']
        count = usage_counts[name]
        
        info = {
            'name': name,
            'file': d['file'],
            'lineno': d['lineno'],
            'type': d['type'],
            'count': count
        }
        
        if count == 0:
            # Should not happen as definition itself is text, but maybe AST vs Regex diff
            report['unused'].append(info)
        elif count == 1:
            report['unused'].append(info) # 1 means likely only the definition exists
        elif count < 3:
            report['low_usage'].append(info)
        else:
            report['good_usage'].append(info)

    # Sort report
    report['unused'].sort(key=lambda x: x['file'])
    
    # Output results
    print("\n=== POTENTIALLY UNUSED FUNCTIONS/CLASSES (Count=1) ===")
    for item in report['unused']:
        print(f"[{item['type']}] {item['name']} in {item['file']}:{item['lineno']}")
        
    print(f"\nSummary: {len(report['unused'])} unused, {len(report['low_usage'])} low usage, {len(report['good_usage'])} good usage.")
    
    # Save to json for further analysis
    with open('verification_report.json', 'w') as f:
        json.dump(report, f, indent=2)
    print("Report saved to verification_report.json")

if __name__ == '__main__':
    main()
