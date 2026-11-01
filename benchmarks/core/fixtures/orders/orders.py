def total(items, member=False):
    if member:
        value = 0
        for price, quantity in items:
            value += price * quantity
        return value * 0.9
    else:
        value = 0
        for price, quantity in items:
            value += price * quantity
        return value
