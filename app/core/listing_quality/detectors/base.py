from typing import Any, Dict, List, Protocol
from ..schemas import Issue

class ListingDetector(Protocol):
    code: str

    def evaluate(self, listing: Dict[str, Any], context: Dict[str, Any]) -> List[Issue]:
        ...
