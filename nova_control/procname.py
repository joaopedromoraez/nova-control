"""Nome do processo: "nova-control" em vez de "python3".

- Nome curto (/proc/<pid>/comm, usado pelo Monitor do Sistema e pelo top): via prctl,
  sem dependências.
- Linha de comando completa (ps aux, htop): via o módulo opcional setproctitle
  (pacotes python3-setproctitle / python-setproctitle), quando instalado.
"""

from __future__ import annotations

import ctypes
import ctypes.util

NAME = "nova-control"
PR_SET_NAME = 15


def set_process_name(args: list[str] | None = None) -> None:
    title = " ".join([NAME, *(args or [])])
    try:
        import setproctitle
        setproctitle.setproctitle(title)
    except ImportError:
        pass
    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)
        libc.prctl(PR_SET_NAME, NAME.encode()[:15], 0, 0, 0)
    except (OSError, AttributeError):
        pass
