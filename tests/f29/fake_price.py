import math


class FakePriceModel:
    def __init__(self, price: float = 100000.0, error: Exception | None = None):
        self.price, self.error = price, error
        self.seen: list = []

    def predict(self, texts):
        self.seen.append(list(texts))
        if self.error:
            raise self.error
        return [math.log(self.price)] * len(texts)
