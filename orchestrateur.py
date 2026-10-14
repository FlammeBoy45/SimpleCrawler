# sharingan_crawl/orchestrateur.py
import logging
from  configuration import Configuration
from  modeles import RequeteURL
from  planificateur.planificateur import Planificateur
from  telechargeur.telechargeur import Telechargeur
from  analyseur.analyseur import Analyseur
from  pipeline.pipeline import PipelineSQLite


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

    def executer(self) -> None:
        print("🌀 Démarrage du SharinganCrawl...")
        
        while not self.planificateur.est_vide():
            requete = self.planificateur.suivant()
            if not requete:
                break

            print(f"📥 Aspiration : {requete.url} (Profondeur: {requete.profondeur})")
            
            # 1. Téléchargement
            page_brute = self.telechargeur.telecharger(requete.url)
            if page_brute.code_statut != 200 or page_brute.erreur:
                print(f"⚠️ Erreur {page_brute.code_statut} sur {requete.url} : {page_brute.erreur}")
                continue

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

        self.pipeline.fermer()
        print("🔥 Crawl terminé avec succès ! Données sauvegardées dans SQLite.")