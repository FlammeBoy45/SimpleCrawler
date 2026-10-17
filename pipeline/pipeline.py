# pipeline/pipeline.py

import json
import logging
import sqlite3
import threading
from abc import ABC, abstractmethod

from modeles import PageAnalysee

logger = logging.getLogger(__name__)


class InterfacePipeline(ABC):
    @abstractmethod
    def sauvegarder(self, page: PageAnalysee) -> None:
        pass

    @abstractmethod
    def fermer(self) -> None:
        pass

    # Permet d'écrire `with PipelineSQLite(...) as pipeline:` et garantit
    # que fermer() est appelé même en cas d'exception.
    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        self.fermer()


class PipelineSQLite(InterfacePipeline):
    _UPSERT = """
        INSERT INTO pages (url, titre, date_extraction, liens_extraits, donnees)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            titre = excluded.titre,
            date_extraction = excluded.date_extraction,
            liens_extraits = excluded.liens_extraits,
            donnees = excluded.donnees
    """

    def __init__(self, chemin_db: str = "resultats_crawl.db", taille_lot: int = 50):
        """
        taille_lot : nombre de pages entre deux commit. 1 = commit à chaque page
        (comportement d'origine, le plus sûr mais le plus lent). Au plus
        `taille_lot - 1` pages sont perdues en cas de crash brutal.
        """
        self.chemin_db = chemin_db
        self.taille_lot = max(1, taille_lot)
        self._verrou = threading.Lock()
        self._en_attente = 0
        self._ferme = False

        # check_same_thread=False + verrou : sûr si l'orchestrateur écrit
        # depuis plusieurs threads.
        self.connexion = sqlite3.connect(self.chemin_db, check_same_thread=False)
        self.connexion.execute("PRAGMA journal_mode=WAL")
        self._creer_table()

    def _creer_table(self) -> None:
        with self._verrou:
            self.connexion.execute("""
                CREATE TABLE IF NOT EXISTS pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    titre TEXT,
                    date_extraction TEXT,
                    liens_extraits TEXT,
                    donnees TEXT
                )
            """)
            self.connexion.commit()

    def sauvegarder(self, page: PageAnalysee) -> None:
        # La sérialisation est faite avant de toucher à la base : une erreur
        # ici ne laisse aucune écriture à moitié faite.
        # ensure_ascii=False garde les accents lisibles ; default=str évite
        # un crash sur une valeur non sérialisable (datetime, set...).
        params = (
            page.url,
            page.titre,
            page.date_extraction.isoformat(),
            json.dumps(page.liens_extraits, ensure_ascii=False),
            json.dumps(page.donnees, ensure_ascii=False, default=str),
        )
        with self._verrou:
            self.connexion.execute(self._UPSERT, params)
            self._en_attente += 1
            if self._en_attente >= self.taille_lot:
                self._valider_sans_verrou()

    def valider(self) -> None:
        """Force le commit des pages en attente."""
        with self._verrou:
            self._valider_sans_verrou()

    def _valider_sans_verrou(self) -> None:
        self.connexion.commit()
        self._en_attente = 0

    def fermer(self) -> None:
        with self._verrou:
            if self._ferme:
                return
            self._valider_sans_verrou()
            self.connexion.close()
            self._ferme = True
