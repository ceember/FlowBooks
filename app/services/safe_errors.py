"""What a caught exception may say to the user.

A route or importer that catches a bare Exception must not put the
exception's own text in a response: SQLAlchemy errors carry the whole
statement and every bound parameter (a live payment token, in the case
macbase1 caught on the 2.9.4 gate), driver errors carry hostnames, and
tracebacks carry paths. The rule here: a data problem described in our own
words passes through; a database constraint is reduced to the constraint;
anything else is logged with its traceback and answered with one fixed
sentence.

"In our own words" used to mean "is a ValueError", and that was a convention
nobody could check: Python's own ValueErrors ("invalid literal for int()
with base 10: 'abc'") passed under the same door, and a scanner reading the
code sees only that a caught exception's text reaches a response — which is
exactly what it should object to. So the marker is now explicit. An
exception that was raised with a sentence for the user carries it as
`user_text`, set at the point it was raised; `safe_message` hands that on
and nothing else. `DataProblem` is the ordinary way to raise one.
"""

import logging
from decimal import InvalidOperation

from sqlalchemy.exc import IntegrityError, StatementError

logger = logging.getLogger(__name__)

GENERIC = "unexpected error — the server log has the details"


class DataProblem(ValueError):
    """A problem with the data, in a sentence written for the person who
    sent it: "Missing customer NAME on TRNS line", "Journal entry not
    balanced". Raise it wherever the text is meant to be read by a user.

    It is a ValueError so existing `except ValueError` handling is
    unchanged. What it adds is `user_text`, the one thing `safe_message`
    will pass on. A bare ValueError — Python's own wording from int(),
    strptime(), a library — is treated as a bug: logged, answered
    generically. Not LookupError / ArithmeticError either: KeyError,
    IndexError and ZeroDivisionError are what Python raises when the code
    is wrong, and a bug must be logged, not handed to the user as
    "'ACCNT'" (macbase1, 2.9.4 gate).
    """

    def __init__(self, user_text: str):
        super().__init__(user_text)
        self.user_text = user_text


def user_text_of(exc: BaseException) -> str | None:
    """The sentence `exc` was raised with for the user, or None.

    Any exception may carry one — `MissingControlAccount` does, because
    its message tells the operator which account to restore — so this
    reads the attribute rather than checking the class."""
    text = getattr(exc, "user_text", None)
    return text if isinstance(text, str) and text else None


def safe_message(exc: BaseException, context: str = "operation") -> str:
    """The sentence a user may see for `exc`. Call from inside the except
    block so the traceback is attached to the log line."""
    if isinstance(exc, IntegrityError):
        # sqlite3 / psycopg wrap the statement and parameters in str(exc);
        # the driver's own first line is the constraint, which is the
        # useful part ("NOT NULL constraint failed: invoices.invoice_number").
        orig = str(getattr(exc, "orig", "") or "").strip().splitlines()
        logger.warning("%s: database constraint", context, exc_info=True)
        return "Database constraint: " + (orig[0] if orig else "see the server log")
    if isinstance(exc, StatementError):
        logger.exception("%s: database error", context)
        return "Database error — the server log has the details"
    if isinstance(exc, InvalidOperation):
        # decimal's own text is "[<class 'decimal.ConversionSyntax'>]"
        logger.info("%s: a number could not be read", context)
        return "a number could not be read"
    text = user_text_of(exc)
    if text is not None:
        logger.info("%s: %s", context, text)
        return text
    if isinstance(exc, ValueError):
        # Python's or a library's wording, not ours. The row is still
        # reported, and the log says what the value was.
        logger.warning("%s: %s", context, exc, exc_info=True)
        return GENERIC
    logger.exception("%s: unexpected error", context)
    return GENERIC
