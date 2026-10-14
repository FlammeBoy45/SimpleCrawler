# sharingan_crawl/planificateur/planificateur.py
from urllib.parse import urlparse
from urllib import robotparser
from typing import Optional
from collections import deque

from sharingan_crawl.modeles import RequeteURL
from sharingan_crawl.configuration import Configuration




class Planificateur:
    def __init__(self, config: Configuration):
        self.config = config
        self.file_attente: deque[RequeteURL] = deque()
        self.urls_vues: set[str] = set()
        self.analyseurs_robots: dict[str, robotparser.RobotFileParser] = {}

    def _obtenir_robots(self, url: str) -> Optional[robotparser.RobotFileParser]:
        parsed = urlparse(url)
        domaine = f"{parsed.scheme}://{parsed.netloc}"
        
        if domaine not in self.analyseurs_robots:
            rp = robotparser.RobotFileParser()
            rp.set_url(f"{domaine}/robots.txt")
            try:
                rp.read()
            except Exception:
                rp = None
            self.analyseurs_robots[domaine] = rp
            
        return self.analyseurs_robots[domaine]

    def est_autorise(self, url: str) -> bool:
        if not self.config.respecter_robots_txt:
            return True
            
        rp = self._obtenir_robots(url)
        if rp is None:
            return True
            
        return rp.can_fetch(self.config.user_agent, url)

    def ajouter(self, requete: RequeteURL) -> bool:
        if requete.url in self.urls_vues:
            return False
            
        if requete.profondeur > self.config.profondeur_max:
            return False
            
        if not self.est_autorise(requete.url):
            return False
            
        self.urls_vues.add(requete.url)
        self.file_attente.append(requete)
        return True

    def suivant(self) -> Optional[RequeteURL]:
        if not self.file_attente:
            return None
        return self.file_attente.popleft()

    def est_vide(self) -> bool:
        return len(self.file_attente) == 0