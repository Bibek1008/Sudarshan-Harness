def clamp(value, low, high):
    if low > high:
        raise ValueError("reversed bounds")
    return max(low, min(high, value))
