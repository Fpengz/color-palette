"""User-facing errors that carry a stable code for interface localization.

Routes translate these into HTTP responses. The English ``message`` stays the
API contract; ``code`` and ``params`` let a client render the same failure in
its own language instead of echoing English text to the user.
"""

from __future__ import annotations


class CodedError(ValueError):
    """Keep ``code`` and ``params`` as plain instance attributes.

    Formulation runs in a worker process, so these have to survive pickling.
    ``BaseException.__reduce__`` already carries ``__dict__`` across as state,
    which covers this for free -- but only while they stay ordinary attributes
    and the constructor stays callable with the message alone. Adding
    ``__slots__`` or a required keyword would break that silently, so
    ``tests/test_concurrency.py`` pins the behavior.
    """

    def __init__(self, message: str, *, code: str | None = None, **params: object) -> None:
        super().__init__(message)
        self.code = code
        self.params = params
