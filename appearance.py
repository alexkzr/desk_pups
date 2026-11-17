"""Persistent coat choices; rendering never consumes the behaviour RNG."""
from dataclasses import asdict, dataclass
import random

STYLES = ('Мультяшная',)
COATS = ('Рыжая', 'Чёрно-подпалая', 'Мраморная')
FURS = ('Гладкая', 'Длинная')


@dataclass(frozen=True)
class Appearance:
    style: int = 0
    coat: int = 0
    fur: int = 0
    seed: int = 1

    def __post_init__(self):
        # Keep the legacy field readable while migrating every dog to one model.
        object.__setattr__(self,'style',0)

    @classmethod
    def random(cls):
        return cls(0, random.randrange(3), random.randrange(2),
                   random.randrange(1, 2**31))

    @classmethod
    def restore(cls, value):
        if not isinstance(value, dict):
            return cls.random()
        limits = {'style': 0, 'coat': 2, 'fur': 1, 'seed': 2**31-1}
        values = {}
        for key, maximum in limits.items():
            try:
                values[key] = max(0, min(maximum, int(value.get(key, 0))))
            except (ValueError, TypeError, OverflowError):
                values[key] = 0
        return cls(**values)

    def serialize(self):
        return asdict(self)

    @property
    def description(self):
        return f'{STYLES[self.style]} · {COATS[self.coat]} · {FURS[self.fur]} шерсть'
