# main.py
from configuration import Configuration
from orchestrateur import Orchestrateur

if __name__ == "__main__":
    config = Configuration(
        delai_aspiration_sec=0.5,       # Un petit délai pour être poli avec le serveur de test
        profondeur_max=2,               # On descend de 2 niveaux pour attraper les catégories et les premiers livres
        urls_initiales=["https://books.toscrape.com/"],
        respecter_robots_txt=False
    )
    
    orchestrateur = Orchestrateur(config)
    orchestrateur.executer()