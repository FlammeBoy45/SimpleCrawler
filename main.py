import asyncio
from configuration import Configuration
from orchestrateur import Orchestrateur

def main():
    # 1. On instancie la configuration avec tes paramètres personnalisés
    config = Configuration(
        delai_aspiration_sec=0.5,
        profondeur_max=3,
        urls_initiales=["https://presidencedufaso.bf/"],
        respecter_robots_txt=False,
        suivre_liens_externes=False
    )
    
    # 2. On initialise l'orchestrateur
    orchestrateur = Orchestrateur(config)
    
    # 3. On lance la boucle asynchrone pour que le spider s'active !
    asyncio.run(orchestrateur.executer())

if __name__ == "__main__":
    main()