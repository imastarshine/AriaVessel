

def safe_get_from_list(source_list: list, index: int):
    try:
        return source_list[index]
    except IndexError:
        return None
