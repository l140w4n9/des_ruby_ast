"""Post-process rendered Ruby source for maximum readability."""
import re
from typing import List, Tuple

# 二元运算符方法名 (MRI NODE_CALL nd_mid)
BINARY_OPS = frozenset({
    '<=>', '==', '!=', '===', '=~', '!~', '<', '>', '<=', '>=',
    '+', '-', '*', '/', '%', '&', '|', '^', '<<', '>>', '&&', '||',
})

RAILS_MACROS_NO_PAREN = frozenset({
    'include', 'extend', 'prepend', 'require', 'require_relative',
    'attr_reader', 'attr_writer', 'attr_accessor', 'attr_accessible',
    'belongs_to', 'has_many', 'has_one', 'has_and_belongs_to_many',
    'validates', 'validate', 'before_action', 'after_action', 'around_action',
    'before_filter', 'after_filter', 'scope', 'delegate', 'enum',
    'acts_as', 'set_table_name', 'table_name', 'default_scope',
    'serialize', 'store_accessor', 'mount', 'use', 'run', 'plugin',
    'helper', 'helper_method', 'skip_before_action', 'skip_after_action',
    'protect_from_forgery', 'layout', 'respond_to', 'resources',
    'resource', 'root', 'match', 'get', 'post', 'put', 'delete', 'patch',
    'with_options', 'alias_method_chain', 'alias_method',
    'after_create', 'after_save', 'after_update', 'after_commit', 'after_destroy',
    'before_create', 'before_save', 'before_update', 'before_destroy',
    'after_validation', 'before_validation', 'after_find', 'after_initialize',
})

ASSOCIATION_MACROS = frozenset({
    'belongs_to', 'has_many', 'has_one', 'has_and_belongs_to_many',
})

RUBY_LITERALS = frozenset({
    'true', 'false', 'nil', 'self', 'null',
})

SYMBOL_VALUE_KEYS = frozenset({
    'foreign_key', 'inverse_of', 'as', 'on', 'through', 'source', 'source_type',
    'dependent', 'class_name', 'primary_key', 'counter_cache', 'touch',
    'client_id', 'sync_type', 'role_code', 'utype', 'client_type',
    'deleted', 'pending', 'actived', 'deleted_mark',
})

CONTINUATION_KEYWORDS = frozenset({'else', 'elsif', 'rescue', 'ensure', 'when'})
INDENT_KEYWORDS = frozenset({
    'class', 'module', 'def', 'if', 'unless', 'case', 'while', 'until', 'for', 'begin',
})

RE_BEGIN_WRAPPER = re.compile(r'^\s*BEGIN\s*\{\s*\n(.*)\n\s*\}\s*$', re.DOTALL | re.MULTILINE)
RE_DEF_EMPTY_PARENS = re.compile(r'\bdef ((?:self\.)?[\w.]+[?!]?)\(\)')
RE_BINARY_OP_CALL = re.compile(
    r'(\S)\.(<=>|==|!=|===|=~|!~|<<|>>|<=|>=|\*\*|&&|\|\||[+\-*/%&|^])\(([^)]*)\)',
)
RE_RAILS_MACRO = re.compile(
    r'\b(' + '|'.join(re.escape(m) for m in sorted(RAILS_MACROS_NO_PAREN, key=len, reverse=True)) + r')\(([^)]*)\)',
)
RE_EMPTY_DO_BLOCK = re.compile(r'^([ \t]*)(\S.*?)\s+do\s*\n\1end\s*$', re.MULTILINE)
RE_EMPTY_MODULE = re.compile(r'^([ \t]*)module (\w+)\s*\n\1end\s*$', re.MULTILINE)
RE_DOUBLE_EQ = re.compile(r'=\s{2,}=')
RE_EMPTY_RESCUE = re.compile(
    r'^([ \t]*)begin\s*\n((?:\1  .+\n)+?)\1rescue\s*\n\1end\s*$', re.MULTILINE,
)
RE_EACH_BARE = re.compile(r'\beach do\s*$')
RE_TRY_STRING = re.compile(r'\.try\("(\w+)"\)')
RE_WITH_ATTR = re.compile(r'\bwith_attribute\("(\w+)"\)')
RE_UPDATE_ATTR = re.compile(r'\.update_attribute\("(\w+)"\s*,')
RE_INCLUDE_STR = re.compile(r'\.include\?\("([^"]+)"\)')
RE_SCOPE_STRING = re.compile(r'\bscope "(\w+)"\s*,')
RE_ASSOC_STRING = re.compile(
    r'^(\s*)(' + '|'.join(ASSOCIATION_MACROS) + r') "(\w+)"\s*,\s*(.+)$',
)
RE_ASSOC_SIMPLE = re.compile(
    r'^(\s*)(' + '|'.join(ASSOCIATION_MACROS) + r') "(\w+)"\s*$',
)
RE_HAS_MACRO = re.compile(r'^(\s*)(has_one|has_many) "(\w+)"\s*$')
RE_HASH_KEY_ROCKET = re.compile(r'"(\w+)"\s*=>\s*')
RE_HASH_CLASS_VAL = re.compile(r':\s*"(::[\w:]+)"')
RE_HASH_SYM_VAL = re.compile(r':\s*"(\w+)"(\s*[,}])')
RE_QUOTED_IDENT = re.compile(r'^"(\w+)"\s*,?\s*$')
RE_CALLBACK_BARE = re.compile(
    r'\b(after_create|after_save|after_update|after_commit|after_destroy|'
    r'before_create|before_save|before_update|before_destroy|'
    r'after_validation|before_validation|after_find|after_initialize) "(\w+)"',
)
RE_BARE_HASH_SYM_VAL = re.compile(
    r'(\b(?:' + '|'.join(re.escape(k) for k in sorted(SYMBOL_VALUE_KEYS, key=len, reverse=True)) + r'):\s+)'
    r'([a-z_]\w*)(\s*[,}])',
)
RE_SINGLE_PAIR_HASH = re.compile(
    r'^(\s*(?:belongs_to|has_many|has_one|has_and_belongs_to_many) :\w+, )\{ ([^:{}]+: [^,{}]+) \}\s*$',
)
RE_CLASS_EMPTY_RESCUE = re.compile(
    r'^([ \t]*)begin\s*\n((?:[ \t].*\n)+?)^\1rescue\s*\n^\1end\s*$',
    re.MULTILINE,
)
RE_CALLBACK_TWO_ARG = re.compile(
    r'\b(after_commit|after_create|after_save|before_save)\("(\w+)"\s*,\s*(\{[^}]+\})\)',
)
RE_SELECT_STRING = re.compile(r'^(\s*)"(\w+)"\s*,?\s*$')


def format_def_signature(name: str, args: List[str], level: int = 0, recv: str = None) -> str:
    prefix = f"{'  ' * level}def "
    prefix += f"{recv}.{name}" if recv else name
    if args:
        prefix += f"({', '.join(args)})"
    return prefix


def ensure_block_indent(text: str, level: int) -> str:
    if not text or level <= 0:
        return text
    pad = '  ' * level
    return '\n'.join(pad + line.lstrip() if line.strip() else '' for line in text.splitlines())


def beautify_ruby(code: str) -> str:
    if not code or not code.strip():
        return ''
    pipeline = (
        _strip_begin_wrapper,
        _fix_binary_operator_calls,
        _fix_def_empty_parens,
        _fix_rails_macro_parens,
        _fix_callback_two_args,
        _fix_callback_bare_strings,
        _fix_try_and_predicates,
        _fix_scope_and_associations,
        _hash_rockets_to_symbols,
        _fix_bare_hash_symbol_values,
        _flatten_single_option_hashes,
        _flatten_multi_option_assoc_hashes,
        _flatten_callback_option_hashes,
        _beautify_hash_literals_multiline,
        _symbols_in_attr_lists,
        _wrap_long_argument_lists,
        _wrap_long_bare_macros,
        _wrap_select_and_where,
        _symbols_in_select_arrays,
        _beautify_inline_select,
        _remove_empty_rescue_blocks,
        _remove_class_empty_rescue,
        _remove_empty_do_blocks,
        _remove_empty_modules,
        _fix_each_blocks,
        _reindent,
        _fix_attr_continuation_indent,
        _separate_methods,
        _separate_associations,
        _collapse_blank_lines,
        _format_hash_spacing,
        _trim_trailing_space,
    )
    for fn in pipeline:
        code = fn(code)
    return code.rstrip() + '\n'


def _strip_begin_wrapper(code: str) -> str:
    m = RE_BEGIN_WRAPPER.match(code.strip())
    if m:
        return m.group(1)
    lines = code.splitlines()
    if lines and lines[0].strip() == 'BEGIN {' and lines[-1].strip() == '}':
        return '\n'.join(lines[1:-1])
    return code


def _fix_binary_operator_calls(code: str) -> str:
    return RE_BINARY_OP_CALL.sub(r'\1 \2 \3', code)


def _fix_def_empty_parens(code: str) -> str:
    return RE_DEF_EMPTY_PARENS.sub(r'def \1', code)


def _fix_rails_macro_parens(code: str) -> str:
    def repl(m):
        macro, inner = m.group(1), m.group(2).strip()
        if not inner:
            return macro
        if ',' not in inner and '(' not in inner:
            return f'{macro} {inner}'
        return m.group(0)
    return RE_RAILS_MACRO.sub(repl, code)


def _fix_callback_bare_strings(code: str) -> str:
    return RE_CALLBACK_BARE.sub(r'\1 :\2', code)


def _fix_callback_two_args(code: str) -> str:
    def repl_paren(m):
        return f'{m.group(1)} :{m.group(2)}, {_format_inline_hash(m.group(3))}'

    code = RE_CALLBACK_TWO_ARG.sub(repl_paren, code)
    code = re.sub(
        r'\b(after_commit|after_create|after_save|before_save) "(\w+)"\s*,\s*(\{[^}]+\})',
        lambda m: f'{m.group(1)} :{m.group(2)}, {_format_inline_hash(m.group(3))}',
        code,
    )
    return code


def _format_inline_hash(h: str) -> str:
    h = _hash_rockets_to_symbols(h)
    h = _fix_bare_hash_symbol_values(h)
    inner = h.strip()[1:-1].strip()
    inner = RE_BARE_HASH_SYM_VAL.sub(r'\1:\2\3', inner)
    if len(inner) > 40 or inner.count(',') >= 2:
        return _format_hash_multiline(inner, base='    ')
    return '{ ' + inner + ' }'


def _fix_try_and_predicates(code: str) -> str:
    code = RE_TRY_STRING.sub(r'.try(:\1)', code)
    code = RE_WITH_ATTR.sub(r'with_attribute :\1', code)
    code = RE_UPDATE_ATTR.sub(r'.update_attribute(:\1,', code)
    code = RE_INCLUDE_STR.sub(r'.include?(:\1)', code)
    return code


def _fix_scope_and_associations(code: str) -> str:
    lines = []
    for line in code.splitlines():
        m = RE_ASSOC_STRING.match(line)
        if m:
            indent, macro, name, rest = m.groups()
            rest = _hash_rockets_to_symbols(rest.strip())
            rest = _fix_bare_hash_symbol_values(rest)
            if rest.startswith('{') and rest.endswith('}'):
                inner = rest[1:-1].strip()
                if len(inner) > 50 or inner.count(',') >= 2:
                    rest = _format_hash_multiline(inner, base=indent + '  ')
                else:
                    rest = '{ ' + inner + ' }'
            lines.append(f'{indent}{macro} :{name}, {rest}')
            continue
        m = RE_ASSOC_SIMPLE.match(line) or RE_HAS_MACRO.match(line)
        if m:
            lines.append(f'{m.group(1)}{m.group(2)} :{m.group(3)}')
            continue
        m = re.match(r'^(\s*)scope "(\w+)"\s*,\s*(.+)$', line)
        if m:
            indent, name, rest = m.groups()
            rest = _hash_rockets_to_symbols(rest)
            rest = _fix_bare_hash_symbol_values(rest)
            if rest.startswith('{') and rest.endswith('}') and len(rest) > 60:
                inner = rest[1:-1].strip()
                rest = _format_hash_multiline(inner, base=indent + '  ')
            lines.append(f'{indent}scope :{name}, {rest}')
            continue
        lines.append(line)
    return '\n'.join(lines)


def _fix_bare_hash_symbol_values(code: str) -> str:
    def repl(m):
        val = m.group(2)
        if val in RUBY_LITERALS:
            return m.group(0)
        return f'{m.group(1)}:{val}{m.group(3)}'
    return RE_BARE_HASH_SYM_VAL.sub(repl, code)


def _flatten_multi_option_assoc_hashes(code: str) -> str:
    """belongs_to :x, { a: 1, b: 2 } 格式化为多行选项 (保留括号时)。"""
    lines = []
    for line in code.splitlines():
        m = re.match(
            r'^(\s*(?:belongs_to|has_many|has_one) :\w+, )\{ (.+) \}\s*$', line,
        )
        if m and m.group(2).count(':') >= 2:
            indent = re.match(r'^(\s*)', line).group(1) + '  '
            pairs = _split_args(m.group(2))
            formatted = m.group(1) + "{\n" + ',\n'.join(
                f'{indent}{p.strip()},' for p in pairs[:-1]
            ) + f'\n{indent}{pairs[-1].strip()}\n' + re.match(r'^(\s*)', line).group(1) + '}'
            lines.append(formatted)
        else:
            lines.append(line)
    return '\n'.join(lines)


def _flatten_callback_option_hashes(code: str) -> str:
    return re.sub(
        r'\b(after_\w+|before_\w+) (:\w+), \{ ([^:{}]+: [^,{}]+) \}',
        r'\1 \2, \3',
        code,
    )


def _flatten_single_option_hashes(code: str) -> str:
    lines = []
    for line in code.splitlines():
        m = RE_SINGLE_PAIR_HASH.match(line)
        if m:
            pair = m.group(2)
            pair = RE_BARE_HASH_SYM_VAL.sub(r'\1:\2\3', pair)
            lines.append(m.group(1) + pair)
        else:
            lines.append(line)
    return '\n'.join(lines)


def _symbols_in_select_arrays(code: str) -> str:
    in_select = False
    base_pad = ''
    out = []
    for line in code.splitlines():
        if re.search(r'\bselect\(\[', line):
            in_select = True
            base_pad = re.match(r'^(\s*)', line).group(1) + '    '
            out.append(line)
            continue
        if in_select:
            m = re.match(r'^(\s*)"(\w+)"\s*,?\s*$', line)
            if m:
                sym = ':' + m.group(2)
                if line.rstrip().endswith(','):
                    sym += ','
                out.append(base_pad + sym)
                continue
            if re.search(r'\]\)', line.strip()) or line.strip() == '])':
                in_select = False
        out.append(line)
    return '\n'.join(out)


def _remove_class_empty_rescue(code: str) -> str:
    prev = None
    while prev != code:
        prev = code
        code = RE_CLASS_EMPTY_RESCUE.sub(lambda m: m.group(2), code)
    return code


def _hash_rockets_to_symbols(code: str) -> str:
    code = RE_HASH_KEY_ROCKET.sub(r'\1: ', code)
    code = RE_HASH_CLASS_VAL.sub(r': \1', code)
    # 字符串值若像符号/标识符则转为 :sym (保留 URL/路径等含特殊字符的)
    def sym_val(m):
        val, tail = m.group(1), m.group(2)
        return f': {val}{tail}'
    code = RE_HASH_SYM_VAL.sub(sym_val, code)
    return code


def _beautify_hash_literals_multiline(code: str) -> str:
    """把行内超长 {...} 格式化为多行。"""
    out = []
    for line in code.splitlines():
        if '{' not in line or '=>' in line or len(line) <= 100:
            # 已转 symbol 或不够长
            if '{' in line and len(line) > 100:
                line = _expand_inline_hash(line)
            out.append(line)
            continue
        if '{' in line and len(line) > 80:
            line = _expand_inline_hash(line)
        out.append(line)
    return '\n'.join(out)


def _expand_inline_hash(line: str) -> str:
    """拆分单行 hash { a: 1, b: 2, ... }。"""
    m = re.search(r'\{([^{}]+)\}', line)
    if not m or m.group(1).count(',') < 2:
        return line
    prefix = line[:m.start()]
    suffix = line[m.end():]
    inner = m.group(1)
    indent = re.match(r'^(\s*)', line).group(1) + '  '
    formatted = _format_hash_multiline(inner, base=indent)
    return prefix + formatted + suffix


def _format_hash_multiline(inner: str, base: str) -> str:
    pairs = _split_args(inner)
    if len(pairs) <= 2:
        return '{ ' + inner.strip() + ' }'
    lines = ['{'] + [f'{base}{p.strip()},' for p in pairs[:-1]] + [f'{base}{pairs[-1].strip()}', '}']
    return '\n'.join(lines)


def _symbols_in_attr_lists(code: str) -> str:
    """attr_accessible / attr_accessor 列表中的字符串转符号。"""
    lines = code.splitlines()
    out = []
    in_attr = False
    attr_macros = ('attr_accessible', 'attr_accessor', 'attr_reader', 'attr_writer')
    for line in lines:
        stripped = line.strip()
        if any(stripped.startswith(m) for m in attr_macros):
            in_attr = True
            # 行内参数
            m = re.match(r'^(\s*(?:attr_\w+))\s+(.*)$', line)
            if m and not m.group(2).startswith('\\'):
                parts = _split_args(m.group(2))
                sym = ', '.join(_quote_to_sym(p.strip()) for p in parts)
                out.append(f'{m.group(1)} {sym}')
                in_attr = False
                continue
            out.append(line)
            continue
        if in_attr:
            if stripped.endswith('\\'):
                out.append(line)
                continue
            m = RE_QUOTED_IDENT.match(stripped.rstrip(','))
            if m:
                sym = ':' + m.group(1)
                if stripped.endswith(','):
                    sym += ','
                out.append(re.match(r'^(\s*)', line).group(1) + sym)
                if not stripped.endswith('\\') and not stripped.endswith(','):
                    in_attr = False
                continue
            in_attr = False
        out.append(line)
    return '\n'.join(out)


def _quote_to_sym(token: str) -> str:
    token = token.strip().rstrip(',')
    m = re.match(r'^"(\w+)"$', token)
    return f':{m.group(1)}' if m else token


def _wrap_long_argument_lists(code: str) -> str:
    max_len = 100
    out_lines = []
    for line in code.splitlines():
        if len(line) <= max_len or '(' not in line:
            out_lines.append(line)
            continue
        m = re.match(r'^(\s*)([\w.]+)\((.+)\)\s*(.*)$', line)
        if not m or ',' not in m.group(3):
            out_lines.append(line)
            continue
        indent, head, args, tail = m.groups()
        parts = _split_args(args)
        if len(parts) <= 3:
            out_lines.append(line)
            continue
        inner_pad = indent + '    '
        wrapped = f'{indent}{head}(\n' + ',\n'.join(f'{inner_pad}{p.strip()}' for p in parts)
        wrapped += f'\n{indent})'
        if tail.strip():
            wrapped += ' ' + tail.strip()
        out_lines.append(wrapped)
    return '\n'.join(out_lines)


def _wrap_long_bare_macros(code: str) -> str:
    max_len = 90
    macro_names = '|'.join(re.escape(m) for m in (
        'attr_accessible', 'attr_accessor', 'attr_reader', 'attr_writer',
    ))
    out_lines = []
    for line in code.splitlines():
        if len(line) <= max_len:
            out_lines.append(line)
            continue
        m = re.match(rf'^(\s*)({macro_names})\s+(.+)$', line)
        if not m or ',' not in m.group(3):
            out_lines.append(line)
            continue
        indent, head, args = m.groups()
        parts = _split_args(args)
        if len(parts) <= 4:
            out_lines.append(line)
            continue
        inner_pad = indent + '    '
        wrapped = f'{indent}{head} \\\n' + ',\n'.join(f'{inner_pad}{p.strip()}' for p in parts)
        out_lines.append(wrapped)
    return '\n'.join(out_lines)


def _wrap_select_and_where(code: str) -> str:
    out = []
    for line in code.splitlines():
        if len(line) <= 100:
            out.append(line)
            continue
        m = re.match(r'^(\s*)(select|where|find_by|order|group|having|pluck)\((\[.+\]|\{.+)\)\s*(.*)$', line)
        if not m:
            out.append(line)
            continue
        indent, method, arg, tail = m.groups()
        if arg.startswith('[') and arg.count(',') >= 4:
            inner = arg[1:-1]
            parts = _split_args(inner)
            inner_pad = indent + '    '
            arg = '[\n' + ',\n'.join(
                f'{inner_pad}{_quote_to_sym(p.strip())}' for p in parts
            ) + f'\n{indent}  ]'
        elif arg.startswith('{') and arg.count(',') >= 2:
            inner = arg[1:-1]
            arg = _format_hash_multiline(inner, base=indent + '    ')
        else:
            out.append(line)
            continue
        line = f'{indent}{method}({arg})'
        if tail.strip():
            line += ' ' + tail.strip()
        out.append(line)
    return '\n'.join(out)


def _beautify_inline_select(code: str) -> str:
    """单行 select([\"a\", \"b\"]) 转符号并可选换行。"""
    def repl(m):
        indent, inner = m.group(1), m.group(2)
        parts = [_quote_to_sym(p.strip()) for p in _split_args(inner)]
        if len(parts) <= 4:
            return f'{indent}select([{", ".join(parts)}])'
        inner_pad = indent + '    '
        body = ',\n'.join(f'{inner_pad}{p}' for p in parts)
        return f'{indent}select([\n{body}\n{indent}  ])'
    return re.sub(r'^(\s*)select\(\[([^\]]+)\]\)\s*$', repl, code, flags=re.MULTILINE)


def _remove_empty_rescue_blocks(code: str) -> str:
    prev = None
    while prev != code:
        prev = code
        code = RE_EMPTY_RESCUE.sub(lambda m: m.group(2), code)
    return code


def _remove_empty_do_blocks(code: str) -> str:
    prev = None
    while prev != code:
        prev = code
        code = RE_EMPTY_DO_BLOCK.sub('', code)
    return code


def _remove_empty_modules(code: str) -> str:
    prev = None
    while prev != code:
        prev = code
        code = RE_EMPTY_MODULE.sub('', code)
    return code


def _fix_each_blocks(code: str) -> str:
    """无块参数的 each/map/select do 补上占位参数。"""
    lines = code.splitlines()
    out = []
    for i, line in enumerate(lines):
        if RE_EACH_BARE.search(line):
            # 根据上下文猜测参数名
            if '.map' in line or '.select' in line or '.find' in line:
                line = line.replace(' do', ' do |item|')
            elif '.each' in line:
                line = line.replace(' do', ' do |item|')
            else:
                line = line.replace(' do', ' do |_item|')
        out.append(line)
    return '\n'.join(out)


def _reindent(code: str) -> str:
    lines = code.splitlines()
    result: List[str] = []
    indent = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append('')
            continue
        first = stripped.split()[0]
        if stripped == '}' or stripped in (']', '])') or re.match(r'^end\b', stripped) or first in CONTINUATION_KEYWORDS:
            indent = max(0, indent - 1)
        elif re.match(r'^\]', stripped):
            indent = max(0, indent - 1)
        result.append('  ' * indent + stripped)
        if stripped.endswith('{') or stripped.endswith('['):
            indent += 1
        elif _opens_block(stripped):
            indent += 1
        elif re.match(r'^end\b', stripped) and re.search(r'\bdo(\s+\|[^|]*\|)?\s*$', stripped):
            indent += 1
        elif first in CONTINUATION_KEYWORDS:
            indent += 1
        elif stripped in (']', '])', '])'):
            indent = max(0, indent - 1)
    return '\n'.join(result)


def _opens_block(line: str) -> bool:
    if re.search(r'\bdo(\s+\|[^|]*\|)?\s*$', line):
        return True
    first = line.split()[0] if line.split() else ''
    return first in INDENT_KEYWORDS


def _fix_attr_continuation_indent(code: str) -> str:
    """attr_accessible \\ 续行参数缩进对齐。"""
    lines = code.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        is_attr_head = (
            re.search(r'\battr_(?:accessible|accessor|reader|writer)\b', line)
            and (line.rstrip().endswith('\\') or re.search(r'\battr_\w+\s*$', line.strip()))
        )
        if is_attr_head:
            out.append(line)
            base = re.match(r'^(\s*)', line).group(1)
            pad = base + '    '
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip():
                    out.append(nxt)
                    i += 1
                    continue
                if re.match(r'^\s*:\w+', nxt.strip()):
                    sym = nxt.strip()
                    out.append(pad + sym)
                    i += 1
                    continue
                break
            continue
        out.append(line)
        i += 1
    return '\n'.join(out)


def _separate_methods(code: str) -> str:
    code = re.sub(r'\n(  def )', r'\n\n\1', code)
    code = re.sub(r'\n(  def self\.)', r'\n\n\1', code)
    return code


def _separate_associations(code: str) -> str:
    """关联宏与方法/彼此间增加空行。"""
    lines = code.splitlines()
    out = []
    prev_kind = None
    for line in lines:
        kind = _line_kind(line)
        if kind == 'assoc' and prev_kind in ('assoc', 'method', 'end', None) and out and out[-1].strip():
            if prev_kind != 'blank' and kind != prev_kind:
                out.append('')
        if kind == 'method' and prev_kind == 'assoc' and out and out[-1].strip():
            out.append('')
        out.append(line)
        prev_kind = kind if kind != 'blank' else prev_kind
    return '\n'.join(out)


def _line_kind(line: str) -> str:
    if not line.strip():
        return 'blank'
    if re.match(r'^\s*def ', line):
        return 'method'
    if re.match(r'^\s*(belongs_to|has_many|has_one|scope|validates|before_|after_)', line):
        return 'assoc'
    if line.strip() == 'end':
        return 'end'
    return 'code'


def _collapse_blank_lines(code: str) -> str:
    return re.sub(r'\n{3,}', '\n\n', code)


def _format_hash_spacing(code: str) -> str:
    """{key: val} -> { key: val }"""
    code = re.sub(r'\{(\S)', r'{ \1', code)
    code = re.sub(r'(\S)\}', r'\1 }', code)
    code = re.sub(r',(\S)', r', \1', code)
    return code


def _trim_trailing_space(code: str) -> str:
    return '\n'.join(line.rstrip() for line in code.splitlines())


def _split_args(s: str) -> List[str]:
    parts, cur, depth = [], [], 0
    in_str, esc = None, False
    for ch in s:
        if in_str:
            cur.append(ch)
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == in_str:
                in_str = None
            continue
        if ch in '"\'':
            in_str = ch
            cur.append(ch)
            continue
        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append(''.join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append(''.join(cur))
    return parts
