# telechargeur/telechargeur.py
import time
import urllib.request
import urllib.error
from typing import Optional

from configuration import Configuration
from modeles import PageBrute


import httpx
import asyncio
import time
from modeles import PageBrute
from configuration import Configuration


class Telechargeur:
    def __init__(self, config: Configuration):
        self.config = config
        self._dernier_appel: float = 0.0

    async def _appliquer_rate_limiting(self) -> None:
        """Rate limiting asynchrone pour respecter la politesse sans bloquer la boucle."""
        maintenant = time.time()
        ecoule = maintenant - self._dernier_appel
        if ecoule < self.config.delai_aspiration_sec:
            delai_attente = self.config.delai_aspiration_sec - ecoule
            await asyncio.sleep(delai_attente)
        self._dernier_appel = time.time()

    async def telecharger(self, url: str) -> PageBrute:
        await self._appliquer_rate_limiting()

        entetes = {"User-Agent": self.config.user_agent}
        debut = time.time()

        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            try:
                reponse = await client.get(url, headers=entetes)
                fin = time.time()
                temps_ms = (fin - debut) * 1000
                
                return PageBrute(
                    url=url,
                    code_statut=reponse.status_code,
                    contenu_html=reponse.text,
                    en_tete=dict(reponse.headers),
                    temps_reponse_ms=temps_ms
                )
                
            except httpx.HTTPStatusError as e:
                fin = time.time()
                return PageBrute(
                    url=url,
                    code_statut=e.response.status_code,
                    contenu_html="",
                    en_tete=dict(e.response.headers) if e.response else {},
                    temps_reponse_ms=(fin - debut) * 1000,
                    erreur=str(e)
                )
                
            except (httpx.RequestError, httpx.TimeoutException) as e:
                fin = time.time()
                return PageBrute(
                    url=url,
                    code_statut=0,
                    contenu_html="",
                    en_tete={},
                    temps_reponse_ms=(fin - debut) * 1000,
                    erreur=str(e)
                )
            except Exception as e:
                fin = time.time()
                return PageBrute(
                    url=url,
                    code_statut=0,
                    contenu_html="",
                    en_tete={},
                    temps_reponse_ms=(fin - debut) * 1000,
                    erreur=str(e)
                )