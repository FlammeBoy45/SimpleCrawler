from urllib.parse import urlparse
from urllib import robotparser
from typing import Optional
from collections import deque
import sqlite3
import os

from modeles import RequeteURL
from configuration import Configuration


class Planificateur:
    def __init__(self, config: Configuration, db_path: str = "resultats_crawl.db"):
        self.config = config
        self.db_path = db_path
        self.file_attente: deque[RequeteURL] = deque()
        self.urls_vues: set[str] = set()
        self.analyseurs_robots: dict[str, robotparser.RobotFileParser] = {}
        
        self.domaines_autorises: set[str] = {
            urlparse(url).netloc for url in self.config.urls_initiales
        }

        # Initialiser les tables SQLite nécessaires si elles n'existent pas
        self._initialiser_base()

        # Charger l'état persistant (urls vues + file d'attente en suspens)
        self._charger_etat_persistant()

    def _initialiser_base(self) -> None:
        """Crée la table de la file d'attente persistante si elle n'existe pas."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS file_attente (
                    url TEXT PRIMARY KEY,
                    profondeur INTEGER
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"⚠️ [Planificateur] Erreur lors de l'initialisation de la table file_attente : {e}")

    def _normaliser_domaine(self, netloc: str) -> str:
        netloc = netloc.lower()
        if netloc.startswith("www."):
            return netloc[4:]
        return netloc

    def _normaliser_url(self, url: str) -> str:
        parsed = urlparse(url)
        netloc = self._normaliser_domaine(parsed.netloc)
        return parsed._replace(netloc=netloc).geturl()

    def _charger_etat_persistant(self) -> None:
        """Charge les URLs vues depuis 'pages' et la file d'attente depuis 'file_attente'."""
        if not os.path.exists(self.db_path):
            return
            
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 1. Charger les pages déjà crawlées (vues)
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pages';")
            if cursor.fetchone():
                cursor.execute("SELECT url FROM pages;")
                for row in cursor.fetchall():
                    self.urls_vues.add(self._normaliser_url(row[0]))
            
            # 2. Charger la file d'attente en suspens
            cursor.execute("SELECT url, profondeur FROM file_attente;")
            lignes_file = cursor.fetchall()
            
            for url, profondeur in lignes_file:
                url_norm = self._normaliser_url(url)
                if url_norm not in self.urls_vues:
                    self.file_attente.append(RequeteURL(url=url, profondeur=profondeur))
                    self.urls_vues.add(url_norm)

            print(f"📦 [Planificateur] Chargé depuis SQLite : {len(self.urls_vues)} URLs connues, {len(self.file_attente)} en attente dans la file.")
            conn.close()
        except Exception as e:
            print(f"⚠️ [Planificateur] Impossible de charger l'état persistant : {e}")

    def _sauvegarder_dans_file_sqlite(self, url: str, profondeur: int) -> None:
        """Ajoute une URL dans la file d'attente persistante SQLite."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO file_attente (url, profondeur) VALUES (?, ?)", (url, profondeur))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _retirer_de_file_sqlite(self, url: str) -> None:
        """Retire une URL de la file persistante SQLite une fois consommée."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM file_attente WHERE url = ?", (url,))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _obtenir_robots(self, url: str) -> Optional[robotparser.RobotFileParser]:
        parsed = urlparse(url)
        domaine = f"{parsed.scheme}://{parsed.netloc}"
        
        if domaine not in self.analyseurs_robots:
            rp = robotparser.RobotFileParser()
            rp.set_url(f"{domaine}/robots.txt")
            try:
                rp.read()
            except Exception:
                rp = None
            self.analyseurs_robots[domaine] = rp
            
        return self.analyseurs_robots[domaine]

    def est_autorise(self, url: str) -> bool:
        if not self.config.respecter_robots_txt:
            return True
        rp = self._obtenir_robots(url)
        return rp.can_fetch(self.config.user_agent, url) if rp else True

    def est_interne_ou_autorise(self, url: str) -> bool:
        if self.config.suivre_liens_externes:
            return True
        parsed_url = urlparse(url)
        domaine_lien = self._normaliser_domaine(parsed_url.netloc)
        domaines_base_normalises = {self._normaliser_domaine(d) for d in self.domaines_autorises}
        return domaine_lien in domaines_base_normalises

    def ajouter(self, requete: RequeteURL) -> bool:
        url_normalisee = self._normaliser_url(requete.url)
        
        if url_normalisee in self.urls_vues:
            return False
        if requete.profondeur > self.config.profondeur_max:
            return False
        if not self.est_interne_ou_autorise(requete.url):
            return False
        if not self.est_autorise(requete.url):
            return False
            
        self.urls_vues.add(url_normalisee)
        self.file_attente.append(requete)
        
        # Persistance immédiate dans SQLite
        self._sauvegarder_dans_file_sqlite(requete.url, requete.profondeur)
        return True

    def suivant(self) -> Optional[RequeteURL]:
        if not self.file_attente:
            return None
        requete = self.file_attente.popleft()
        
        # On la retire de la file persistante puisqu'elle va être traitée
        self._retirer_de_file_sqlite(requete.url)
        return requete

    def est_vide(self) -> bool:
        return len(self.file_attente) == 0