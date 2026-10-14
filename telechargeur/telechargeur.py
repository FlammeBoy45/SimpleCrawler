# sharingan_crawl/telechargeur/telechargeur.py
import time
import urllib.request
import urllib.error
from typing import Optional

from sharingan_crawl.configuration import Configuration
from sharingan_crawl.modeles import PageBrute


class Telechargeur:
    def __init__(self, config: Configuration):
        self.config = config
        self._dernier_appel: float = 0.0

    def _appliquer_rate_limiting(self) -> None:
        maintenant = time.time()
        ecoule = maintenant - self._dernier_appel
        if ecoule < self.config.delai_aspiration_sec:
            time.sleep(self.config.delai_aspiration_sec - ecoule)
        self._dernier_appel = time.time()

    def telecharger(self, url: str) -> PageBrute:
        self._appliquer_rate_limiting()
        
        entetes = {"User-Agent": self.config.user_agent}
        requete = urllib.request.Request(url, headers=entetes)
        
        debut = time.time()
        try:
            with urllib.request.urlopen(requete, timeout=10) as reponse:
                fin = time.time()
                temps_ms = (fin - debut) * 1000
                code_statut = reponse.getcode()
                contenu_html = reponse.read().decode("utf-8", errors="ignore")
                headers_dict = dict(reponse.headers.items())
                
                return PageBrute(
                    url=url,
                    code_statut=code_statut,
                    contenu_html=contenu_html,
                    en_tete=headers_dict,
                    temps_reponse_ms=temps_ms
                )
        except urllib.error.HTTPError as e:
            fin = time.time()
            return PageBrute(
                url=url,
                code_statut=e.code,
                contenu_html="",
                temps_reponse_ms=(fin - debut) * 1000,
                erreur=str(e)
            )
        except Exception as e:
            fin = time.time()
            return PageBrute(
                url=url,
                code_statut=0,
                contenu_html="",
                temps_reponse_ms=(fin - debut) * 1000,
                erreur=str(e)
            )