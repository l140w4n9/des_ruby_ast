import sys

from desast import parse_dump, render
from desast.beautify import beautify_ruby


def main(argv=None):
    argv = argv if argv is not None else sys.argv
    if len(argv) != 2:
        print(f"Usage: python -m desast <ast_dump_file>")
        sys.exit(1)

    with open(argv[1], encoding="utf-8") as f:
        text = f.read()

    root_node = parse_dump(text)
    if not root_node:
        print("Parse failed or empty AST")
        sys.exit(2)

    print(beautify_ruby(render(root_node)))


if __name__ == "__main__":
    main()
