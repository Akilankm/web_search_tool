from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "product_url_v2"
POLICY = PACKAGE / "policy.py"

FORBIDDEN_TEXT = {
    "hard_url_blockers": "Ad hoc blocker state is forbidden; derive blockers in policy.py.",
    ".mapping_eligible": "Mapping eligibility must come from evaluate_acceptance().",
    ".strictly_verified": "Strict verification must come from evaluate_acceptance().",
    ".review_eligible": "Review eligibility must come from evaluate_acceptance().",
}
POLICY_FUNCTIONS = {
    "evaluate_acceptance",
    "browser_precheck",
    "browser_rank",
    "final_rank",
    "choose_delivery",
}


def main() -> int:
    failures: list[str] = []
    for path in sorted(PACKAGE.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT)
        if path != POLICY:
            for token, reason in FORBIDDEN_TEXT.items():
                if token in text:
                    failures.append(f"{relative}: contains {token!r}. {reason}")

        tree = ast.parse(text, filename=str(relative))
        for node in ast.walk(tree):
            if path != POLICY and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in POLICY_FUNCTIONS:
                failures.append(f"{relative}:{node.lineno}: {node.name} must be defined only in policy.py")
            if path != POLICY and isinstance(node, (ast.Assign, ast.AnnAssign)):
                names = _assigned_names(node)
                if "SOURCE_PRIORITY" in names or "_SOURCE_PRIORITY" in names:
                    failures.append(f"{relative}:{node.lineno}: source priority must be defined only in policy.py")

    if failures:
        print("Canonical acceptance architecture check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Canonical acceptance architecture check passed.")
    return 0


def _assigned_names(node: ast.Assign | ast.AnnAssign) -> set[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    names: set[str] = set()
    for target in targets:
        if isinstance(target, ast.Name):
            names.add(target.id)
    return names


if __name__ == "__main__":
    raise SystemExit(main())
