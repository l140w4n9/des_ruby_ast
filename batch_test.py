"""Batch test restored_app AST files and collect readability issues."""
import glob
import os
import re
import traceback
from collections import Counter

from desast import decompile, parse_dump, render
from desast.beautify import beautify_ruby

ROOT = os.path.dirname(os.path.abspath(__file__))
AST_ROOT = os.path.join(ROOT, 'restored_app')
OUT_ROOT = os.path.join(ROOT, 'restored_app', '_decompiled')

issues = Counter()
errors = []
stats = {'total': 0, 'ok': 0, 'empty': 0, 'fail': 0}


def scan_issues(code: str, path: str):
    if 'BEGIN {' in code:
        issues['begin_wrapper'] += 1
    if re.search(r'\bdef \w+\(\)', code):
        issues['def_empty_parens'] += 1
    if re.search(r'\binclude\(', code):
        issues['include_parens'] += 1
    if re.search(r'\.(<=>|!=|==)\(', code):
        issues['binary_dot_call'] += 1
        if re.search(r'^\s+\S', line) and not re.match(r'^\s*(class|module|def|end|else|elsif|rescue|when|begin)', line):
            if len(line) - len(line.lstrip()) < 2 and line.strip():
                issues['bad_indent'] += 1
    for line in code.splitlines():
        if len(line) > 120:
            issues['long_lines'] += 1
        if re.search(r'\{"\w+"\s*=>\s*[^,}]+\}', line) and ' => ' in line:
            issues['hash_rocket'] += 1
        if re.search(r'belongs_to "[^"]+", \{', line):
            issues['association_hash'] += 1
        if re.search(r'\brescue\s*$', line):
            issues['bare_rescue'] += 1
        if re.search(r'\beach do\s*$', line):
            issues['each_no_param'] += 1
        if '.try("' in line:
            issues['try_string'] += 1
        if re.search(r'after_\w+\("', line):
            issues['callback_string'] += 1
        if re.search(r'scope "[^"]+"', line):
            issues['scope_string'] += 1


def main():
    os.makedirs(OUT_ROOT, exist_ok=True)
    ast_files = glob.glob(os.path.join(AST_ROOT, '**', '*.ast'), recursive=True)
    stats['total'] = len(ast_files)

    for ast_path in ast_files:
        rel = os.path.relpath(ast_path, AST_ROOT)
        out_rel = rel[:-4] if rel.endswith('.ast') else rel.replace('.ast', '.rb')
        out_path = os.path.join(OUT_ROOT, out_rel)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        try:
            with open(ast_path, encoding='utf-8') as f:
                text = f.read()
            root = parse_dump(text)
            if not root:
                stats['empty'] += 1
                continue
            raw = render(root)
            code = beautify_ruby(raw)
            if not code.strip():
                stats['empty'] += 1
                continue
            scan_issues(code, ast_path)
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(code)
            stats['ok'] += 1
        except Exception as e:
            stats['fail'] += 1
            errors.append((rel, str(e)))

    print('=== Batch Stats ===')
    for k, v in stats.items():
        print(f'  {k}: {v}')
    print('\n=== Issue Counts ===')
    for k, v in issues.most_common():
        print(f'  {k}: {v}')
    if errors[:5]:
        print('\n=== Sample Errors ===')
        for rel, err in errors[:5]:
            print(f'  {rel}: {err}')
    report = os.path.join(OUT_ROOT, '_report.txt')
    with open(report, 'w', encoding='utf-8') as f:
        f.write(str(dict(stats)) + '\n')
        f.write(str(dict(issues)) + '\n')
        for rel, err in errors:
            f.write(f'ERROR {rel}: {err}\n')


if __name__ == '__main__':
    main()
