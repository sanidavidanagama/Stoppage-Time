# service/context.py
import contextvars

_session_id_var = contextvars.ContextVar("session_id", default=None)
_bet_id_var = contextvars.ContextVar("bet_id", default=None)


def set_context(session_id: str, bet_id: str | None = None) -> None:
    _session_id_var.set(session_id)
    _bet_id_var.set(bet_id)


def get_session_id() -> str | None:
    return _session_id_var.get()


def get_bet_id() -> str | None:
    return _bet_id_var.get()