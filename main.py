import asyncio
from configuration import Configuration
from orchestrateur import Orchestrateur

if __name__ == "__main__":
    config = Configuration(
        delai_aspiration_sec=0.5,
        profondeur_max=3,
        urls_initiales=["https://presidencedufaso.bf/"],
        respecter_robots_txt=False,
        suivre_liens_externes=False
    )
    
    orchestrateur = Orchestrateur(config)
    asyncio.run(orchestrateur.executer())