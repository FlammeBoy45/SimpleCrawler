# configuration.py

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Configuration:
    # Mêmes noms et même ordre qu'avant : les appels existants restent valides.
    urls_initiales: Optional[List[str]] = field(default_factory=list)
    profondeur_max: int = 2
    respecter_robots_txt: bool = False
    user_agent: str = "ALEXIA-BF/1.0"
    suivre_liens_externes: bool = False
    concurrence_max: int = 5
    delai_aspiration_sec: float = 0.5
    chemin_db: str = "resultats_crawl.db"

    def __post_init__(self) -> None:
        self.urls_initiales = list(self.urls_initiales or [])
        if self.concurrence_max < 1:
            raise ValueError("concurrence_max doit être >= 1")
        if self.profondeur_max < 0:
            raise ValueError("profondeur_max doit être >= 0")
        if self.delai_aspiration_sec < 0:
            raise ValueError("delai_aspiration_sec doit être >= 0")
