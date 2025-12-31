import os
import re
import ast
from collections import defaultdict

PROJECT_ROOT = '/home/cwdavis/netstacks'

def extract_routes(root_path):
    """
    Extracts Flask routes from Python files.
    Returns a list of dicts: {'file':, 'line':, 'endpoint':, 'methods':, 'function':}
    """
    routes = []
    
    # Regex to find @app.route('/path', ...) or @ns.route('...', ...)
    # His AST visitor approach is better
    
    for root, dirs, files in os.walk(root_path):
        if 'venv' in dirs: dirs.remove('venv')
        if 'node_modules' in dirs: dirs.remove('node_modules')
        
        for file in files:
            if file.endswith('.py'):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8') as f:
                    try:
                        tree = ast.parse(f.read(), filename=path)
                    except:
                        continue
                    
                    for node in ast.walk(tree):
                        if isinstance(node, ast.FunctionDef):
                            for decorator in node.decorator_list:
                                if isinstance(decorator, ast.Call):
                                    # check for route
                                    func_name = ""
                                    if isinstance(decorator.func, ast.Attribute):
                                        func_name = decorator.func.attr
                                    elif isinstance(decorator.func, ast.Name):
                                        func_name = decorator.func.id
                                    
                                    if func_name in ['route', 'expect', 'doc']:
                                        # Only care about route
                                        if func_name == 'route':
                                            # Arg 0 is usually the path
                                            if decorator.args:
                                                if isinstance(decorator.args[0], ast.Constant):
                                                    url_path = decorator.args[0].value
                                                    routes.append({
                                                        'file': path,
                                                        'line': node.lineno,
                                                        'url': url_path,
                                                        'function': node.name
                                                    })

    return routes

def scan_frontend_for_urls(root_path, routes):
    """
    Scans JS/HTML for strings that look like the route URLs.
    """
    unused_routes = []
    used_routes = []
    
    # We strip <param> from routes to match the base path
    # e.g. /api/device/<id> -> match /api/device/ or /api/device
    
    normalized_routes = {}
    for r in routes:
        # crude regex to replace <...> with nothing or regex
        # For searching, we'll try to find the constant parts
        # e.g. /api/v1/devices
        parts = r['url'].split('/')
        search_terms = [p for p in parts if not p.startswith('<') and p != '']
        if not search_terms:
            # Root path '/'
            search_terms = ['/']
        
        normalized_routes[r['url']] = {
            'terms': search_terms,
            'original': r,
            'found': False
        }

    # Files to scan
    scan_exts = ('.js', '.html', '.j2')
    
    for root, dirs, files in os.walk(root_path):
        if 'node_modules' in dirs: dirs.remove('node_modules')
        
        for file in files:
            if file.endswith(scan_exts):
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        
                        for url, data in normalized_routes.items():
                            if data['found']: continue
                            
                            # Heuristic: check if all constant parts exist in a single line or close proximity
                            # Or simpler: check if the exact path string (minus params) exists
                            # E.g. for /api/devices/<id>, look for "/api/devices/" or "/api/devices"
                            
                            # Construct a partial path
                            # /api/devices/<id> -> /api/devices
                            base_path = url.split('<')[0]
                            if base_path.endswith('/') and len(base_path) > 1:
                                base_path = base_path[:-1]
                                
                            if base_path in content:
                                data['found'] = True
                            
                            # Also check for flask's url_for('function_name') in Jinja
                            # url_for('get_devices')
                            if f"url_for('{data['original']['function']}'" in content or \
                               f'url_for("{data["original"]["function"]}"' in content:
                                data['found'] = True
                except Exception as e:
                    print(f"Error reading {path}: {e}")

    for url, data in normalized_routes.items():
        if data['found']:
            used_routes.append(data['original'])
        else:
            unused_routes.append(data['original'])
            
    return unused_routes, used_routes

def main():
    print("Extracting routes...")
    routes = extract_routes(PROJECT_ROOT)
    print(f"Found {len(routes)} routes.")
    
    print("Auditing frontend usage...")
    unused, used = scan_frontend_for_urls(PROJECT_ROOT, routes)
    
    print(f"\n=== POSSIBLY UNUSED ROUTES ({len(unused)}) ===")
    for r in unused:
        print(f"{r['url']} => {r['function']} ({r['file']}:{r['line']})")
        
    print(f"\nSummary: {len(used)} verified used, {len(unused)} potentially unused (no direct exact string match or url_for).")

if __name__ == "__main__":
    main()
