# sharingan_crawl/configuration.py
from dataclasses import dataclass, field
from typing import List


@dataclass
class Configuration:
    delai_aspiration_sec: float = 1.0
    profondeur_max: int = 3
    user_agent: str = "SharinganCrawl/1.0 (+https://example.com)"
    urls_initiales: List[str] = field(default_factory=list)
    respecter_robots_txt: bool = True