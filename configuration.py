# sharingan_crawl/configuration.py
from dataclasses import dataclass, field
from typing import List


@dataclass
class Configuration:
    def __init__(
        self,
        urls_initiales=None,
        profondeur_max=2,
        respecter_robots_txt=True,
        user_agent="SharinganSpider/1.0",
        suivre_liens_externes=False,
        concurrence_max=5,
        delai_aspiration_sec=0.5
    ):
        self.urls_initiales = urls_initiales or ["https://presidencedufaso.bf/"]
        self.profondeur_max = profondeur_max
        self.respecter_robots_txt = respecter_robots_txt
        self.user_agent = user_agent
        self.suivre_liens_externes = suivre_liens_externes
        self.concurrence_max = concurrence_max
        self.delai_aspiration_sec = delai_aspiration_sec