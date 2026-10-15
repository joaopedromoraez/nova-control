"""Traduções.

O texto original do código é inglês. As traduções ficam em po/<idioma>.po e são lidas
diretamente em tempo de execução (sem compilar para .mo), então o app funciona igual
rodando do repositório ou instalado, sem depender das ferramentas do gettext.

O idioma vem do sistema, na ordem do gettext: LANGUAGE, LC_ALL, LC_MESSAGES, LANG.
Ex.: LANGUAGE=es nova-control
"""

from __future__ import annotations

import ast
import gettext
import os

PO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "po")

# Regras de plural (iguais às do cabeçalho Plural-Forms de cada .po)
PLURAL_RULES = {
    "pt_BR": lambda n: int(n > 1),
}


def available_languages() -> list[str]:
    try:
        return sorted(f[:-3] for f in os.listdir(PO_DIR) if f.endswith(".po"))
    except OSError:
        return []


def system_languages() -> list[str]:
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            return [v for v in value.split(":") if v]
    return []


def choose_language(wanted: list[str], available: list[str]) -> str | None:
    """'pt_BR.UTF-8' -> pt_BR; 'es_MX' -> es; 'pt_PT' -> pt_BR; 'C'/'en_US' -> None (inglês)."""
    for entry in wanted:
        code = entry.split(".")[0].split("@")[0]
        if code in ("C", "POSIX") or code.startswith("en"):
            return None
        if code in available:
            return code
        lang = code.split("_")[0]
        if lang in available:
            return lang
        for a in available:
            if a.split("_")[0] == lang:
                return a
    return None


def _unquote(line: str) -> str:
    return ast.literal_eval(line.strip())


def parse_po(path: str) -> dict:
    """Lê um .po: {msgid: msgstr} e {(msgid, msgid_plural): [msgstr0, msgstr1]}. Ignora entradas fuzzy."""
    catalog: dict = {}
    entry: dict = {}
    field = None
    fuzzy = False

    def flush():
        nonlocal entry, fuzzy
        msgid = entry.get("msgid")
        if msgid and not fuzzy:
            if "msgid_plural" in entry:
                forms = [entry.get(f"msgstr[{i}]", "") for i in range(2)]
                if all(forms):
                    catalog[(msgid, entry["msgid_plural"])] = forms
            elif entry.get("msgstr"):
                catalog[msgid] = entry["msgstr"]
        entry, fuzzy = {}, False

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                flush()
                field = None
            elif line.startswith("#,") and "fuzzy" in line:
                fuzzy = True
            elif line.startswith("#"):
                continue
            elif line.startswith('"'):
                if field:
                    entry[field] = entry.get(field, "") + _unquote(line)
            else:
                key, _, rest = line.partition(" ")
                if key == "msgid" and any(k.startswith("msgstr") for k in entry):
                    flush()  # entrada nova sem linha em branco separando
                field = key
                entry[field] = _unquote(rest)
    flush()
    return catalog


class POTranslations(gettext.NullTranslations):
    def __init__(self, language: str, catalog: dict):
        super().__init__()
        self.language = language
        self._catalog = catalog
        self._plural = PLURAL_RULES.get(language, lambda n: int(n != 1))

    def gettext(self, message):
        return self._catalog.get(message, message)

    def ngettext(self, singular, plural, n):
        forms = self._catalog.get((singular, plural))
        if forms:
            return forms[self._plural(n)]
        return singular if n == 1 else plural


def _load() -> gettext.NullTranslations:
    lang = choose_language(system_languages(), available_languages())
    if lang:
        try:
            return POTranslations(lang, parse_po(os.path.join(PO_DIR, f"{lang}.po")))
        except (OSError, ValueError, SyntaxError):
            pass
    return gettext.NullTranslations()


translations = _load()
_ = translations.gettext
ngettext = translations.ngettext


def N_(message: str) -> str:
    """Marca um texto para tradução sem traduzir agora (traduzido depois com _())."""
    return message
