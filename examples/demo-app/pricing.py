"""Example business rule. Run the demo acceptance checks against this module."""

def total(price: float, quantity: int, discount_percent: float = 0) -> float:
    if price < 0 or quantity < 0 or not 0 <= discount_percent <= 100:
        raise ValueError("Invalid inputs")
    return round(price * quantity * (1 - discount_percent / 100), 2)
