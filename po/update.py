#!/usr/bin/env python3
"""Extrai os textos traduzíveis do código e atualiza po/nova-control.pot e po/*.po.

    python3 po/update.py           atualiza o .pot e acrescenta textos novos a cada .po
    python3 po/update.py --check   falha se algum .po tiver texto sem tradução (usado no CI)
    python3 po/update.py --new fr  cria po/fr.po a partir do .pot

Os textos são encontrados pela árvore sintática do Python (chamadas _("..."),
N_("...") e ngettext("...", "...", n)), sem depender das ferramentas do gettext.
"""

from __future__ import annotations

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PO_DIR = os.path.join(ROOT, "po")
SRC_DIR = os.path.join(ROOT, "nova_control")
POT = os.path.join(PO_DIR, "nova-control.pot")

sys.path.insert(0, ROOT)
from nova_control.i18n import parse_po  # noqa: E402

PLURAL_FORMS = {
    "pt_BR": "nplurals=2; plural=(n > 1);",
}
DEFAULT_PLURAL = "nplurals=2; plural=(n != 1);"


def extract() -> list[tuple[str, str | None, list[str]]]:
    """[(msgid, msgid_plural, [referências])] na ordem em que aparecem no código."""
    found: dict[tuple[str, str | None], list[str]] = {}
    for name in sorted(os.listdir(SRC_DIR)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(SRC_DIR, name)
        tree = ast.parse(open(path, encoding="utf-8").read(), path)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            args = node.args
            if node.func.id in ("_", "N_") and args and _is_str(args[0]):
                key = (args[0].value, None)
            elif node.func.id == "ngettext" and len(args) >= 2 and _is_str(args[0]) and _is_str(args[1]):
                key = (args[0].value, args[1].value)
            else:
                continue
            found.setdefault(key, []).append(f"nova_control/{name}:{node.lineno}")
    def first_ref(item):
        path, line = item[1][0].rsplit(":", 1)
        return path, int(line)
    return [(k[0], k[1], refs) for k, refs in sorted(found.items(), key=first_ref)]


def _is_str(node) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def quote(text: str) -> str:
    """Formata um texto no estilo do .po, quebrando em linhas após cada \\n."""
    esc = text.replace("\\", "\\\\").replace('"', '\\"').replace("\t", "\\t")
    parts = esc.split("\n")
    lines = [p + "\\n" for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])
    if len(lines) <= 1:
        return f'"{lines[0] if lines else ""}"'
    return '""\n' + "\n".join(f'"{line}"' for line in lines)


def header(lang: str | None) -> str:
    plural = PLURAL_FORMS.get(lang, DEFAULT_PLURAL) if lang else "nplurals=INTEGER; plural=EXPRESSION;"
    return (
        'msgid ""\nmsgstr ""\n'
        '"Project-Id-Version: nova-control\\n"\n'
        '"Report-Msgid-Bugs-To: https://github.com/joaopedromoraez/nova-control/issues\\n"\n'
        f'"Language: {lang or ""}\\n"\n'
        '"MIME-Version: 1.0\\n"\n'
        '"Content-Type: text/plain; charset=UTF-8\\n"\n'
        '"Content-Transfer-Encoding: 8bit\\n"\n'
        f'"Plural-Forms: {plural}\\n"\n'
    )


def render(entries, lang: str | None, catalog: dict) -> str:
    out = [
        "# Nova Control translations" + (f" ({lang})" if lang else " template") + ".",
        "# This file is distributed under the same license as the Nova Control package (MIT).",
        header(lang),
    ]
    for msgid, plural, refs in entries:
        block = ["#: " + " ".join(refs)]
        if "{" in msgid:
            block.append("#, python-brace-format")
        block.append("msgid " + quote(msgid))
        if plural is None:
            block.append("msgstr " + quote(catalog.get(msgid, "")))
        else:
            forms = catalog.get((msgid, plural), ["", ""])
            block.append("msgid_plural " + quote(plural))
            block.append("msgstr[0] " + quote(forms[0]))
            block.append("msgstr[1] " + quote(forms[1]))
        out.append("\n".join(block) + "\n")
    return "\n".join(out)


def po_files() -> list[str]:
    return sorted(f[:-3] for f in os.listdir(PO_DIR) if f.endswith(".po"))


def shadowed_underscore() -> list[str]:
    """Lugares que usam `_` como variável: isso esconde a função de tradução _() naquele escopo."""
    problems = []
    for name in sorted(os.listdir(SRC_DIR)):
        if not name.endswith(".py") or name == "i18n.py":
            continue
        tree = ast.parse(open(os.path.join(SRC_DIR, name), encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.arg) and node.arg == "_":
                problems.append(f"nova_control/{name}:{node.lineno}")
            elif isinstance(node, ast.Name) and node.id == "_" and isinstance(node.ctx, ast.Store):
                problems.append(f"nova_control/{name}:{node.lineno}")
    return problems


def missing(entries, catalog: dict) -> list[str]:
    return [m for m, p, _r in entries if (m if p is None else (m, p)) not in catalog]


def main(argv: list[str]) -> int:
    entries = extract()
    if "--check" in argv:
        bad = 0
        for lang in po_files():
            miss = missing(entries, parse_po(os.path.join(PO_DIR, f"{lang}.po")))
            for m in miss:
                print(f"{lang}.po: sem tradução: {m!r}")
            bad += len(miss)
        print(f"{len(entries)} textos, {bad} sem tradução")
        for where in shadowed_underscore():
            print(f"{where}: '_' usado como variável esconde a função de tradução _(); use outro nome")
            bad += 1
        return 1 if bad else 0

    langs = po_files()
    if "--new" in argv:
        langs.append(argv[argv.index("--new") + 1])

    with open(POT, "w", encoding="utf-8") as f:
        f.write(render(entries, None, {}))
    for lang in sorted(set(langs)):
        path = os.path.join(PO_DIR, f"{lang}.po")
        catalog = parse_po(path) if os.path.exists(path) else {}
        with open(path, "w", encoding="utf-8") as f:
            f.write(render(entries, lang, catalog))
        print(f"{lang}.po: {len(missing(entries, catalog))} sem tradução")
    print(f"{len(entries)} textos em {os.path.relpath(POT, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
