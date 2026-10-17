# modeles.py
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional


@dataclass
class RequeteURL:
    url: str
    priorite: int = 0
    profondeur: int = 0
    metadonnees: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PageBrute:
    url: str
    code_statut: int
    contenu_html: str
    en_tete: Dict[str, str] = field(default_factory=dict)
    temps_reponse_ms: float = 0.0
    erreur: Optional[str] = None


@dataclass
class PageAnalysee:
    url: str
    titre: Optional[str] = None
    donnees: Dict[str, Any] = field(default_factory=dict)
    liens_extraits: List[str] = field(default_factory=list)
    date_extraction: datetime = field(default_factory=lambda: datetime.now(timezone.utc))