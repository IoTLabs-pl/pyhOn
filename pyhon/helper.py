def str_to_float(string: str | float | int) -> float | int:
    try:
        return int(string)
    except ValueError:
        return float(str(string).replace(",", "."))
