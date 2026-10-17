# orchestrateur.py
import logging
from configuration import Configuration
from modeles import RequeteURL
from planificateur.planificateur import Planificateur
from telechargeur.telechargeur import Telechargeur
from analyseur.analyseur import Analyseur
from pipeline.pipeline import PipelineSQLite
from datetime import datetime
import time
import asyncio
import threading

class Orchestrateur:
    def __init__(self, config: Configuration):
        self.config = config
        db_path = "resultats_crawl.db"
        
        self.planificateur = Planificateur(config, db_path=db_path)
        self.telechargeur = Telechargeur(config)
        self.analyseur = Analyseur()
        self.pipeline = PipelineSQLite()
        self._arret_demande = threading.Event()

        # Initialisation si la file est vide au départ
        if self.planificateur.est_vide():
            for url in config.urls_initiales:
                self.planificateur.ajouter(RequeteURL(url=url, profondeur=0))

    async def _traiter_requete(self, requete: RequeteURL, semaphore: asyncio.Semaphore) -> int:
        """Traite une seule requête HTTP, analyse et sauvegarde avec contrôle de concurrence."""
        async with semaphore:
            print(f"📥 Aspiration : {requete.url} (Profondeur: {requete.profondeur})")
            
            # 1. Téléchargement asynchrone
            page_brute = await self.telechargeur.telecharger(requete.url)
            if page_brute.code_statut != 200 or page_brute.erreur:
                print(f"⚠️ Erreur {page_brute.code_statut} sur {requete.url} : {page_brute.erreur}")
                return 0

            # 2. Analyse
            page_analysee = self.analyseur.analyser(page_brute)
            print(f"✨ Analysé : {page_analysee.titre or 'Sans titre'} ({len(page_analysee.liens_extraits)} liens trouvés)")

            # 3. Pipeline (Persistance)
            self.pipeline.sauvegarder(page_analysee)

            # 4. Propagation des nouveaux liens dans le planificateur
            if requete.profondeur < self.config.profondeur_max:
                for lien in page_analysee.liens_extraits:
                    nouvelle_requete = RequeteURL(
                        url=lien,
                        profondeur=requete.profondeur + 1
                    )
                    self.planificateur.ajouter(nouvelle_requete)
                    if self._arret_demande.is_set():
                        break
                    
            return 1

    def demander_arret(self) -> None:
        self._arret_demande.set()

    async def executer(self) -> None:
        print(f"🌀 Démarrage d’ALEXIA-BF (mode asynchrone - concurrence max : {self.config.concurrence_max})...")
        
        temps_debut = time.time()
        print(f"⏰ Heure de début : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        pages_crawlées = 0
        semaphore = asyncio.Semaphore(self.config.concurrence_max)

        try:
            while (
                not self.planificateur.est_vide()
                and not self._arret_demande.is_set()
            ):
                await asyncio.sleep(0)
                
                # On collecte un batch de requêtes disponibles dans la file
                taches = []
                while (
                    not self.planificateur.est_vide()
                    and len(taches) < self.config.concurrence_max
                    and not self._arret_demande.is_set()
                ):
                    requete = self.planificateur.suivant()
                    if requete:
                        taches.append(self._traiter_requete(requete, semaphore))

                if not taches:
                    break

                # Exécution simultanée du batch
                resultats = await asyncio.gather(*taches, return_exceptions=True)
                
                for res in resultats:
                    if isinstance(res, int):
                        pages_crawlées += res
                    elif isinstance(res, Exception):
                        print(f"⚠️ Erreur dans une tâche concurrente : {res}")

            if self._arret_demande.is_set():
                print("\n🛑 Arrêt demandé (Ctrl+C). Crawl interrompu proprement.")
            else:
                print("🔥 Crawl terminé avec succès !")

        finally:
            try:
                self.pipeline.fermer()
            finally:
                temps_fin = time.time()
                duree_totale_sec = temps_fin - temps_debut

                h = int(duree_totale_sec // 3600)
                m = int((duree_totale_sec % 3600) // 60)
                s = int(duree_totale_sec % 60)

                moyenne_sec = (
                    duree_totale_sec / pages_crawlées if pages_crawlées > 0 else 0
                )

                print("\n📊 --- RAPPORT DE CRAWL ---")
                print(f"📄 Pages crawlées : {pages_crawlées}")
                print(f"⏱️ Durée totale    : {h}h {m}m {s}s")
                print(f"⚡ Moyenne par page : {moyenne_sec:.2f} secondes")
                print(f"⏰ Heure de fin     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print("--------------------------")