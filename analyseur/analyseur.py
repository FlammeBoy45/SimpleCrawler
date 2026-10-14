# sharingan_crawl/analyseur/analyseur.py
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from typing import List, Tuple

from sharingan_crawl.modeles import PageBrute, PageAnalysee


class _ExtracteurHTML(HTMLParser):
    def __init__(self, url_base: str):
        super().__init__()
        self.url_base = url_base
        self.titre: str = ""
        self.liens: List[str] = []
        self._en_train_de_lire_titre = False
        self._donnees_titre = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, str]]) -> None:
        if tag.lower() == "title":
            self._en_train_de_lire_titre = True
        elif tag.lower() == "a":
            for nom, valeur in attrs:
                if nom.lower() == "href" and valeur:
                    url_absolue = urljoin(self.url_base, valeur)
                    self.liens.append(url_absolue)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._en_train_de_lire_titre = False
            self.titre = "".join(self._donnees_titre).strip()

    def handle_data(self, data: str) -> None:
        if self._en_train_de_lire_titre:
            self._donnees_titre.append(data)


class Analyseur:
    def __init__(self):
        self.extensions_exclues = {".png", ".jpg", ".jpeg", ".gif", ".css", ".js", ".ico", ".svg", ".pdf"}

    def _est_lien_valide(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        
        chemin = parsed.path.lower()
        if any(chemin.endswith(ext) for ext in self.extensions_exclues):
            return False
            
        return True

    def classifier_lien(self, url: str) -> str:
        parsed = urlparse(url)
        chemin = parsed.path.lower()
        if chemin.endswith(".pdf"):
            return "document"
        elif any(chemin.endswith(ext) for ext in (".json", ".xml", ".api")):
            return "api"
        return "html"

    def analyser(self, page_brute: PageBrute) -> PageAnalysee:
        if page_brute.code_statut != 200 or not page_brute.contenu_html:
            return PageAnalysee(url=page_brute.url, titre="Erreur / Vide")

        extracteur = _ExtracteurHTML(page_brute.url)
        try:
            extracteur.feed(page_brute.contenu_html)
        except Exception:
            pass

        liens_filtres = []
        vus = set()
        for lien in extracteur.liens:
            lien_propre = lien.split("#")[0]
            if lien_propre not in vus and self._est_lien_valide(lien_propre):
                vus.add(lien_propre)
                liens_filtres.append(lien_propre)

        return PageAnalysee(
            url=page_brute.url,
            titre=extracteur.titre,
            liens_extraits=liens_filtres,
            donnees={"total_liens_bruts": len(extracteur.liens)}
        )