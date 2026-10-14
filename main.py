# main.py
from configuration import Configuration
from orchestrateur import Orchestrateur

if __name__ == "__main__":
    config = Configuration(
        delai_aspiration_sec=1.0,
        profondeur_max=2,
        urls_initiales=["https://example.com"],
        respecter_robots_txt=False  # Pour le test local
    )
    
    orchestrateur = Orchestrateur(config)
    orchestrateur.executer()