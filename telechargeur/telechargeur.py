# telechargeur/telechargeur.py

import asyncio
import codecs
import logging
import re
import time
from typing import Optional
from urllib.parse import urlparse

import httpx

from configuration import Configuration
from modeles import PageBrute

logger = logging.getLogger(__name__)

# À terme, ces réglages ont leur place dans configuration.py.
TIMEOUT = httpx.Timeout(10.0, connect=5.0)  # délai par opération réseau
TIMEOUT_TOTAL = 30.0          # durée maximale d'une tentative (corps compris)
MAX_REDIRECTIONS = 5
MAX_OCTETS = 2 * 1024 * 1024  # au-delà, le corps est tronqué
TENTATIVES_MAX = 3
PAUSE_RETRY_BASE = 1.0        # 1 s, 2 s, 4 s...
PAUSE_RETRY_MAX = 30.0
STATUTS_TRANSITOIRES = {429, 502, 503, 504}
TYPES_HTML = {"text/html", "application/xhtml+xml"}

_RE_CHARSET_ENTETE = re.compile(r"charset\s*=\s*[\"']?([\w.:-]+)", re.I)
_RE_CHARSET_HTML = re.compile(rb"charset\s*=\s*[\"']?\s*([\w.:-]+)", re.I)


def _decrire(erreur: BaseException) -> str:
    """Les timeouts httpx ont souvent un message vide : on garde au moins le type."""
    return f"{type(erreur).__name__}: {erreur}".rstrip(": ")


class Telechargeur:
    """Téléchargeur asynchrone.

    - Un seul `httpx.AsyncClient` partagé (réutilisation des connexions),
      créé à la première requête. Appeler `await fermer()` à la fin du crawl,
      ou utiliser `async with Telechargeur(config) as t:`.
    - Politesse par hôte : deux requêtes vers le même site sont espacées d'au
      moins `delai_aspiration_sec` (ou du Crawl-delay du site si plus grand),
      même si plusieurs coroutines appellent `telecharger` en parallèle.
    """

    def __init__(self, config: Configuration):
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
        self._verrous: dict[str, asyncio.Lock] = {}
        self._prochain_creneau: dict[str, float] = {}

    # ------------------------------------------------------------------ #
    # Cycle de vie
    # ------------------------------------------------------------------ #
    def _obtenir_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                follow_redirects=True,
                max_redirects=MAX_REDIRECTIONS,
                timeout=TIMEOUT,
                headers={
                    "User-Agent": self.config.user_agent,
                    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
                },
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    async def fermer(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.fermer()

    # ------------------------------------------------------------------ #
    # Politesse
    # ------------------------------------------------------------------ #
    async def _attendre_son_tour(self, url: str, delai_min: Optional[float]) -> None:
        hote = (urlparse(url).hostname or "").lower()
        delai = max(self.config.delai_aspiration_sec, delai_min or 0.0)
        verrou = self._verrous.setdefault(hote, asyncio.Lock())
        # Le verrou fait la queue : chaque appelant réserve le créneau suivant.
        async with verrou:
            attente = self._prochain_creneau.get(hote, 0.0) - time.monotonic()
            if attente > 0:
                await asyncio.sleep(attente)
            self._prochain_creneau[hote] = time.monotonic() + delai

    # ------------------------------------------------------------------ #
    # Téléchargement
    # ------------------------------------------------------------------ #
    async def telecharger(self, url: str, delai_min: Optional[float] = None) -> PageBrute:
        """Télécharge `url`. `delai_min` permet de passer le Crawl-delay du site
        (voir `Planificateur.delai_crawl`). Ne lève jamais : en cas d'échec,
        retourne une PageBrute avec `code_statut=0` et `erreur` renseigné."""
        for tentative in range(1, TENTATIVES_MAX + 1):
            await self._attendre_son_tour(url, delai_min)
            debut = time.perf_counter()
            try:
                page = await asyncio.wait_for(self._une_tentative(url, debut), TIMEOUT_TOTAL)
                transitoire = page.code_statut in STATUTS_TRANSITOIRES
            except (httpx.RequestError, asyncio.TimeoutError) as e:
                page = self._page_erreur(url, debut, _decrire(e))
                transitoire = True
            except Exception as e:
                logger.exception("Erreur inattendue en téléchargeant %s", url)
                return self._page_erreur(url, debut, _decrire(e))

            if not transitoire or tentative == TENTATIVES_MAX:
                return page

            pause = self._pause_avant_retry(page, tentative)
            logger.info(
                "%s : %s, nouvelle tentative (%d/%d) dans %.1f s",
                url, page.erreur or f"HTTP {page.code_statut}", tentative + 1,
                TENTATIVES_MAX, pause,
            )
            await asyncio.sleep(pause)

        raise AssertionError("inatteignable")  # pragma: no cover

    async def _une_tentative(self, url: str, debut: float) -> PageBrute:
        html, erreur = "", None
        async with self._obtenir_client().stream("GET", url) as reponse:
            statut = reponse.status_code
            en_tete = dict(reponse.headers)
            url_finale = str(reponse.url)
            content_type = reponse.headers.get("content-type", "")
            type_contenu = content_type.split(";")[0].strip().lower()

            if not 200 <= statut < 300:
                pass  # le code de statut suffit ; on ne télécharge pas le corps
            elif type_contenu and type_contenu not in TYPES_HTML:
                erreur = f"Contenu ignoré (type {type_contenu})"
            else:
                corps, tronque = await self._lire_corps(reponse)
                html = self._decoder(corps, content_type)
                if tronque:
                    logger.warning("%s : corps tronqué à %d octets", url, MAX_OCTETS)

        return PageBrute(
            url=url,
            code_statut=statut,
            contenu_html=html,
            en_tete=en_tete,
            temps_reponse_ms=(time.perf_counter() - debut) * 1000,
            erreur=erreur,
            url_finale=url_finale,
        )

    @staticmethod
    async def _lire_corps(reponse: httpx.Response) -> tuple[bytes, bool]:
        morceaux: list[bytes] = []
        taille = 0
        async for morceau in reponse.aiter_bytes():  # déjà décompressé
            morceaux.append(morceau)
            taille += len(morceau)
            if taille > MAX_OCTETS:
                return b"".join(morceaux)[:MAX_OCTETS], True
        return b"".join(morceaux), False

    @staticmethod
    def _decoder(corps: bytes, content_type: str) -> str:
        """Charset de l'en-tête HTTP, sinon <meta charset> (fréquent sur les
        sites français en ISO-8859-1), sinon UTF-8."""
        m = _RE_CHARSET_ENTETE.search(content_type)
        encodage = m.group(1) if m else None
        if encodage is None:
            m2 = _RE_CHARSET_HTML.search(corps[:2048])
            encodage = m2.group(1).decode("ascii", "ignore") if m2 else "utf-8"
        try:
            codecs.lookup(encodage)
        except LookupError:
            encodage = "utf-8"
        return corps.decode(encodage, errors="replace")

    @staticmethod
    def _pause_avant_retry(page: PageBrute, tentative: int) -> float:
        pause = PAUSE_RETRY_BASE * 2 ** (tentative - 1)
        entetes = {k.lower(): v for k, v in (page.en_tete or {}).items()}
        retry_after = str(entetes.get("retry-after", "")).strip()
        if retry_after.isdigit():  # la forme « date HTTP » est ignorée
            pause = max(pause, int(retry_after))
        return min(pause, PAUSE_RETRY_MAX)

    @staticmethod
    def _page_erreur(url: str, debut: float, erreur: str) -> PageBrute:
        return PageBrute(
            url=url,
            code_statut=0,
            contenu_html="",
            en_tete={},
            temps_reponse_ms=(time.perf_counter() - debut) * 1000,
            erreur=erreur,
        )
