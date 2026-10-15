# main.py
from configuration import Configuration
from orchestrateur import Orchestrateur

if __name__ == "__main__":
    config = Configuration(
        delai_aspiration_sec=0.5,
        profondeur_max=3,  # On s'assure d'avoir de la profondeur
        urls_initiales=["https://presidencedufaso.bf/"],
        respecter_robots_txt=False,
        suivre_liens_externes=False  # Reste strictement sur le même site
    )
    
    orchestrateur = Orchestrateur(config)
    orchestrateur.executer()