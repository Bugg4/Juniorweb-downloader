from magic import from_buffer
import json


def buffer_is_pdf(buffer) -> tuple[bool, str]:
    detected_type: str = from_buffer(buffer)
    return ("PDF document" in detected_type, detected_type)


def difference_between_dict_lists(primary, secondary, keys=None):
    """
    Returns a list of dictionaries that are in the primary list but not in the secondary list,
    considering only the specified keys for comparison.

    Args:
        primary (list): List of dictionaries to compare from.
        secondary (list): List of dictionaries to compare against.
        keys (list, optional): List of keys to consider for comparison. If None, all keys are considered.

    Returns:
        list: A list of dictionaries that are in `primary` but not in `secondary`.
    """

    def filter_keys(item, keys):
        """Filter a dictionary to include only the specified keys."""
        if keys:
            return {k: item[k] for k in keys if k in item}
        return item

    # Convert secondary dictionaries to sets of their filtered key-value pairs
    secondary_set = {frozenset(filter_keys(item, keys).items()) for item in secondary}

    # Find all dictionaries in primary that are not in secondary
    difference = [
        item
        for item in primary
        if frozenset(filter_keys(item, keys).items()) not in secondary_set
    ]

    return difference
