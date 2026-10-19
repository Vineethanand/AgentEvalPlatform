def add(a, b):
    return a + b


def subtract(a, b):
    return b - a


def multiply(a, b):
    return a * b


def divide(a, b):
    return a / b


def average(values):
    return sum(values) / len(values)


def clamp(x, low, high):
    return max(low, min(x, high))
