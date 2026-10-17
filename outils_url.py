from typing import Optional
from urllib.parse import urlparse, urlunparse

PORTS_PAR_DEFAUT = {"http": 80, "https": 443}


def normaliser_url(url: str) -> Optional[str]:
    """Retourne une forme canonique de l'URL (sans fragment, schéma/hôte en
    minuscules, port par défaut retiré, identifiants retirés, chemin vide -> "/"),
    ou None si l'URL est invalide ou n'est pas en http(s)."""
    try:
        p = urlparse(url.strip())
        schema = p.scheme.lower()
        hote = p.hostname
        port = p.port  # peut lever ValueError si le port est invalide
    except ValueError:
        return None

    if schema not in PORTS_PAR_DEFAUT or not hote:
        return None

    hote = hote.lower()
    if ":" in hote:  # IPv6
        hote = f"[{hote}]"
    netloc = hote
    if port and port != PORTS_PAR_DEFAUT[schema]:
        netloc += f":{port}"

    return urlunparse((schema, netloc, p.path or "/", p.params, p.query, ""))


def _sans_www(netloc: str) -> str:
    return netloc[4:] if netloc.startswith("www.") else netloc


def domaine_de(url: str) -> Optional[str]:
    """Domaine normalisé d'une URL (minuscules, sans 'www.'), ou None."""
    norm = normaliser_url(url)
    if norm is None:
        return None
    return _sans_www(urlparse(norm).netloc)


def cle_deduplication(url: str) -> Optional[str]:
    """Clé servant à reconnaître deux URL équivalentes : URL normalisée, sans
    'www.'. Retourne None si l'URL est invalide."""
    norm = normaliser_url(url)
    if norm is None:
        return None
    p = urlparse(norm)
    return urlunparse(p._replace(netloc=_sans_www(p.netloc)))
