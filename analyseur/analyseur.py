import logging
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from modeles import PageBrute, PageAnalysee
from outils_url import normaliser_url

logger = logging.getLogger(__name__)


class _ExtracteurHTML(HTMLParser):
    def __init__(self, url_base: str):
        super().__init__(convert_charrefs=True)
        self.url_base = url_base
        self.titre: str = ""
        self.liens: List[str] = []
        self.nofollow_page: bool = False

        self._dans_titre = False
        self._titre_termine = False
        self._donnees_titre: List[str] = []
        self._profondeur_svg = 0
        self._base_definie = False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        attributs: Dict[str, Optional[str]] = {nom.lower(): val for nom, val in attrs}

        if tag == "svg":
            self._profondeur_svg += 1

        elif tag == "title":
            # Seul le premier <title> hors SVG est le titre de la page.
            if not self._titre_termine and self._profondeur_svg == 0:
                self._dans_titre = True

        elif tag == "base":
            href = (attributs.get("href") or "").strip()
            if href and not self._base_definie:
                self._base_definie = True
                try:
                    self.url_base = urljoin(self.url_base, href)
                except ValueError:
                    logger.debug("<base href> invalide ignoré : %r", href)

        elif tag == "meta":
            if (attributs.get("name") or "").lower() == "robots":
                if "nofollow" in (attributs.get("content") or "").lower():
                    self.nofollow_page = True

        elif tag == "a":
            href = (attributs.get("href") or "").strip()
            if not href:
                return
            # Heuristique : un href "www.exemple.com" sans schéma est traité
            # comme un lien externe plutôt que comme un chemin relatif.
            if href.lower().startswith("www."):
                href = "https://" + href
            try:
                self.liens.append(urljoin(self.url_base, href))
            except ValueError:
                # Une URL malformée ne doit pas faire perdre le reste de la page.
                logger.debug("Lien malformé ignoré : %r", href)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "svg" and self._profondeur_svg > 0:
            self._profondeur_svg -= 1
        elif tag == "title" and self._dans_titre:
            self._dans_titre = False
            self._titre_termine = True
            self.titre = " ".join("".join(self._donnees_titre).split())

    def handle_data(self, data: str) -> None:
        if self._dans_titre:
            self._donnees_titre.append(data)


class Analyseur:
    def __init__(self, extensions_exclues: Optional[set] = None):
        self.extensions_exclues = tuple(
            extensions_exclues
            or {".png", ".jpg", ".jpeg", ".gif", ".css", ".js", ".ico", ".svg", ".pdf"}
        )

    def _est_lien_valide(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        return not parsed.path.lower().endswith(self.extensions_exclues)

    def classifier_lien(self, url: str) -> str:
        chemin = urlparse(url).path.lower()
        if chemin.endswith(".pdf"):
            return "document"
        if chemin.endswith((".json", ".xml", ".api")):
            return "api"
        return "html"

    def analyser(self, page_brute: PageBrute) -> PageAnalysee:
        if page_brute.code_statut != 200 or not page_brute.contenu_html:
            return PageAnalysee(url=page_brute.url, titre="Erreur / Vide")

        # Après une redirection, les liens relatifs se résolvent contre l'URL
        # finale, pas contre l'URL demandée.
        url_finale = getattr(page_brute, "url_finale", None) or page_brute.url
        extracteur = _ExtracteurHTML(url_finale)
        try:
            extracteur.feed(page_brute.contenu_html)
            extracteur.close()
        except Exception:
            logger.warning(
                "Analyse HTML interrompue pour %s", page_brute.url, exc_info=True
            )

        liens_filtres: List[str] = []
        if not extracteur.nofollow_page:
            # On pré-remplit "vus" avec la page elle-même pour exclure les
            # auto-références (href="#", lien vers soi-même...).
            vus = set()
            for u in (page_brute.url, url_finale):
                url_page = normaliser_url(u)
                if url_page:
                    vus.add(url_page)

            for lien in extracteur.liens:
                lien_propre = normaliser_url(lien)
                if (
                    lien_propre is None
                    or lien_propre in vus
                    or not self._est_lien_valide(lien_propre)
                ):
                    continue
                vus.add(lien_propre)
                liens_filtres.append(lien_propre)

        return PageAnalysee(
            url=page_brute.url,
            titre=extracteur.titre,
            liens_extraits=liens_filtres,
            donnees={
                "total_liens_bruts": len(extracteur.liens),
                "nofollow_page": extracteur.nofollow_page,
            },
        )
