# orchestrateur.py

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from analyseur.analyseur import Analyseur
from configuration import Configuration
from modeles import PageAnalysee, PageBrute, RequeteURL
from outils_url import normaliser_url
from pipeline.pipeline import PipelineSQLite
from planificateur.planificateur import Planificateur
from robots import GestionnaireRobots
from telechargeur.telechargeur import Telechargeur

logger = logging.getLogger(__name__)

PAUSE_ATTENTE_SEC = 0.05  # un travailleur sans URL attend qu'un autre en produise


@dataclass
class Statistiques:
    pages: int = 0     # pages téléchargées, analysées et enregistrées
    erreurs: int = 0   # échecs HTTP/réseau
    ignorees: int = 0  # interdites par robots.txt, hors domaine, non HTML


def _est_transitoire(page: PageBrute) -> bool:
    """Échec qui peut disparaître en réessayant plus tard (réseau, 5xx, 429...)."""
    code = page.code_statut
    return code == 0 or code >= 500 or code in (408, 429)


class Orchestrateur:
    """Pilote le crawl avec `concurrence_max` travailleurs asynchrones.

    Cohérence en cas d'interruption ou de crash : une URL n'est considérée comme
    faite que lorsqu'elle figure dans la table `pages`. Les échecs transitoires
    (réseau, 5xx) ne sont pas enregistrés : l'URL est reprise au prochain démarrage.
    """

    def __init__(self, config: Configuration, db_path: Optional[str] = None):
        self.config = config
        db_path = db_path or config.chemin_db

        self.planificateur = Planificateur(config, db_path=db_path)
        self.telechargeur = Telechargeur(config)
        self.robots = GestionnaireRobots(config)
        self.analyseur = Analyseur()
        self.pipeline = PipelineSQLite(db_path)

        self._arret_demande = threading.Event()
        self._actifs = 0
        self.stats = Statistiques()

        # Toujours tenté : la déduplication du planificateur écarte les URL déjà
        # connues, et une nouvelle URL de départ est prise en compte même si une
        # ancienne file existe.
        for url in config.urls_initiales:
            self.planificateur.ajouter(RequeteURL(url=url, profondeur=0))

    # ------------------------------------------------------------------ #
    # Arrêt
    # ------------------------------------------------------------------ #
    def demander_arret(self) -> None:
        self._arret_demande.set()

    @property
    def arret_demande(self) -> bool:
        return self._arret_demande.is_set()

    # ------------------------------------------------------------------ #
    # Traitement d'une URL
    # ------------------------------------------------------------------ #
    def _enregistrer_sans_contenu(self, requete: RequeteURL, donnees: Dict[str, Any]) -> None:
        """Marque l'URL comme faite (elle ne sera pas reprise) en gardant la raison."""
        donnees = {**donnees, "profondeur": requete.profondeur}
        self.pipeline.sauvegarder(PageAnalysee(url=requete.url, donnees=donnees))

    async def _traiter_requete(self, requete: RequeteURL) -> None:
        url = requete.url
        logger.info("Aspiration : %s (profondeur %d)", url, requete.profondeur)

        # 1. robots.txt, contrôlé au moment du téléchargement
        autorise = await self.robots.verifier(url)
        if autorise is None:
            logger.warning("robots.txt indisponible : %s sera repris au prochain démarrage", url)
            self.stats.erreurs += 1
            return
        if autorise is False:
            logger.info("Interdit par robots.txt : %s", url)
            self._enregistrer_sans_contenu(requete, {"statut": "interdit_robots"})
            self.stats.ignorees += 1
            return

        # 2. Téléchargement (en respectant le Crawl-delay éventuel du site)
        delai = await self.robots.delai_crawl(url)
        page_brute = await self.telechargeur.telecharger(url, delai_min=delai)

        if page_brute.code_statut != 200 or page_brute.erreur:
            if _est_transitoire(page_brute):
                logger.warning(
                    "Échec transitoire sur %s (%s) : repris au prochain démarrage",
                    url, page_brute.erreur or f"HTTP {page_brute.code_statut}",
                )
            else:
                logger.warning(
                    "Échec définitif sur %s (%s)",
                    url, page_brute.erreur or f"HTTP {page_brute.code_statut}",
                )
                self._enregistrer_sans_contenu(
                    requete,
                    {"code_statut": page_brute.code_statut, "erreur": page_brute.erreur},
                )
            if page_brute.code_statut == 200:
                self.stats.ignorees += 1  # page servie mais pas du HTML
            else:
                self.stats.erreurs += 1
            return

        # 3. Redirections : l'URL finale doit rester dans le périmètre du crawl
        url_finale = page_brute.url_finale or url
        redirige = normaliser_url(url_finale) != normaliser_url(url)
        if redirige:
            if not self.planificateur.est_interne_ou_autorise(url_finale):
                logger.info("Redirection externe ignorée : %s -> %s", url, url_finale)
                self._enregistrer_sans_contenu(
                    requete, {"statut": "redirection_externe", "url_finale": url_finale}
                )
                self.stats.ignorees += 1
                return
            if await self.robots.verifier(url_finale) is False:
                logger.info("URL finale interdite par robots.txt : %s", url_finale)
                self._enregistrer_sans_contenu(
                    requete, {"statut": "interdit_robots", "url_finale": url_finale}
                )
                self.stats.ignorees += 1
                return

        # 4. Analyse
        page_analysee = self.analyseur.analyser(page_brute)
        page_analysee.donnees["profondeur"] = requete.profondeur
        if redirige:
            page_analysee.donnees["url_finale"] = url_finale
        logger.info(
            "Analysé : %s (%d liens trouvés)",
            page_analysee.titre or "Sans titre", len(page_analysee.liens_extraits),
        )

        # 5. Propager les liens avant d'enregistrer la page, sauf si un arrêt
        #    est demandé ; la page traitée est toujours enregistrée.
        if requete.profondeur < self.config.profondeur_max:
            for lien in page_analysee.liens_extraits:
                if self._arret_demande.is_set():
                    break
                self.planificateur.ajouter(
                    RequeteURL(url=lien, profondeur=requete.profondeur + 1)
                )
        self.pipeline.sauvegarder(page_analysee)
        self.stats.pages += 1

    # ------------------------------------------------------------------ #
    # Boucle principale
    # ------------------------------------------------------------------ #
    async def _travailleur(self) -> None:
        while not self._arret_demande.is_set():
            requete = self.planificateur.suivant()
            if requete is None:
                if self._actifs == 0:
                    return  # file vide et personne ne peut plus y ajouter de liens
                await asyncio.sleep(PAUSE_ATTENTE_SEC)
                continue

            # Pas d'await entre suivant() et l'incrément : le compte est exact.
            self._actifs += 1
            try:
                await self._traiter_requete(requete)
            except Exception:
                logger.exception("Erreur inattendue sur %s", requete.url)
                self.stats.erreurs += 1
            finally:
                self._actifs -= 1

    async def _fermer_ressources(self) -> None:
        for nom, fermeture in (
            ("téléchargeur", self.telechargeur.fermer),
            ("robots", self.robots.fermer),
        ):
            try:
                await fermeture()
            except Exception:
                logger.exception("Fermeture impossible : %s", nom)
        for nom, fermeture in (
            ("pipeline", self.pipeline.fermer),
            ("planificateur", self.planificateur.fermer),
        ):
            try:
                fermeture()
            except Exception:
                logger.exception("Fermeture impossible : %s", nom)

    async def executer(self) -> None:
        logger.info(
            "Démarrage d'ALEXIA-BF (asynchrone, %d travailleurs)", self.config.concurrence_max
        )
        debut = time.monotonic()
        print(f"⏰ Heure de début : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            await asyncio.gather(
                *(self._travailleur() for _ in range(self.config.concurrence_max))
            )
            if self._arret_demande.is_set():
                print("\n🛑 Arrêt demandé. Crawl interrompu proprement ; "
                      "relancez la même commande pour reprendre.")
            else:
                print("🔥 Crawl terminé avec succès !")
        finally:
            await self._fermer_ressources()
            self._afficher_rapport(time.monotonic() - debut)

    def _afficher_rapport(self, duree_sec: float) -> None:
        h = int(duree_sec // 3600)
        m = int((duree_sec % 3600) // 60)
        s = int(duree_sec % 60)
        pages = self.stats.pages
        moyenne = duree_sec / pages if pages > 0 else 0

        print("\n📊 --- RAPPORT DE CRAWL ---")
        print(f"📄 Pages crawlées  : {pages}")
        print(f"⚠️ Erreurs         : {self.stats.erreurs}")
        print(f"⏭️ Ignorées        : {self.stats.ignorees}")
        print(f"⏱️ Durée totale    : {h}h {m}m {s}s")
        print(f"⚡ Moyenne par page : {moyenne:.2f} secondes")
        print(f"⏰ Heure de fin     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("--------------------------")
