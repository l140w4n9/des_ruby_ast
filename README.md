# desast

将 **MRI Ruby AST dump**（`.ast` 文本）反编译为可读 Ruby 源码的工具，适用于 Rails/Grape 等项目的静态分析与代码还原。

## 功能概览

- 解析 Ruby 解释器导出的节点树 dump（`@ NODE_*` 格式）
- 重建 class / module / def / 控制流 / 方法调用 / hash 等语法结构
- 内置 **beautify** 后处理：Rails 风格、符号化 hash、缩进修正、长行折行等
- 支持单文件 CLI 与 Python API，可批量处理整个目录

## 环境要求

- Python 3.8+
- 无第三方依赖（仅标准库）

## 项目结构

```
desast/
├── desast/                 # 主包
│   ├── __init__.py         # 对外 API：decompile, parse_dump, render, beautify_ruby
│   ├── __main__.py         # python -m desast 入口
│   ├── parser.py           # AST dump 文本 → 节点树
│   ├── node.py             # Node 数据结构
│   ├── helpers.py          # cons-list 遍历、字符串转义等
│   ├── args.py             # 方法形参与调用参数重建
│   ├── render.py           # 节点树 → Ruby 源码（核心）
│   ├── beautify.py         # 源码美化后处理
│   └── cli.py              # 命令行入口
├── desast_fixed.py         # 兼容入口（推荐）
├── desast.py               # 早期单文件版本（已过时）
├── batch_test.py           # 批量反编译 restored_app
└── restored_app/           # 示例 AST 与反编译输出
    ├── **/*.ast            # 输入 dump
    └── _decompiled/**/*.rb # 批量输出
```

## 快速开始

### 命令行

```bash
# 推荐：兼容入口，输出已美化
python desast_fixed.py path/to/file.ast

# 或使用包入口
python -m desast path/to/file.ast
```

输出打印到 stdout，可重定向：

```bash
python desast_fixed.py restored_app/models/account.rb.ast > account.rb
```

### Python API

```python
from desast import decompile, parse_dump, render, beautify_ruby

# 一步到位（解析 + 渲染 + 美化）
with open("file.ast", encoding="utf-8") as f:
    ruby = decompile(f.read())

# 分步控制
from desast import parse_dump, render
from desast.beautify import beautify_ruby

root = parse_dump(text)
raw = render(root)              # 原始渲染
pretty = beautify_ruby(raw)     # 仅美化
```

### 批量反编译 restored_app

```bash
python batch_test.py
```

- 输入：`restored_app/**/*.ast`
- 输出：`restored_app/_decompiled/**/*.rb`（目录结构镜像）
- 报告：`restored_app/_decompiled/_report.txt`

## 输入格式

工具读取 MRI 风格的 AST dump 文本，典型片段如下：

```
# @ NODE_SCOPE (line: 1)
# +- nd_tbl: :account_id
# +- nd_body:
#     @ NODE_CLASS (line: 2)
#     +- nd_cpath:
#         @ NODE_CONST (line: 2)
#         +- nd_vid: :Account
```

以 `#` 开头的注释行会被预处理为节点内容；缩进（`|` 或空格）用于确定父子关系。

## 美化（beautify）能力

CLI 与 `decompile()` 默认启用美化，主要包括：

| 类别 | 示例 |
|------|------|
| 去掉 AST 包装 | `BEGIN { ... }` → 直接输出 class/module |
| Rails 宏 | `include(Foo)` → `include Foo` |
| 关联声明 | `belongs_to "user", {"foreign_key"=>"id"}` → `belongs_to :user, foreign_key: :id` |
| Hash 语法 | `"key" => val` → `key: val` / `key: :val` |
| 运算符 | `.<=>(x)` → ` <=> x` |
| 方法签名 | `def foo()` → `def foo` |
| 缩进 / 空行 | 块结构重算缩进，def 之间空行 |
| 长列表折行 | `attr_accessible`、`select([...])` 多行符号列表 |
| 块参数补全 | `each do` → `each do \|item\|` |

## 已知局限

反编译结果 **不能** 与原始源码完全一致，原因包括：

- 局部变量名、块参数名（`\|r\|`）在 dump 中可能缺失
- 部分 `rescue` 体为空，只能还原为裸 `rescue`
- 复杂嵌套表达式可能产生超长行
- 注释、部分元数据不会出现在 AST dump 中

在 `restored_app` 全量测试中（659 个文件）：653 成功、6 空 AST、0 失败。

## 版本说明

| 文件 | 说明 |
|------|------|
| `desast/` 包 + `desast_fixed.py` | **当前推荐**，修复了 cons-list 遍历、hash 渲染、形参回退等结构性问题，并集成 beautify |
| `desast.py` | 早期 monolith 版本，存在 hash/参数重复渲染等问题，仅作参考 |

## 典型工作流（漏洞分析 / 代码审计）

1. 从目标 Rails 应用导出各文件的 AST dump（`.ast`）
2. 放入类似 `restored_app/` 的目录结构
3. 运行 `python batch_test.py` 或单文件 `desast_fixed.py`
4. 在 `_decompiled/` 下阅读还原后的 Ruby，结合路由、Gemfile 等做进一步分析

## License

内部研究工具，按需自行维护与扩展。
