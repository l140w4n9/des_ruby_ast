from typing import Optional

from desast.args import format_method_args, render_arg_list
from desast.beautify import (
    BINARY_OPS,
    RAILS_MACROS_NO_PAREN,
    ensure_block_indent,
    format_def_signature,
)
from desast.helpers import collect_list, esc_str_content, find_child
from desast.node import Node

def render_array_as_block(node: Node, level: int) -> str:
    """将 NODE_ARRAY 渲染为多行语句块"""
    parts = []
    head = node.attrs.get('nd_head')
    if isinstance(head, Node):
        rendered = render(head, level)
        if rendered:
            parts.append(rendered)
    for c in node.children:
        rendered = render(c, level)
        if rendered:
            parts.append(rendered)
    return "\n".join(parts)


def render(node: Optional[Node], level=0) -> str:
    if node is None:
        return ''

    # 取消_processed判断，防止误过滤
    if hasattr(node, '_processed'):
        return ''
    node._processed = True

    t = node.type

    # 基础容器节点
    if t == 'NODE_SCOPE':
        parts = []
        body = node.attrs.get('nd_body')
        if isinstance(body, Node):
            parts.append(render(body, level))
        else:
            for c in node.children:
                parts.append(render(c, level))
        return '\n'.join([p for p in parts if p])

    # 局部变量引用
    if t == 'NODE_LVAR':
        vid = node.attrs.get('nd_vid') or ''
        return vid.lstrip(':')

    # 类定义
    if t == 'NODE_CLASS':
        name = None
        cpath = node.attrs.get('nd_cpath')
        if isinstance(cpath, Node):
            name = render(cpath, 0)
        if not name:
            for c in node.children:
                if c.type in ('NODE_COLON2', 'NODE_COLON3', 'NODE_CONST'):
                    name = render(c, 0)
                    break
        if not name:
            name = 'UNKNOWN_CLASS'

        sup = None
        sattr = node.attrs.get('nd_super')
        if isinstance(sattr, Node):
            sup = render(sattr, 0)
        else:
            for c in node.children:
                if c.type == 'NODE_COLON2' and 'nd_mid' in c.attrs:
                    sup = render(c, 0)
                    break

        body_node = node.attrs.get('nd_body') or find_child(
            node, ['NODE_SCOPE', 'NODE_BLOCK'])
        body = render(body_node, level +
                      1) if isinstance(body_node, Node) else ''

        out = f"{'  ' * level}class {name}"
        if sup:
            out += f" < {sup}"
        out += "\n"
        if body:
            out += body + "\n"
        out += f"{'  ' * level}end"
        return out

    # NODE_DEFN - 方法定义
    if t == 'NODE_DEFN':
        mid = node.attrs.get('nd_mid') or 'unknown_method'
        defn = node.attrs.get('nd_defn') or find_child(node, ['NODE_SCOPE'])

        args = format_method_args(defn) if isinstance(defn, Node) else []

        body = ''
        if isinstance(defn, Node):
            body_node = defn.attrs.get('nd_body')
            if isinstance(body_node, Node):
                if body_node.type == 'NODE_ARRAY':
                    body = render_array_as_block(body_node, level + 1)
                elif any(c.type == 'NODE_RESCUE' for c in defn.children):
                    body = render(defn, level)
                else:
                    body = render(defn, level + 1)

        out = format_def_signature(mid, args, level) + "\n"
        if body:
            out += body + "\n"
        out += f"{'  ' * level}end"
        return out

    # 无接收者的方法调用 (如 `before`, `after`)
    if t == 'NODE_VCALL':
        mid = node.attrs.get('nd_mid') or ''
        return f"{'  ' * level}{mid}"

    # NODE_IASGN - 实例变量赋值
    if t == 'NODE_IASGN':
        vid = node.attrs.get('nd_vid') or ''
        var_name = f"@{vid.lstrip('@')}" if not vid.startswith('@') else vid
        val = node.attrs.get('nd_value')
        if val is None:
            return f"{'  ' * level}{var_name} = nil"
        val_s = render(val, 0) if isinstance(val, Node) else str(val)
        if not val_s.strip():
            val_s = 'nil'
        return f"{'  ' * level}{var_name} = {val_s}"

    # 属性赋值 (如 obj.attr = value, obj[key] = value)
    if t == 'NODE_ATTRASGN':
        recv = node.attrs.get('nd_recv')  # 接收者对象
        mid = node.attrs.get('nd_mid') or ''  # 方法名
        args = node.attrs.get('nd_args')  # 参数（包括赋值的值）

        # 处理接收者
        recv_s = ''
        if isinstance(recv, Node):
            recv_s = render(recv, 0)
            # 特殊处理实例变量接收者
            if recv.type == 'NODE_IVAR':
                recv_s = f"@{recv_s.lstrip('@')}"

        # 处理参数（通常是数组，最后一个元素是赋值的值）
        assign_value = ''
        attr_args = []

        if isinstance(args, Node):
            if args.type in ('NODE_ARRAY', 'NODE_LIST'):
                # 用 collect_list 正确遍历: 最后一个元素是赋值的值, 其余是下标/属性参数
                all_args = [render(e, 0) for e in collect_list(args)]
                if all_args:
                    assign_value = all_args[-1]
                    attr_args = all_args[:-1]
            else:
                # 单个参数，就是赋值的值
                assign_value = render(args, 0)

        # 根据方法名确定赋值类型
        if mid == '[]=' and attr_args:
            # 数组/哈希赋值: obj[key] = value
            if recv_s and assign_value:
                keys = ', '.join(attr_args)
                return f"{'  ' * level}{recv_s}[{keys}] = {assign_value}"
            elif recv_s and not assign_value:
                # 可能是删除操作或者设置为nil
                keys = ', '.join(attr_args)
                return f"{'  ' * level}{recv_s}[{keys}] = nil"
            else:
                keys = ', '.join(attr_args) if attr_args else ''
                return f"{'  ' * level}[{keys}] = {assign_value or 'nil'}"
        elif mid.endswith('='):
            # 属性赋值: obj.attr = value
            attr_name = mid[:-1]  # 去掉末尾的 '='
            if recv_s:
                return f"{'  ' * level}{recv_s}.{attr_name} = {assign_value or 'nil'}"
            else:
                return f"{'  ' * level}{attr_name} = {assign_value or 'nil'}"
        else:
            # 其他情况，按一般方法调用处理
            if recv_s:
                all_args_str = ', '.join(
                    attr_args + [assign_value]) if attr_args else (assign_value or '')
                return f"{'  ' * level}{recv_s}.{mid}({all_args_str})"
            else:
                all_args_str = ', '.join(
                    attr_args + [assign_value]) if attr_args else (assign_value or '')
                return f"{'  ' * level}{mid}({all_args_str})"

    if t == 'NODE_LASGN':
        vid = node.attrs.get('nd_vid') or ''
        val = node.attrs.get('nd_value')

        # 特殊处理异常捕获的情况 (NODE_ERRINFO)
        if isinstance(val, Node) and val.type == 'NODE_ERRINFO':
            return f" => {vid}"

        # 普通局部变量赋值
        val_s = render(val, 0) if isinstance(val, Node) else ''
        return f"{'  ' * level}{vid} = {val_s}"

    # rescue语句
    if t == 'NODE_RESCUE':
        begin_body = node.attrs.get('nd_head')
        rescue_bodies = []
        else_body = node.attrs.get('nd_else')

        begin_s = render(begin_body, level + 1) if begin_body else ''

        for c in node.children:
            if c.type == 'NODE_RESBODY':
                rescue_s = render(c, level + 1)
                if rescue_s:
                    rescue_bodies.append(rescue_s)

        else_s = render(else_body, level + 1) if else_body else ''

        out = f"{'  ' * level}begin\n{begin_s}"
        if rescue_bodies:
            out += "\n" + "\n".join(rescue_bodies)
        if else_s:
            out += f"\n{'  ' * level}else\n{else_s}"
        out += f"\n{'  ' * level}end"
        return out

    if t == 'NODE_RESBODY':
        exc_var = None
        body = None

        for c in node.children:
            if c.type == 'NODE_LASGN':
                exc_var = c.attrs.get('nd_vid')
                break

        for c in node.children:
            if c.type == 'NODE_BLOCK':
                body = c
                break

        body_s = render(body, level + 1) if body else ''

        out = f"{'  ' * level}rescue"
        if exc_var:
            out += f" => {exc_var}"
        if body_s:
            out += f"{body_s}"
        return out

    # NODE_MODULE
    if t == 'NODE_MODULE':
        name = None
        cpath = node.attrs.get('nd_cpath')
        if isinstance(cpath, Node):
            name = render(cpath, 0)
        if not name:
            for c in node.children:
                if c.type in ('NODE_COLON2', 'NODE_COLON3', 'NODE_CONST'):
                    name = render(c, 0)
                    break
        if not name:
            name = 'UNKNOWN_MODULE'

        body_node = node.attrs.get('nd_body') or find_child(
            node, ['NODE_SCOPE', 'NODE_BLOCK'])
        body = render(body_node, level +
                      1) if isinstance(body_node, Node) else ''

        out = f"{'  ' * level}module {name}\n"
        if body:
            out += body + "\n"
        out += f"{'  ' * level}end"
        return out

    # NODE_COLON2 (常量路径)
    if t == 'NODE_COLON2':
        mid = node.attrs.get('nd_mid')
        head = node.attrs.get('nd_head')

        if isinstance(head, Node):
            if head.type == 'NODE_COLON2':
                head_s = render(head, 0) + '::'
            elif head.type == 'NODE_CONST':
                head_s = render(head, 0) + '::'
            else:
                head_s = ''
        else:
            for c in node.children:
                if c.type in ('NODE_CONST', 'NODE_COLON2'):
                    head_s = render(c, 0) + '::'
                    break
            else:
                head_s = ''

        return head_s + (mid or 'UNKNOWN')

    # NODE_COLON3 (顶级常量引用 ::Const, 此前缺失导致渲染成空)
    if t == 'NODE_COLON3':
        mid = node.attrs.get('nd_mid')
        return '::' + str(mid or 'UNKNOWN').lstrip(':')

    # 常量
    if t == 'NODE_CONST':
        return node.attrs.get('nd_vid') or 'CONST'

    # NODE_CALL
    # 方法调用
    if t == 'NODE_CALL':
        mid = node.attrs.get('nd_mid') or ''
        recv = node.attrs.get('nd_recv')
        args = node.attrs.get('nd_args')

        # 处理接收者
        recv_s = ''
        if isinstance(recv, Node):
            recv_s = render(recv, 0)
            # 特殊处理实例变量接收者
            if recv.type == 'NODE_IVAR':
                recv_s = f"@{recv_s.lstrip('@')}"

        # 处理参数 (用 collect_list 正确遍历 cons-list, 每元素只渲染一次)
        args_s = render_arg_list(args)

        # 二元运算符: obj.method(arg) -> obj method arg
        if mid in BINARY_OPS and recv_s and args_s:
            call_str = f"{recv_s} {mid} {args_s}"
        # 特殊处理[]方法调用（数组/哈希访问）
        elif mid == '[]':
            if recv_s and args_s:
                call_str = f"{recv_s}[{args_s}]"
            else:
                call_str = f"{recv_s}[]" if recv_s else "[]"
        # 特殊处理HTTP方法
        elif mid.lower() in ['post', 'get', 'put', 'delete', 'patch', 'head', 'options'] and not recv_s:
            if args_s:
                return f"{'  ' * level}{mid} {args_s} do"
            else:
                return f"{'  ' * level}{mid} do"
        # 特殊处理Grape DSL方法
        elif mid in ['desc', 'params', 'requires', 'optional', 'namespace'] and not recv_s:
            if mid == 'params':
                return f"{'  ' * level}params do"
            elif mid == 'namespace':
                if args_s:
                    return f"{'  ' * level}namespace {args_s} do"
                else:
                    return f"{'  ' * level}namespace do"
            else:
                if args_s:
                    return f"{'  ' * level}{mid} {args_s}"
                else:
                    return f"{'  ' * level}{mid}"
        else:
            # 构建一般方法调用字符串
            if recv_s:
                if args_s:
                    call_str = f"{recv_s}.{mid}({args_s})"
                else:
                    call_str = f"{recv_s}.{mid}"
            else:
                if args_s:
                    call_str = f"{mid}({args_s})"
                else:
                    call_str = f"{mid}"

        # 根据上下文决定是否添加缩进
        if level > 0:
            return f"{'  ' * level}{call_str}"
        else:
            return call_str

    # 无接收者函数调用（DSL、普通方法）
    if t == 'NODE_FCALL':
        mid = node.attrs.get('nd_mid') or ''
        args = node.attrs.get('nd_args')

        # 处理参数 (用 collect_list 正确遍历 cons-list)
        args_s = render_arg_list(args)

        # 无接收者的 []/[]= = 隐式 self 下标 (ActiveRecord self[attr])
        if mid == '[]':
            return f"{'  ' * level}self[{args_s}]"
        if mid == '[]=':
            all_a = [render(e, 0) for e in collect_list(args)] if isinstance(args, Node) else []
            if len(all_a) >= 2:
                return f"{'  ' * level}self[{', '.join(all_a[:-1])}] = {all_a[-1]}"

        # DSL 方法列表（需要块的方法）
        dsl_with_block = ['post', 'get', 'put', 'delete',
                          'patch', 'head', 'options', 'params', 'namespace']
        # DSL 方法列表（不需要块的方法）
        dsl_no_block = ['desc', 'requires', 'optional']
        # Ruby特殊方法
        ruby_special = ['lambda', 'proc', 'puts', 'print', 'p']

        if mid in dsl_with_block:
            if args_s:
                return f"{'  ' * level}{mid} {args_s}"
            else:
                return f"{'  ' * level}{mid}"
        elif mid in dsl_no_block:
            if args_s:
                return f"{'  ' * level}{mid} {args_s}"
            else:
                return f"{'  ' * level}{mid}"
        elif mid in ruby_special:
            # 特殊处理Ruby内建方法，如lambda
            if mid == 'lambda':
                return f"{'  ' * level}lambda"
            else:
                if args_s:
                    return f"{'  ' * level}{mid}({args_s})"
                else:
                    return f"{'  ' * level}{mid}"
        else:
            # 一般函数调用
            if mid in RAILS_MACROS_NO_PAREN:
                if args_s:
                    return f"{'  ' * level}{mid} {args_s}"
                return f"{'  ' * level}{mid}"
            if args_s:
                return f"{'  ' * level}{mid}({args_s})"
            else:
                return f"{'  ' * level}{mid}"

    # 实例变量引用
    if t == 'NODE_IVAR':
        vid = node.attrs.get('nd_vid') or ''
        return f"@{vid.lstrip('@')}"

    # 全局变量引用
    if t == 'NODE_GVAR':
        # MRI dump 用 nd_entry (如 :$redis), 老逻辑误用 nd_vid 导致只剩 '$'
        vid = node.attrs.get('nd_vid') or node.attrs.get('nd_entry') or ''
        return f"${str(vid).lstrip('$').lstrip(':')}"

    # 类变量引用
    if t == 'NODE_CVAR':
        vid = node.attrs.get('nd_vid') or ''
        return f"@@{vid.lstrip('@')}"

    # NODE_DVAR - 动态变量
    if t == 'NODE_DVAR':
        vid = node.attrs.get('nd_vid')
        name = vid.lstrip(':') if isinstance(vid, str) else (str(vid) if vid else '')
        return f"{'  ' * level}{name}" if level > 0 else name

    # NODE_DASGN_CURR - 动态作用域变量赋值
    if t == 'NODE_DASGN_CURR':
        vid = node.attrs.get('nd_vid') or ''
        val = node.attrs.get('nd_value')
        if val is None:
            return f"{'  ' * level}{vid} = nil"
        val_s = render(val, 0) if isinstance(val, Node) else str(val)
        if not val_s.strip():
            val_s = 'nil'
        return f"{'  ' * level}{vid} = {val_s}"

    # NODE_ITER - 迭代器/块结构 (method do...end 或 lambda { ... })
    if t == 'NODE_ITER':
        iter_node = node.attrs.get('nd_iter')  # 迭代调用的方法
        body_node = node.attrs.get('nd_body')  # 块体内容

        # 渲染迭代器方法调用
        iter_s = render(iter_node, level) if iter_node else ''

        # 渲染块体
        body_s = render(body_node, level + 1) if body_node else ''

        # 判断是否是lambda类型
        is_lambda = (isinstance(iter_node, Node) and
                     iter_node.type == 'NODE_FCALL' and
                     iter_node.attrs.get('nd_mid') == 'lambda')

        if is_lambda:
            # lambda使用花括号语法
            if body_s:
                # 检查是否有参数
                args_part = ''
                if isinstance(body_node, Node):
                    args_node = body_node.attrs.get('nd_args')
                    if isinstance(args_node, Node) and args_node.type == 'NODE_ARGS':
                        # 处理lambda参数
                        pre_args_num = args_node.attrs.get(
                            'nd_ainfo->pre_args_num', 0)
                        if pre_args_num > 0:
                            # 从符号表中获取参数名
                            if isinstance(body_node, Node):
                                tbl = body_node.attrs.get('nd_tbl', '')
                                if isinstance(tbl, str) and tbl:
                                    args_list = [arg.strip().lstrip(
                                        ':') for arg in tbl.split(',')][:pre_args_num]
                                    if args_list:
                                        args_part = f"|{', '.join(args_list)}| "

                return f"{iter_s} {{ {args_part}{body_s} }}"
            else:
                return f"{iter_s} {{ }}"
        else:
            # 普通的do...end块
            if iter_s and body_s:
                # 确保迭代器调用后面有 do
                if not iter_s.strip().endswith(' do') and not iter_s.strip().endswith('do'):
                    iter_s += ' do'
                return f"{iter_s}\n{body_s}\n{'  ' * level}end"
            elif iter_s:
                # 只有迭代器调用，没有块体
                if not iter_s.strip().endswith(' do') and not iter_s.strip().endswith('do'):
                    iter_s += ' do'
                return f"{iter_s}\n{'  ' * level}end"
            elif body_s:
                # 只有块体，没有迭代器（不太常见）
                return body_s
            else:
                return ''

    # NODE_STR
    if t == 'NODE_STR':
        lit = node.attrs.get('nd_lit')
        if lit is None:
            lit = ''
        return '"' + esc_str_content(lit) + '"'

    # NODE_DSTR - 动态字符串（字符串插值）
    if t == 'NODE_DSTR':
        # MRI 结构: nd_lit=首段字面量; nd_next->nd_head=首个分段(EVSTR/STR);
        # nd_next->nd_next=剩余分段组成的 cons-list NODE_ARRAY。
        def render_dstr_seg(seg) -> str:
            if not isinstance(seg, Node):
                return ''
            if seg.type == 'NODE_STR':
                return esc_str_content(seg.attrs.get('nd_lit') or '')
            if seg.type == 'NODE_EVSTR':
                body = seg.attrs.get('nd_body')
                inner = render(body, 0).strip() if isinstance(body, Node) else ''
                return '#{' + inner + '}'
            # 兜底: 当作插值表达式
            inner = render(seg, 0).strip()
            return '#{' + inner + '}' if inner else ''

        buf = esc_str_content(node.attrs.get('nd_lit') or '')
        first = node.attrs.get('nd_next->nd_head')
        if isinstance(first, Node):
            buf += render_dstr_seg(first)
        rest = node.attrs.get('nd_next->nd_next')
        for seg in collect_list(rest) if isinstance(rest, Node) else []:
            buf += render_dstr_seg(seg)

        final_str = '"' + buf + '"'
        return ('  ' * level + final_str) if level > 0 else final_str

    # NODE_EVSTR - 字符串插值表达式 #{}
    if t == 'NODE_EVSTR':
        body = node.attrs.get('nd_body')
        if isinstance(body, Node):
            # 递归渲染插值内容
            inner = render(body, 0)

            # 处理不同类型的插值内容
            if body.type == 'NODE_STR':
                # 如果是字符串字面量，去掉外层引号
                if inner.startswith('"') and inner.endswith('"'):
                    inner = inner[1:-1]
                elif inner.startswith("'") and inner.endswith("'"):
                    inner = inner[1:-1]
            elif body.type == 'NODE_LVAR':
                # 局部变量，直接使用
                pass
            elif body.type == 'NODE_IVAR':
                # 实例变量，确保有@前缀
                if not inner.startswith('@'):
                    inner = f"@{inner}"
            elif body.type == 'NODE_CALL':
                # 方法调用，保持原样
                pass
            elif body.type in ('NODE_GVAR', 'NODE_CVAR'):
                # 全局变量或类变量
                pass

            # 直接返回内容，不要嵌套#{}标记（因为会在上层处理）
            return inner
        else:
            # 没有body，返回空字符串
            return ""

    # 逻辑或操作
    if t == 'NODE_OR':
        first = node.attrs.get('nd_1st')
        second = node.attrs.get('nd_2nd')
        first_s = render(first, 0).strip() if isinstance(first, Node) else ''
        second_s = render(second, 0).strip(
        ) if isinstance(second, Node) else ''

        or_expr = f"{first_s} || {second_s}"
        return f"{'  ' * level}{or_expr}" if level > 0 else or_expr

    # 逻辑与操作 (&& 或 and)
    if t == 'NODE_AND':
        first = node.attrs.get('nd_1st')
        second = node.attrs.get('nd_2nd')
        first_s = render(first, 0).strip() if isinstance(first, Node) else ''
        second_s = render(second, 0).strip() if isinstance(second, Node) else ''

        and_expr = f"{first_s} && {second_s}"
        return f"{'  ' * level}{and_expr}" if level > 0 else and_expr

    # NODE_IF
    if t == 'NODE_IF':
        cond = node.attrs.get('nd_cond')
        then_body = node.attrs.get('nd_body')
        else_body = node.attrs.get('nd_else')

        cond_s = render(cond, 0) if cond else 'false'
        then_s = render(then_body, level + 1) if then_body else ''
        else_s = render(else_body, level + 1) if else_body else ''

        out = f"{'  ' * level}if {cond_s}"
        if then_s:
            out += f"\n{then_s}"
        if else_s:
            out += f"\n{'  ' * level}else\n{else_s}"
        out += f"\n{'  ' * level}end"
        return out

    # NODE_CASE - case/when 语句
    if t == 'NODE_CASE':
        head = node.attrs.get('nd_head')  # case 表达式
        body = node.attrs.get('nd_body')  # when 子句

        head_s = render(head, 0) if head else ''

        out = f"{'  ' * level}case {head_s}" if head_s else f"{'  ' * level}case"

        # 处理 when 子句
        if isinstance(body, Node):
            when_parts = []
            current = body

            # 遍历所有 when 子句（通常是链式结构）
            while current:
                if current.type == 'NODE_WHEN':
                    when_s = render(current, level)
                    if when_s:
                        when_parts.append(when_s)
                    current = current.attrs.get('nd_next')
                else:
                    # 如果不是 NODE_WHEN，可能是 else 子句
                    else_s = render(current, level + 1)
                    if else_s:
                        when_parts.append(f"{'  ' * level}else\n{else_s}")
                    break

            if when_parts:
                out += "\n" + "\n".join(when_parts)

        out += f"\n{'  ' * level}end"
        return out

    # NODE_WHEN - when 子句
    if t == 'NODE_WHEN':
        # when 条件可能在 nd_head 或 nd_args 中
        args = node.attrs.get('nd_head') or node.attrs.get('nd_args')
        body = node.attrs.get('nd_body')  # when 主体
        next_when = node.attrs.get('nd_next')  # 下一个 when 或 else

        # 处理 when 条件
        when_conditions = []
        if isinstance(args, Node):
            if args.type == 'NODE_ARRAY':
                # 多个条件
                head = args.attrs.get('nd_head')
                if isinstance(head, Node):
                    when_conditions.append(render(head, 0))
                for c in args.children:
                    cond = render(c, 0)
                    if cond:
                        when_conditions.append(cond)
            else:
                # 单个条件
                cond = render(args, 0)
                if cond:
                    when_conditions.append(cond)

        # 构建 when 行
        when_line = f"{'  ' * level}when {', '.join(when_conditions)}" if when_conditions else f"{'  ' * level}when"

        # 处理 when 主体
        body_s = render(body, level + 1) if body else ''

        out = when_line
        if body_s:
            out += f"\n{body_s}"

        return out

    # NODE_LASGN - 局部变量赋值
    if t == 'NODE_LASGN':
        vid = node.attrs.get('nd_vid') or ''
        val = node.attrs.get('nd_value')
        if val is None:
            return f"{'  ' * level}{vid} = nil"
        elif isinstance(val, Node) and val.type == 'NODE_ERRINFO':
            return f" => {vid}"
        val_s = render(val, 0) if isinstance(val, Node) else str(val)
        if not val_s.strip():
            val_s = 'nil'
        return f"{'  ' * level}{vid} = {val_s}"

    # NODE_HASH
    if t == 'NODE_HASH':
        # MRI: NODE_HASH.nd_head 指向一条扁平 cons-list, 元素按 key,value,key,value 交替
        arr = node.attrs.get('nd_head')
        elems = collect_list(arr) if isinstance(arr, Node) else []
        pairs = []
        for i in range(0, len(elems) - 1, 2):
            k_node, v_node = elems[i], elems[i + 1]
            value = render(v_node, 0)
            pairs.append(f"{render(k_node, 0)} => {value}")

        if not pairs:
            return '{}'

        # 根据上下文决定是否添加缩进
        hash_content = '{' + ', '.join(pairs) + '}'
        if level > 0:
            return '  ' * level + hash_content
        else:
            return hash_content

    # NODE_ARRAY
    if t == 'NODE_ARRAY':
        if node.parent and node.parent.type in ('NODE_SCOPE', 'NODE_BLOCK', 'NODE_IF', 'NODE_DEFN'):
            return render_array_as_block(node, level)
        else:
            # 数组字面量值上下文: 用 collect_list 正确遍历并补回 [ ] 括号
            parts = []
            for e in collect_list(node):
                rendered = render(e, 0)
                if rendered:
                    parts.append(rendered)
            return '[' + ', '.join(parts) + ']'

    # NODE_ZARRAY - 空数组
    if t == 'NODE_ZARRAY':
        return '[]'

    # NODE_LIT
    if t == 'NODE_LIT':
        lit = node.attrs.get('nd_lit')
        if isinstance(lit, str):
            if lit.startswith(':'):
                return lit  # 返回符号
            elif lit.startswith('"') and lit.endswith('"'):
                return lit  # 返回字符串字面量
            elif lit.startswith("'") and lit.endswith("'"):
                return lit  # 返回字符串字面量
            else:
                return f'"{lit}"'  # 包装成字符串
        return str(lit)

    # NODE_BLOCK
    if t == 'NODE_BLOCK':
        parts = []
        current = node
        while current:
            head = current.attrs.get('nd_head')
            if head:
                rendered = render(head, 0)
                if rendered:
                    parts.append(ensure_block_indent(rendered, level))
            current = current.attrs.get('nd_next')
        return '\n'.join(filter(lambda x: x.strip(), parts))

    # NODE_DEFS
    if t == 'NODE_DEFS':
        recv = node.attrs.get('nd_recv')
        mid = node.attrs.get('nd_mid') or 'unknown_method'
        defn = node.attrs.get('nd_defn') or find_child(node, ['NODE_SCOPE'])

        # 处理接收者（保持与NODE_DEFN一致的风格）
        recv_s = 'self' if isinstance(recv, Node) and recv.type == 'NODE_SELF' else (
            render(recv, 0) if isinstance(recv, Node) else ''
        )

        args = format_method_args(defn) if isinstance(defn, Node) else []

        # 处理方法体（完全复用NODE_DEFN的逻辑）
        body = ''
        if isinstance(defn, Node):
            if any(c.type == 'NODE_RESCUE' for c in defn.children):
                # 包含rescue时保持当前缩进
                body = render(defn, level)
            else:
                body = render(defn, level + 1)

        # 构建输出（保持相同格式）
        out = format_def_signature(mid, args, level, recv=recv_s) + "\n"
        if body:
            out += body + "\n"
        out += f"{'  ' * level}end"
        return out

    # NODE_ARGS - 方法参数定义
    if t == 'NODE_ARGS':
        # NODE_ARGS用于表示方法的参数信息，通常不直接渲染
        # 参数信息会通过nd_tbl在作用域中处理
        return ''

    if t == 'NODE_SELF':
        return 'self'

    # false 字面量
    if t == 'NODE_FALSE':
        return 'false'

    # true 字面量 (如果将来需要添加)
    if t == 'NODE_TRUE':
        return 'true'

    # nil 字面量 (此前缺失, 导致 {:k => nil} 渲染成空值)
    if t == 'NODE_NIL':
        return 'nil'

    # 块局部变量 (与 LVAR 同样处理, 此前缺失会泄漏 Python repr)
    if t == 'NODE_DVAR':
        return str(node.attrs.get('nd_vid') or '').lstrip(':')

    # NODE_RETURN - return 语句
    if t == 'NODE_RETURN':
        stts = node.attrs.get('nd_stts')
        if stts is None:
            return f"{'  ' * level}return"
        elif isinstance(stts, Node):
            if stts.type == 'NODE_ARRAY':
                parts = []
                head = stts.attrs.get('nd_head')
                if isinstance(head, Node):
                    rendered = render(head, 0)
                    if rendered:
                        parts.append(rendered)
                for c in stts.children:
                    rendered = render(c, 0)
                    if rendered:
                        parts.append(rendered)
                return f"{'  ' * level}return {', '.join(parts)}"
            else:
                return f"{'  ' * level}return {render(stts, 0)}"
        else:
            return f"{'  ' * level}return {stts}"

    # 在 render 函数中添加以下分支逻辑（建议放在 NODE_IF 分支之后）

    # NODE_WHILE - while 循环
    if t == 'NODE_WHILE':
        cond = node.attrs.get('nd_cond')
        body = node.attrs.get('nd_body')

        cond_s = render(cond, 0) if cond else 'false'
        body_s = render(body, level + 1) if body else ''

        out = f"{'  ' * level}while {cond_s}"
        if body_s:
            out += f"\n{body_s}"
        out += f"\n{'  ' * level}end"
        return out

    # NODE_UNTIL - until 循环
    if t == 'NODE_UNTIL':
        cond = node.attrs.get('nd_cond')
        body = node.attrs.get('nd_body')

        cond_s = render(cond, 0) if cond else 'false'
        body_s = render(body, level + 1) if body else ''

        out = f"{'  ' * level}until {cond_s}"
        if body_s:
            out += f"\n{body_s}"
        out += f"\n{'  ' * level}end"
        return out

    # NODE_FOR - for 循环
    if t == 'NODE_FOR':
        iter = node.attrs.get('nd_iter')  # 迭代变量
        var = node.attrs.get('nd_var')  # 循环变量
        body = node.attrs.get('nd_body')  # 循环体

        # 处理迭代变量（通常是数组或范围）
        iter_s = render(iter, 0) if iter else '[]'

        # 处理循环变量
        var_s = ''
        if isinstance(var, Node):
            if var.type == 'NODE_LASGN':
                var_s = var.attrs.get('nd_vid', 'item')
            else:
                var_s = render(var, 0)
        elif isinstance(var, str):
            var_s = var.lstrip(':')

        # 处理循环体
        body_s = render(body, level + 1) if body else ''

        out = f"{'  ' * level}for {var_s} in {iter_s}"
        if body_s:
            out += f"\n{body_s}"
        out += f"\n{'  ' * level}end"
        return out

    # NODE_BREAK - break 语句
    if t == 'NODE_BREAK':
        args = node.attrs.get('nd_stts')  # break 的参数
        if args:
            if isinstance(args, Node):
                if args.type == 'NODE_ARRAY':
                    parts = []
                    head = args.attrs.get('nd_head')
                    if isinstance(head, Node):
                        parts.append(render(head, 0))
                    for c in args.children:
                        parts.append(render(c, 0))
                    args_s = ', '.join(filter(None, parts))
                else:
                    args_s = render(args, 0)
            else:
                args_s = str(args)
            return f"{'  ' * level}break {args_s}"
        return f"{'  ' * level}break"

    # NODE_NEXT - next 语句
    if t == 'NODE_NEXT':
        args = node.attrs.get('nd_stts')  # next 的参数
        if args:
            if isinstance(args, Node):
                if args.type == 'NODE_ARRAY':
                    parts = []
                    head = args.attrs.get('nd_head')
                    if isinstance(head, Node):
                        parts.append(render(head, 0))
                    for c in args.children:
                        parts.append(render(c, 0))
                    args_s = ', '.join(filter(None, parts))
                else:
                    args_s = render(args, 0)
            else:
                args_s = str(args)
            return f"{'  ' * level}next {args_s}"
        return f"{'  ' * level}next"

    # NODE_REDO - redo 语句
    if t == 'NODE_REDO':
        return f"{'  ' * level}redo"

    # NODE_RETRY - retry 语句
    if t == 'NODE_RETRY':
        return f"{'  ' * level}retry"

    # 在 render 函数中添加以下分支逻辑（建议放在 NODE_IASGN 分支之后）

    # NODE_OP_ASGN1 - 运算符赋值（如 ary[0] += 1）
    if t == 'NODE_OP_ASGN1':
        recv = node.attrs.get('nd_recv')  # 接收者（如数组）
        # MRI dump: 下标在 nd_args->nd_head, 赋值值在 nd_args->nd_body
        args = node.attrs.get('nd_args->nd_head')
        value = node.attrs.get('nd_args->nd_body')
        mid = node.attrs.get('nd_mid')  # 操作符；||=/&&= 会是占位符

        # 处理接收者
        recv_s = render(recv, 0) if isinstance(recv, Node) else ''

        # 处理索引参数
        args_s = render_arg_list(args) if isinstance(args, Node) else ''

        # 处理赋值值
        value_s = render(value, 0) if isinstance(value, Node) else (
            'nil' if value is None else str(value))

        # 构建操作符: 普通操作符(:+ 等)直接用; ||=/&&= 在 dump 里是占位符, 默认 ||
        if isinstance(mid, str) and mid.lstrip(':') and mid.lstrip(':')[0] in '+-*/%<>&|^':
            op = mid.lstrip(':')
        else:
            op = '||'

        return f"{'  ' * level}{recv_s}[{args_s}] {op}= {value_s}"

    # NODE_OP_ASGN2 - 对象属性运算符赋值（如 obj.attr += 1）
    if t == 'NODE_OP_ASGN2':
        recv = node.attrs.get('nd_recv')  # 接收者对象
        # MRI dump: 属性名在 nd_next->nd_vid, 操作符在 nd_next->nd_mid
        mid = node.attrs.get('nd_next->nd_vid')
        op = node.attrs.get('nd_next->nd_mid')
        value = node.attrs.get('nd_value')  # 赋值值

        # 处理接收者
        recv_s = render(recv, 0) if isinstance(recv, Node) else ''

        # 处理方法名（去掉冒号）
        attr = str(mid).lstrip(':') if mid is not None else 'unknown'

        # 处理操作符（去掉冒号）
        op_s = str(op).lstrip(':') if op is not None else '+'

        # 处理赋值值
        value_s = render(value, 0) if isinstance(value, Node) else ('nil' if value is None else str(value))

        # ||= / &&= 与普通 op= 形式略不同
        if op_s in ('||', '&&'):
            return f"{'  ' * level}{recv_s}.{attr} {op_s}= {value_s}"
        return f"{'  ' * level}{recv_s}.{attr} {op_s}= {value_s}"

    # NODE_OP_ASGN_AND - &&= 赋值
    if t == 'NODE_OP_ASGN_AND':
        var = node.attrs.get('nd_head')  # 变量名
        value = node.attrs.get('nd_value')  # 赋值值

        # 处理变量名
        var_s = ''
        if isinstance(var, Node):
            if var.type in ('NODE_IVAR', 'NODE_LVAR', 'NODE_CVAR', 'NODE_GVAR'):
                var_s = render(var, 0)
            else:
                var_s = str(var)
        elif isinstance(var, str):
            var_s = var.lstrip(':')

        # 处理赋值值
        value_s = render(value, 0) if isinstance(value, Node) else str(value)

        return f"{'  ' * level}{var_s} &&= {value_s}"

    # NODE_OP_ASGN_OR - ||= 赋值
    if t == 'NODE_OP_ASGN_OR':
        var = node.attrs.get('nd_head')  # 变量名
        value = node.attrs.get('nd_value')  # 赋值值

        # 处理变量名 (DVAR/CONST 等也走 render, 避免泄漏 Python repr)
        var_s = ''
        if isinstance(var, Node):
            var_s = render(var, 0)
        elif isinstance(var, str):
            var_s = var.lstrip(':')

        # 处理赋值值
        if isinstance(value, Node):
            value_s = render(value, 0)
        else:
            value_s = 'nil' if value is None else str(value)

        return f"{'  ' * level}{var_s} ||= {value_s}"

    # NODE_OP_CDECL - 常量运算符赋值（如 CONST += 1）
    if t == 'NODE_OP_CDECL':
        const = node.attrs.get('nd_head')  # 常量名
        op = node.attrs.get('nd_mid')  # 操作符（如 :+）
        value = node.attrs.get('nd_value')  # 赋值值

        # 处理常量名
        const_s = ''
        if isinstance(const, Node):
            if const.type == 'NODE_CONST':
                const_s = const.attrs.get('nd_vid', 'CONST')
            else:
                const_s = render(const, 0)
        elif isinstance(const, str):
            const_s = const.lstrip(':')

        # 处理操作符（去掉冒号）
        op = op[1:] if isinstance(op, str) and op.startswith(':') else str(op)

        # 处理赋值值
        value_s = render(value, 0) if isinstance(value, Node) else str(value)

        return f"{'  ' * level}{const_s} {op}= {value_s}"

    # 在 render 函数中添加以下分支逻辑（建议放在 NODE_ARGS 分支之后）

    # NODE_OPT_ARG - 可选参数（如 def foo(a=1)）
    if t == 'NODE_OPT_ARG':
        vid = node.attrs.get('nd_vid')  # 参数名
        default = node.attrs.get('nd_value')  # 默认值

        # 处理参数名
        var_name = vid.lstrip(':') if isinstance(vid, str) else (str(vid) if vid else 'arg')

        # 处理默认值
        default_s = ''
        if isinstance(default, Node):
            default_s = render(default, 0)
        elif default is not None:
            default_s = str(default)

        # 返回格式化的可选参数
        if default_s:
            return f"{var_name}={default_s}"
        else:
            return var_name

    # NODE_KW_ARG - 关键字参数（如 def foo(a:)
    if t == 'NODE_KW_ARG':
        vid = node.attrs.get('nd_vid')  # 参数名
        default = node.attrs.get('nd_value')  # 默认值（可选）

        # 处理参数名
        var_name = vid.lstrip(':') if isinstance(vid, str) else (str(vid) if vid else 'arg')

        # 处理默认值
        default_s = ''
        if isinstance(default, Node):
            default_s = render(default, 0)
        elif default is not None:
            default_s = str(default)

        # 返回格式化的关键字参数
        if default_s:
            return f"{var_name}: {default_s}"
        else:
            return f"{var_name}:"

    # NODE_POSTARG - 后置参数（Ruby 内部使用，通常不需要渲染）
    if t == 'NODE_POSTARG':
        # 后置参数通常是Ruby内部使用的节点，直接返回空字符串
        return ''

    # NODE_BLOCK_ARG - 块参数（如 def foo(&block)）
    if t == 'NODE_BLOCK_ARG':
        vid = node.attrs.get('nd_vid')  # 块参数名

        # 处理块参数名
        if vid:
            block_name = vid.lstrip(':') if isinstance(vid, str) else str(vid)
            return f"&{block_name}"
        else:
            return "&"

    # 在 render 函数中添加以下分支逻辑（建议放在 NODE_HASH 分支之后）

    # NODE_MASGN - 多重赋值（如 a, b = [1, 2]）
    if t == 'NODE_MASGN':
        vars_node = node.attrs.get('nd_head')  # 左侧变量部分
        value_node = node.attrs.get('nd_value')  # 右侧值部分

        # 处理左侧变量列表 (用 collect_list 遍历, 仅取目标变量名, 避免卷入 nd_next 嵌套赋值)
        vars_list = []
        if isinstance(vars_node, Node):
            if vars_node.type in ('NODE_ARRAY', 'NODE_LIST'):
                for child in collect_list(vars_node):
                    if child.type in ('NODE_LASGN', 'NODE_DASGN', 'NODE_DASGN_CURR',
                                      'NODE_IASGN', 'NODE_GASGN', 'NODE_CVASGN', 'NODE_CDECL'):
                        var_name = str(child.attrs.get('nd_vid') or '').lstrip(':')
                        vars_list.append(var_name)
                    else:
                        vars_list.append(render(child, 0))
            else:
                vars_list.append(render(vars_node, 0))

        # 处理右侧值
        value_str = render(value_node, 0) if isinstance(value_node, Node) else 'nil'

        # 构建多重赋值表达式
        return f"{'  ' * level}{', '.join(vars_list)} = {value_str}"

    # NODE_DASGN - 动态作用域变量赋值（补充 NODE_DASGN_CURR 的覆盖）
    if t == 'NODE_DASGN':
        vid = node.attrs.get('nd_vid') or ''
        value = node.attrs.get('nd_value')

        # 处理变量名
        var_name = vid.lstrip(':') if isinstance(vid, str) else str(vid)

        # 处理赋值值
        if value is None:
            return f"{'  ' * level}{var_name} = nil"
        elif isinstance(value, Node):
            value_str = render(value, 0)
        else:
            value_str = str(value)

        return f"{'  ' * level}{var_name} = {value_str}"

    # NODE_ALIAS - 方法别名（如 alias :new :old）
    if t == 'NODE_ALIAS':
        new_name = node.attrs.get('nd_new')  # 新方法名
        old_name = node.attrs.get('nd_old')  # 原方法名

        # 处理方法名（支持符号和字符串）
        def render_method_name(node):
            if isinstance(node, Node):
                if node.type == 'NODE_LIT' and isinstance(node.attrs.get('nd_lit'), str):
                    return node.attrs['nd_lit']
                return render(node, 0)
            elif isinstance(node, str):
                return node.lstrip(':')
            return str(node)

        new_str = render_method_name(new_name)
        old_str = render_method_name(old_name)

        # 确保方法名格式正确
        if not new_str.startswith(':'):
            new_str = f":{new_str}"
        if not old_str.startswith(':'):
            old_str = f":{old_str}"

        return f"{'  ' * level}alias {new_str} {old_str}"

    # NODE_UNDEF - undef 语句
    if t == 'NODE_UNDEF':
        names = []
        current = node
        while current:
            name_node = current.attrs.get('nd_head')
            if name_node:
                if isinstance(name_node, Node):
                    if name_node.type == 'NODE_LIT' and isinstance(name_node.attrs.get('nd_lit'), str):
                        name = name_node.attrs['nd_lit']
                    else:
                        name = render(name_node, 0)
                else:
                    name = str(name_node).lstrip(':')
                names.append(f":{name}")
            current = current.attrs.get('nd_next') if isinstance(current, Node) else None

        return f"{'  ' * level}undef {', '.join(names)}"

    # NODE_DOT2 - 范围字面量（如 1..10）
    if t == 'NODE_DOT2':
        begin_node = node.attrs.get('nd_beg')
        end_node = node.attrs.get('nd_end')

        begin_str = render(begin_node, 0) if isinstance(begin_node, Node) else str(begin_node)
        end_str = render(end_node, 0) if isinstance(end_node, Node) else str(end_node)

        return f"{begin_str}..{end_str}"

    # NODE_DOT3 - 排除末尾的范围（如 1...10）
    if t == 'NODE_DOT3':
        begin_node = node.attrs.get('nd_beg')
        end_node = node.attrs.get('nd_end')

        begin_str = render(begin_node, 0) if isinstance(begin_node, Node) else str(begin_node)
        end_str = render(end_node, 0) if isinstance(end_node, Node) else str(end_node)

        return f"{begin_str}...{end_str}"

    # NODE_FLIP2/NODE_FLIP3 - 触发器语法（如 if /start/../end/）
    if t in ('NODE_FLIP2', 'NODE_FLIP3'):
        begin_node = node.attrs.get('nd_beg')
        end_node = node.attrs.get('nd_end')

        begin_str = render(begin_node, 0) if isinstance(begin_node, Node) else str(begin_node)
        end_str = render(end_node, 0) if isinstance(end_node, Node) else str(end_node)

        # FLIP2 是包含结束点，FLIP3 是不包含结束点
        op = '..' if t == 'NODE_FLIP2' else '...'
        return f"{begin_str}{op}{end_str}"

    # NODE_DEFINED - defined? 操作符
    if t == 'NODE_DEFINED':
        expr_node = node.attrs.get('nd_head')
        expr_str = render(expr_node, 0) if isinstance(expr_node, Node) else str(expr_node)
        return f"{'  ' * level}defined?({expr_str})"

    # 在 render 函数中添加以下分支逻辑

    # --------------------------------------------------
    # 5. 字符串和正则表达式变体
    # --------------------------------------------------

    # NODE_XSTR - 反引号命令（如 `ls`）
    if t == 'NODE_XSTR':
        parts = []
        lit = node.attrs.get('nd_lit', '')  # 基础命令部分

        if lit:
            parts.append(lit)

        # 处理子节点（插值部分）
        for child in node.children:
            if child.type == 'NODE_EVSTR':
                interpolated = render(child, 0).strip()
                if interpolated:
                    parts.append(f"#{{{interpolated}}}")

        # 组装命令字符串
        cmd = ''.join(parts)
        return f"{'  ' * level}`{cmd}`" if level > 0 else f"`{cmd}`"

    # NODE_DREGX_ONCE - 只执行一次的正则插值（如 /#{foo}/o）
    if t == 'NODE_DREGX_ONCE':
        parts = []
        lit = node.attrs.get('nd_lit', '')  # 基础正则部分

        if lit:
            parts.append(lit)

        # 处理插值内容
        for child in node.children:
            if child.type == 'NODE_EVSTR':
                interpolated = render(child, 0).strip()
                if interpolated:
                    parts.append(f"#{{{interpolated}}}")

        # 添加 'o' 修饰符表示只编译一次
        regex = '/' + ''.join(parts) + '/o'
        return f"{'  ' * level}{regex}" if level > 0 else regex

    # NODE_DSYM - 动态符号（如 :"foo#{bar}"）
    if t == 'NODE_DSYM':
        parts = []

        # 处理子节点
        for child in node.children:
            if child.type == 'NODE_EVSTR':
                interpolated = render(child, 0).strip()
                if interpolated:
                    parts.append(f"#{{{interpolated}}}")
            elif child.type == 'NODE_STR':
                parts.append(child.attrs.get('nd_lit', ''))

        # 组装动态符号
        symbol_content = ''.join(parts)
        return f":\"{symbol_content}\""

    # --------------------------------------------------
    # 6. 元编程相关
    # --------------------------------------------------

    # NODE_BMETHOD - 块定义的方法
    if t == 'NODE_BMETHOD':
        body = node.attrs.get('nd_body')  # 方法体
        cref = node.attrs.get('nd_cref')  # 上下文引用

        # 渲染方法体
        body_s = render(body, level + 1) if isinstance(body, Node) else ''

        # 构建输出（类似于普通方法定义，但用 define_method 表示）
        out = f"{'  ' * level}define_method(:method_name) do"
        if body_s:
            out += f"\n{body_s}"
        out += f"\n{'  ' * level}end"
        return out

    # NODE_MEMO - 记忆化节点（内部使用）
    if t == 'NODE_MEMO':
        # 通常不需要渲染，直接返回空字符串或原始值
        value = node.attrs.get('nd_value')
        if isinstance(value, Node):
            return render(value, level)
        return str(value) if value else ''

    # NODE_PRELUDE - 文件级前导 (还原时省略 BEGIN{} 包装)
    if t == 'NODE_PRELUDE':
        body = node.attrs.get('nd_body')
        return render(body, level) if isinstance(body, Node) else ''

    # NODE_POSTEXE - 后置执行块（如 END {}）
    if t == 'NODE_POSTEXE':
        body = node.attrs.get('nd_body')
        body_s = render(body, level + 1) if isinstance(body, Node) else ''

        out = f"{'  ' * level}END {{"
        if body_s:
            out += f"\n{body_s}\n{'  ' * level}}}"
        else:
            out += "}"
        return out

    # 在 render 函数中添加以下分支逻辑（建议放在函数末尾的缺省处理之前）

    # NODE_OPT_N - 数值可选参数（内部优化节点，通常不需要直接渲染）
    if t == 'NODE_OPT_N':
        # 通常作为方法可选参数的优化表示，直接返回空字符串
        # 实际参数处理会在 NODE_OPT_ARG 或方法定义节点中处理
        return ''

    # NODE_IASGN2 - 实例变量二次赋值（内部使用）
    if t == 'NODE_IASGN2':
        vid = node.attrs.get('nd_vid') or ''  # 变量名
        value = node.attrs.get('nd_value')  # 赋值值

        # 确保实例变量有 @ 前缀
        var_name = f"@{vid.lstrip('@')}" if vid else '@undefined'

        # 处理赋值值
        if value is None:
            return f"{'  ' * level}{var_name} = nil"
        elif isinstance(value, Node):
            value_s = render(value, 0)
        else:
            value_s = str(value)

        return f"{'  ' * level}{var_name} = {value_s}"

    # NODE_CVDECL - 类变量声明（如 @@foo 的声明）
    if t == 'NODE_CVDECL':
        vid = node.attrs.get('nd_vid') or ''  # 变量名
        value = node.attrs.get('nd_value')  # 初始值

        # 确保类变量有 @@ 前缀
        var_name = f"@@{vid.lstrip('@')}" if vid else '@@undefined'

        # 处理初始值
        if value is None:
            return f"{'  ' * level}{var_name} = nil"
        elif isinstance(value, Node):
            value_s = render(value, 0)
        else:
            value_s = str(value)

        return f"{'  ' * level}{var_name} = {value_s}"

    # NODE_NTH_REF - 正则分组引用（如 $1）
    if t == 'NODE_NTH_REF':
        nth = node.attrs.get('nd_nth', 1)  # 分组编号
        return f"${nth}"

    # NODE_BACK_REF - 正则反向引用（如 $&）
    if t == 'NODE_BACK_REF':
        ref_type = node.attrs.get('nd_nth')  # 引用类型

        # 根据类型返回对应的全局变量
        back_refs = {
            0: '$&',  # 最近匹配
            1: '$`',  # 匹配前的内容
            2: '$\'',  # 匹配后的内容
            3: '$+',  # 最后捕获组
        }

        return back_refs.get(ref_type, '$&')  # 默认为 $&

    # 缺省，递归渲染子节点
    outlist = []
    for c in node.children:
        s = render(c, level)
        if s and s.strip():  # 只添加非空且非空白的内容
            outlist.append(s)
    return '\n'.join(outlist)

