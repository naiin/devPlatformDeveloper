from enum import StrEnum


class Operation(StrEnum):
    uppercase = "uppercase"
    reverse = "reverse"


def transform(text: str, operation: Operation) -> str:
    match operation:
        case Operation.uppercase:
            return text.upper()
        case Operation.reverse:
            return text[::-1]
        case _:
            raise ValueError("Unsupported operation")
