# robots.py

import asyncio
import logging
import time
from typing import Optional
from urllib import robotparser
from urllib.parse import urlparse

import httpx

from configuration import Configuration
from outils_url import normaliser_url

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(10.0, connect=5.0)
TIMEOUT_TOTAL = 20.0
MAX_OCTETS = 512 * 1024      # un robots.txt plus gros est tronqué
TTL_OK = 3600                # durée de vie du cache d'un robots.txt lu
TTL_ECHEC = 300              # on réessaie plus vite après un échec
CRAWL_DELAY_MAX = 30.0       # un Crawl-delay démesuré ne doit pas bloquer un site


class GestionnaireRobots:
    """Lecture asynchrone et mise en cache de robots.txt (ne bloque pas la boucle).

    `verifier(url)` retourne :
      - True  : l'URL peut être téléchargée ;
      - False : elle est interdite par robots.txt ;
      - None  : robots.txt est indisponible (erreur 5xx, 429, réseau). Ce n'est
                pas un refus : l'appelant doit réessayer plus tard.
    Une réponse 4xx (pas de robots.txt) autorise tout, comme le prévoit la RFC 9309.
    """

    def __init__(self, config: Configuration):
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
        # origine ("https://site.com") -> (expiration, analyseur ou None si indisponible)
        self._cache: dict[str, tuple[float, Optional[robotparser.RobotFileParser]]] = {}
        self._verrous: dict[str, asyncio.Lock] = {}

    def _obtenir_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                follow_redirects=True,
                max_redirects=5,
                timeout=TIMEOUT,
                headers={"User-Agent": self.config.user_agent},
            )
        return self._client

    async def fermer(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def _origine(url: str) -> str:
        p = urlparse(normaliser_url(url) or url)
        return f"{p.scheme}://{p.netloc}"

    async def _lire(self, origine: str) -> tuple[int, str]:
        async with self._obtenir_client().stream("GET", f"{origine}/robots.txt") as rep:
            if rep.status_code != 200:
                return rep.status_code, ""
            morceaux: list[bytes] = []
            taille = 0
            async for morceau in rep.aiter_bytes():
                morceaux.append(morceau)
                taille += len(morceau)
                if taille > MAX_OCTETS:
                    break
            texte = b"".join(morceaux)[:MAX_OCTETS].decode("utf-8", errors="replace")
            return 200, texte

    async def _charger(self, origine: str) -> tuple[Optional[robotparser.RobotFileParser], int]:
        try:
            statut, texte = await asyncio.wait_for(self._lire(origine), TIMEOUT_TOTAL)
        except (httpx.RequestError, asyncio.TimeoutError) as e:
            motif = f"{type(e).__name__}: {e}".rstrip(": ")
        else:
            rp = robotparser.RobotFileParser()
            if statut == 200:
                rp.parse(texte.splitlines())
                return rp, TTL_OK
            if 400 <= statut < 500 and statut not in (408, 429):
                rp.allow_all = True  # pas de robots.txt : tout est permis
                return rp, TTL_OK
            motif = f"HTTP {statut}"

        logger.warning("robots.txt de %s indisponible (%s)", origine, motif)
        return None, TTL_ECHEC

    async def _analyseur(self, url: str) -> Optional[robotparser.RobotFileParser]:
        origine = self._origine(url)
        # Un verrou par site : plusieurs travailleurs qui arrivent en même temps
        # sur un nouveau domaine ne téléchargent robots.txt qu'une seule fois.
        verrou = self._verrous.setdefault(origine, asyncio.Lock())
        async with verrou:
            entree = self._cache.get(origine)
            if entree and entree[0] > time.monotonic():
                return entree[1]
            rp, ttl = await self._charger(origine)
            self._cache[origine] = (time.monotonic() + ttl, rp)
            return rp

    async def verifier(self, url: str) -> Optional[bool]:
        if not self.config.respecter_robots_txt:
            return True
        rp = await self._analyseur(url)
        if rp is None:
            return None
        return rp.can_fetch(self.config.user_agent, url)

    async def delai_crawl(self, url: str) -> Optional[float]:
        """Crawl-delay demandé par le site, en secondes (plafonné), ou None."""
        if not self.config.respecter_robots_txt:
            return None
        rp = await self._analyseur(url)
        if rp is None:
            return None
        delai = rp.crawl_delay(self.config.user_agent)
        return min(float(delai), CRAWL_DELAY_MAX) if delai is not None else None
