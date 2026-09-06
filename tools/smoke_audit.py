from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def module_path(name: str) -> Path | None:
    if name == "__main__":
        return None
    parts = name.split(".")
    candidate = ROOT.joinpath(*parts)
    py = candidate.with_suffix(".py")
    init = candidate / "__init__.py"
    if py.is_file():
        return py
    if init.is_file():
        return init
    return None


def local_module_name(current: Path, level: int, module: str | None) -> str | None:
    rel = current.relative_to(ROOT).with_suffix("")
    package = list(rel.parts[:-1])
    if level:
        if level > len(package) + 1:
            return None
        package = package[: len(package) - level + 1]
    if module:
        package.extend(module.split("."))
    return ".".join(package) if package else None


def defined_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def main() -> None:
    errors: list[str] = []
    py_files = [p for p in ROOT.rglob("*.py") if ".git" not in p.parts]

    for path in py_files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            errors.append(f"PY syntax {path.relative_to(ROOT)}: {exc}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports = [(alias.name, None) for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                name = local_module_name(path, node.level, node.module)
                imports = [(name, alias.name) for alias in node.names] if name else []
            else:
                continue

            for name, symbol in imports:
                target = module_path(name) if name else None
                if target is None:
                    continue
                if symbol and symbol != "*":
                    try:
                        available = defined_names(target)
                    except Exception as exc:
                        errors.append(
                            f"AST read {target.relative_to(ROOT)}: {exc}"
                        )
                        continue
                    if symbol not in available:
                        errors.append(
                            f"missing local import: {path.relative_to(ROOT)} -> "
                            f"{name}.{symbol} (not defined in {target.relative_to(ROOT)})"
                        )

    if importlib.util.find_spec("database") is None:
        errors.append("cannot resolve top-level database module")

    if errors:
        raise SystemExit("\n".join(errors))

    print(f"python smoke audit: OK ({len(py_files)} files)")


if __name__ == "__main__":
    main()
