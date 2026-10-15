# sharingan_crawl/orchestrateur.py
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

class Orchestrateur:
    def __init__(self, config: Configuration):
        self.config = config
        self.planificateur = Planificateur(config)
        self.telechargeur = Telechargeur(config)
        self.analyseur = Analyseur()
        self.pipeline = PipelineSQLite()

        # Initialisation des URLs de départ
        for url in config.urls_initiales:
            self.planificateur.ajouter(RequeteURL(url=url, profondeur=0))

    async def executer(self) -> None:
        print("🌀 Démarrage du SharinganSpider (Mode Asynchrone)...")
        
        temps_debut = time.time()
        print(f"⏰ Heure de début : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        pages_crawlées = 0

        try:
            while not self.planificateur.est_vide():
                # Permet de détecter proprement une interruption clavier en async
                await asyncio.sleep(0)
                
                requete = self.planificateur.suivant()
                if not requete:
                    break

                print(f"📥 Aspiration : {requete.url} (Profondeur: {requete.profondeur})")
                
                # 1. Téléchargement asynchrone
                page_brute = await self.telechargeur.telecharger(requete.url)
                if page_brute.code_statut != 200 or page_brute.erreur:
                    print(f"⚠️ Erreur {page_brute.code_statut} sur {requete.url} : {page_brute.erreur}")
                    continue

                # 2. Analyse
                page_analysee = self.analyseur.analyser(page_brute)
                print(f"✨ Analysé : {page_analysee.titre or 'Sans titre'} ({len(page_analysee.liens_extraits)} liens trouvés)")

                # 3. Pipeline (Persistance)
                self.pipeline.sauvegarder(page_analysee)
                pages_crawlées += 1

                # 4. Propagation des nouveaux liens dans le planificateur
                if requete.profondeur < self.config.profondeur_max:
                    for lien in page_analysee.liens_extraits:
                        nouvelle_requete = RequeteURL(
                            url=lien,
                            profondeur=requete.profondeur + 1
                        )
                        self.planificateur.ajouter(nouvelle_requete)

            print("🔥 Crawl terminé avec succès !")

        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\n🛑 Interruption détectée (Ctrl+C). Arrêt en cours...")

        finally:
            self.pipeline.fermer()
            
            temps_fin = time.time()
            duree_totale_sec = temps_fin - temps_debut
            
            h = int(duree_totale_sec // 3600)
            m = int((duree_totale_sec % 3600) // 60)
            s = int(duree_totale_sec % 60)
            
            moyenne_sec = (duree_totale_sec / pages_crawlées) if pages_crawlées > 0 else 0

            print("\n📊 --- RAPPORT DE CRAWL ---")
            print(f"📄 Pages crawlées : {pages_crawlées}")
            print(f"⏱️ Durée totale    : {h}h {m}m {s}s")
            print(f"⚡ Moyenne par page : {moyenne_sec:.2f} secondes")
            print(f"⏰ Heure de fin     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("--------------------------")