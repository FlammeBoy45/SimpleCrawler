# sharingan_crawl/pipeline/pipeline.py
import sqlite3
import json
from abc import ABC, abstractmethod
from modeles import PageAnalysee


class InterfacePipeline(ABC):
    @abstractmethod
    def sauvegarder(self, page: PageAnalysee) -> None:
        pass

    @abstractmethod
    def fermer(self) -> None:
        pass


class PipelineSQLite(InterfacePipeline):
    def __init__(self, chemin_db: str = "resultats_crawl.db"):
        self.chemin_db = chemin_db
        self.connexion = sqlite3.connect(self.chemin_db)
        self._creer_table()

    def _creer_table(self) -> None:
        curseur = self.connexion.cursor()
        curseur.execute("""
            CREATE TABLE IF NOT EXISTS pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE,
                titre TEXT,
                date_extraction TEXT,
                liens_extraits TEXT,
                donnees TEXT
            )
        """)
        self.connexion.commit()

    def sauvegarder(self, page: PageAnalysee) -> None:
        curseur = self.connexion.cursor()
        curseur.execute("""
            INSERT OR REPLACE INTO pages (url, titre, date_extraction, liens_extraits, donnees)
            VALUES (?, ?, ?, ?, ?)
        """, (
            page.url,
            page.titre,
            page.date_extraction.isoformat(),
            json.dumps(page.liens_extraits),
            json.dumps(page.donnees)
        ))
        self.connexion.commit()

    def fermer(self) -> None:
        self.connexion.close()