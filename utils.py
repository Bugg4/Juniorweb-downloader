from magic import from_buffer
import json


def buffer_is_pdf(buffer) -> tuple[bool, str]:
    detected_type: str = from_buffer(buffer)
    return ("PDF document" in detected_type, detected_type)


def dump_json(data, filepath: str):
    with open(filepath, "w") as f:
        json.dump(data, f)


def list_difference_asymmetric(primary: list, secondary: list) -> list:
    # return elements which are in primary but not in secondary
    # returned list may be shuffled
    return list(set(primary) - set(secondary))
