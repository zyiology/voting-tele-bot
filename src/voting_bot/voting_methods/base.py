from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar


BallotT = TypeVar("BallotT")
ResultT = TypeVar("ResultT")


class VotingMethod(ABC, Generic[BallotT, ResultT]):
    @abstractmethod
    def tally(self, ballots: list[BallotT]) -> ResultT:
        """Return aggregate results for a collection of ballots."""
