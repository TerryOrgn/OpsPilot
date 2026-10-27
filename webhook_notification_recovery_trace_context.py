
from contextvars import ContextVar


_request_id = ContextVar(
    "opspilot_request_id",
    default=None,
)


def get_request_id():
    return _request_id.get()


def set_request_id(request_id):
    if not isinstance(request_id, str):
        raise ValueError(
            "request_id must be a string"
        )

    if not request_id.strip():
        raise ValueError(
            "request_id must not be empty"
        )

    return _request_id.set(request_id)


def reset_request_id(token):
    _request_id.reset(token)
