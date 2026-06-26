from typing import List, Optional

from desast.helpers import collect_list
from desast.node import Node

_lazy_render_fn = None


def _lazy_render(node, level=0):
    global _lazy_render_fn
    if _lazy_render_fn is None:
        from desast.render import render as _lazy_render_fn_impl
        _lazy_render_fn = _lazy_render_fn_impl
    return _lazy_render_fn(node, level)


def format_method_args(scope_node: Optional[Node]) -> List[str]:
    """从 NODE_SCOPE 的 NODE_ARGS 正确重建形参列表 (pre/opt/rest/post/block)。
    无 NODE_ARGS 时回退 nd_tbl；NODE_ARGS 解析结果为空但 nd_tbl 非空时也回退 nd_tbl。"""
    if not isinstance(scope_node, Node):
        return []
    tbl_str = scope_node.attrs.get('nd_tbl')
    tbl = [a.strip().lstrip(':') for a in tbl_str.split(',') if a.strip()] \
        if isinstance(tbl_str, str) else []
    args_node = scope_node.attrs.get('nd_args')
    if not isinstance(args_node, Node) or args_node.type != 'NODE_ARGS':
        return tbl  # 回退旧行为
    a = args_node.attrs
    pre_n = a.get('nd_ainfo->pre_args_num') or 0
    post_n = a.get('nd_ainfo->post_args_num') or 0
    pre_n = pre_n if isinstance(pre_n, int) else 0
    post_n = post_n if isinstance(post_n, int) else 0

    result: List[str] = []
    idx = 0
    for _ in range(pre_n):  # 必选前置参数
        if idx < len(tbl):
            result.append(tbl[idx]); idx += 1
    opt = a.get('nd_ainfo->opt_args')  # 可选参数(带默认值)
    while isinstance(opt, Node) and opt.type == 'NODE_OPT_ARG':
        lasgn = opt.attrs.get('nd_body')
        if isinstance(lasgn, Node):
            name = str(lasgn.attrs.get('nd_vid') or '').lstrip(':')
            dval = lasgn.attrs.get('nd_value')
            ds = _lazy_render(dval, 0).strip() if isinstance(dval, Node) else 'nil'
            if not ds:
                ds = 'nil'
            if name:
                result.append(f"{name} = {ds}"); idx += 1
        opt = opt.attrs.get('nd_next')
    rest = a.get('nd_ainfo->rest_arg')  # *args
    if isinstance(rest, str) and rest:
        result.append('*' + rest.lstrip(':')); idx += 1
    for _ in range(post_n):  # 必选后置参数
        if idx < len(tbl):
            result.append(tbl[idx]); idx += 1
    blk = a.get('nd_ainfo->block_arg')  # &block
    if isinstance(blk, str) and blk:
        result.append('&' + blk.lstrip(':'))
    # NODE_ARGS 解析为空但 nd_tbl 有符号时回退 (如 pre_args_num:0 而 nd_tbl 仍有形参名)
    if not result and tbl:
        return tbl
    return result


def render_arg_list(args_node: Optional[Node]) -> str:
    """把方法调用/数组的参数 NODE_ARRAY 用 collect_list 正确遍历, 每个元素只渲染一次,
    避免"render(nd_head)+迭代children"反模式导致的重复渲染/裸@幻影。"""
    if not isinstance(args_node, Node):
        return ''
    if args_node.type in ('NODE_ARRAY', 'NODE_LIST'):
        items = []
        for e in collect_list(args_node):
            s = _lazy_render(e, 0)
            if s is not None and s != '':
                items.append(s)
        return ', '.join(items)
    # 参数拼接 + splat: foo(a, b, *rest)
    if args_node.type == 'NODE_ARGSCAT':
        parts = []
        head = args_node.attrs.get('nd_head')
        body = args_node.attrs.get('nd_body')
        if isinstance(head, Node):
            hs = render_arg_list(head)
            if hs:
                parts.append(hs)
        if isinstance(body, Node):
            parts.append('*' + _lazy_render(body, 0))
        return ', '.join(parts)
    # 参数追加单值: foo(*a, b)
    if args_node.type == 'NODE_ARGSPUSH':
        parts = []
        head = args_node.attrs.get('nd_head')
        body = args_node.attrs.get('nd_body')
        if isinstance(head, Node):
            hs = render_arg_list(head)
            if hs:
                parts.append(hs)
        if isinstance(body, Node):
            parts.append(_lazy_render(body, 0))
        return ', '.join(parts)
    # 裸 splat: foo(*x)
    if args_node.type == 'NODE_SPLAT':
        return '*' + _lazy_render(args_node.attrs.get('nd_head'), 0)
    # block-pass: foo(args, &block) / foo(&:sym)
    if args_node.type == 'NODE_BLOCK_PASS':
        head = args_node.attrs.get('nd_head')  # 普通参数
        body = args_node.attrs.get('nd_body')  # & 之后的块表达式
        parts = []
        if isinstance(head, Node):
            hs = render_arg_list(head)
            if hs:
                parts.append(hs)
        if isinstance(body, Node):
            if body.type == 'NODE_LIT':  # &:sym (符号转 proc)
                parts.append('&:' + str(body.attrs.get('nd_lit') or '').lstrip(':'))
            else:
                parts.append('&' + _lazy_render(body, 0))
        return ', '.join(parts)
    return _lazy_render(args_node, 0)
