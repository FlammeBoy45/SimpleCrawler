import logging
import os
import sqlite3
from collections import deque
from typing import Optional

from configuration import Configuration
from modeles import RequeteURL
from outils_url import cle_deduplication, domaine_de

logger = logging.getLogger(__name__)


class Planificateur:
    """File d'attente d'URL à crawler, persistante.

    Le contrôle de robots.txt n'est pas fait ici (il demande du réseau) : voir
    `robots.GestionnaireRobots`, appelé par l'orchestrateur au moment du
    téléchargement. `ajouter()` est donc rapide et sans réseau.

    Persistance : la table `file_attente` vit dans une base *séparée* de la base
    de résultats (voir `chemin_etat`), pour ne jamais se disputer le verrou
    d'écriture SQLite avec le pipeline. Les pages déjà crawlées sont lues dans
    la table `pages` de la base de résultats (lecture seule).

    Reprise après interruption : une URL n'est PAS retirée de `file_attente`
    quand `suivant()` la rend ; elle est nettoyée au prochain démarrage si sa
    page a bien été enregistrée dans `pages`. Ainsi, une URL en cours de
    traitement au moment d'un crash est reprise au lieu d'être perdue.

    Non thread-safe : à appeler depuis la boucle principale.
    """

    def __init__(
        self,
        config: Configuration,
        db_path: str = "resultats_crawl.db",
        chemin_etat: Optional[str] = None,
    ):
        self.config = config
        self.db_path = db_path
        if chemin_etat is None:
            chemin_etat = (
                ":memory:"
                if db_path == ":memory:"
                else os.path.splitext(db_path)[0] + "_etat.db"
            )
        self.chemin_etat = chemin_etat

        self.file_attente: deque[RequeteURL] = deque()
        self.urls_vues: set[str] = set()

        self.domaines_autorises: set[str] = {
            d for d in (domaine_de(u) for u in config.urls_initiales) if d
        }

        self._conn = self._ouvrir_etat()
        self._charger_etat_persistant()

    # ------------------------------------------------------------------ #
    # Persistance
    # ------------------------------------------------------------------ #
    def _ouvrir_etat(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.chemin_etat)
        # WAL + synchronous=NORMAL : un commit par opération reste peu coûteux
        # et protège contre un crash du processus.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS file_attente (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                profondeur INTEGER NOT NULL
            )
        """)
        conn.commit()
        return conn

    def _lire_urls_crawlees(self) -> list[str]:
        """URL déjà enregistrées par le pipeline (lecture seule)."""
        if self.db_path == ":memory:" or not os.path.exists(self.db_path):
            return []
        conn = sqlite3.connect(self.db_path)
        try:
            existe = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='pages'"
            ).fetchone()
            if not existe:
                return []
            return [ligne[0] for ligne in conn.execute("SELECT url FROM pages")]
        finally:
            conn.close()

    def _charger_etat_persistant(self) -> None:
        for url in self._lire_urls_crawlees():
            cle = cle_deduplication(url)
            if cle:
                self.urls_vues.add(cle)
        nb_crawlees = len(self.urls_vues)

        a_nettoyer: list[tuple[str]] = []
        lignes = self._conn.execute(
            "SELECT url, profondeur FROM file_attente ORDER BY id"
        ).fetchall()
        for url, profondeur in lignes:
            cle = cle_deduplication(url)
            if cle is None or cle in self.urls_vues:
                a_nettoyer.append((url,))  # déjà crawlée (ou doublon/invalide)
            else:
                self.urls_vues.add(cle)
                self.file_attente.append(RequeteURL(url=url, profondeur=profondeur))
                if not self.config.urls_initiales:
                    domaine = domaine_de(url)
                    if domaine:
                        self.domaines_autorises.add(domaine)

        if a_nettoyer:
            self._conn.executemany("DELETE FROM file_attente WHERE url = ?", a_nettoyer)
            self._conn.commit()

        logger.info(
            "Planificateur : %d pages déjà crawlées, %d URL reprises dans la file.",
            nb_crawlees,
            len(self.file_attente),
        )

    def _persister(self, requete: RequeteURL) -> None:
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO file_attente (url, profondeur) VALUES (?, ?)",
                (requete.url, requete.profondeur),
            )
            self._conn.commit()
        except sqlite3.Error:
            # Le crawl continue, mais cette URL ne survivrait pas à un redémarrage.
            logger.exception("Persistance impossible pour %s", requete.url)

    def fermer(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        self.fermer()

    # ------------------------------------------------------------------ #
    # API publique
    # ------------------------------------------------------------------ #
    def est_interne_ou_autorise(self, url: str) -> bool:
        if self.config.suivre_liens_externes:
            return True
        return domaine_de(url) in self.domaines_autorises

    def ajouter(self, requete: RequeteURL) -> bool:
        cle = cle_deduplication(requete.url)
        if cle is None or cle in self.urls_vues:
            return False
        if requete.profondeur > self.config.profondeur_max:
            return False
        if not self.est_interne_ou_autorise(requete.url):
            return False

        self.urls_vues.add(cle)
        self.file_attente.append(requete)
        self._persister(requete)
        return True

    def suivant(self) -> Optional[RequeteURL]:
        if not self.file_attente:
            return None
        # Volontairement, pas de suppression en base ici (voir la docstring).
        return self.file_attente.popleft()

    def est_vide(self) -> bool:
        return len(self.file_attente) == 0
