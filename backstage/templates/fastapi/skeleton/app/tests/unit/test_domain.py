import pytest
from pydantic import ValidationError

from platform_app.config import Settings
from platform_app.domain import Operation, transform


@pytest.mark.parametrize(
    "text,operation,result",
    [
        ("Hello, world!", Operation.uppercase, "HELLO, WORLD!"),
        ("Straße", Operation.uppercase, "STRASSE"),
        ("abc123", Operation.reverse, "321cba"),
        ("", Operation.reverse, ""),
    ],
)
def test_transform(text, operation, result):
    assert transform(text, operation) == result


def test_unsupported_operation():
    with pytest.raises(ValueError, match="Unsupported"):
        transform("hello", "unknown")


def test_invalid_retry_configuration():
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql+psycopg://unused", outbox_retry_seconds=-1)
