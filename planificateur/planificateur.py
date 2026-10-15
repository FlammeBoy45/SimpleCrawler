from urllib.parse import urlparse
from urllib import robotparser
from typing import Optional
from collections import deque

from modeles import RequeteURL
from configuration import Configuration


class Planificateur:
    def __init__(self, config: Configuration):
        self.config = config
        self.file_attente: deque[RequeteURL] = deque()
        self.urls_vues: set[str] = set()
        self.analyseurs_robots: dict[str, robotparser.RobotFileParser] = {}
        
        # On extrait les domaines autorisés à partir des URLs initiales
        self.domaines_autorises: set[str] = {
            urlparse(url).netloc for url in self.config.urls_initiales
        }

    def _normaliser_domaine(self, netloc: str) -> str:
        """Retire le préfixe 'www.' pour uniformiser la comparaison."""
        netloc = netloc.lower()
        if netloc.startswith("www."):
            return netloc[4:]
        return netloc

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

    def est_interne_ou_autorise(self, url: str) -> bool:
        """Vérifie si le lien appartient au même domaine de base (avec ou sans www)."""
        if self.config.suivre_liens_externes:
            return True
            
        parsed_url = urlparse(url)
        domaine_lien = self._normaliser_domaine(parsed_url.netloc)
        
        # Normalisation de tous les domaines autorisés de référence
        domaines_base_normalises = {
            self._normaliser_domaine(d) for d in self.domaines_autorises
        }
        
        return domaine_lien in domaines_base_normalises

    def ajouter(self, requete: RequeteURL) -> bool:
        if requete.url in self.urls_vues:
            return False
            
        if requete.profondeur > self.config.profondeur_max:
            return False
            
        # Filtrage des liens externes si l'option est désactivée
        if not self.est_interne_ou_autorise(requete.url):
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