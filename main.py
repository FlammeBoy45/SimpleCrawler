
import argparse
import asyncio
import signal

from configuration import Configuration
from orchestrateur import Orchestrateur


def main():
    parser = argparse.ArgumentParser(
        description=(
            "ALEXIA-BF — Analyse en Ligne et EXploration pour l’Investigation "
            "et l’Archivage au Burkina Faso"
        )
    )
    parser.add_argument(
        "url",
        help="URL de départ du crawl",
    )
    args = parser.parse_args()

    config = Configuration(
        delai_aspiration_sec=0.5,
        profondeur_max=3,
        urls_initiales=[args.url],
        respecter_robots_txt=False,
        suivre_liens_externes=False,
    )

    orchestrateur = Orchestrateur(config)
    gestionnaire_precedent = signal.getsignal(signal.SIGINT)
    signal.signal(
        signal.SIGINT,
        lambda _signum, _frame: orchestrateur.demander_arret(),
    )
    try:
        asyncio.run(orchestrateur.executer())
    except KeyboardInterrupt:
        print("\n🛑 Interruption reçue. Arrêt en cours...")
    finally:
        signal.signal(signal.SIGINT, gestionnaire_precedent)


if __name__ == "__main__":
    main()
