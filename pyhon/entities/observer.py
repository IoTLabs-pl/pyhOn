import abc
from dataclasses import dataclass, field
from typing import Generic, Self, TypeVar

P = TypeVar("P")
T = TypeVar("T", bound="Observable")


class Subscriber(Generic[T], abc.ABC):
    @abc.abstractmethod
    def update(self, observable: "T"):
        pass


@dataclass
class Observable(Generic[P]):
    _data: P
    subscribers: set[Subscriber[Self]] = field(default_factory=set, init=False)

    def subscribe(self, subscriber: Subscriber[Self]):
        self.subscribers.add(subscriber)

    def unsubscribe(self, subscriber: Subscriber[Self]):
        self.subscribers.discard(subscriber)

    @property
    def data(self) -> P:
        return self._data

    @data.setter
    def data(self, value: P) -> None:
        self._data = value
        for subscriber in self.subscribers:
            subscriber.update(self)
