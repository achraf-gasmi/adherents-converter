"""
core.anomalies
===============
Registre des codes d'anomalie (§7.4) et collecteur central. Toute règle de
conversion ou de normalisation qui corrige, vide ou signale une valeur passe
par ce module afin que la feuille "Anomalies" de chaque fichier exporté et
le rapport global RAPPORT_ANOMALIES.xlsx partagent exactement la même
structure et la même traçabilité (§7.1).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Sévérités
# --------------------------------------------------------------------------

SEVERITE_ERREUR = "Erreur"
SEVERITE_AVERTISSEMENT = "Avertissement"
SEVERITE_INFORMATION = "Information"

# --------------------------------------------------------------------------
# Types d'anomalie (§7.2)
# --------------------------------------------------------------------------

TYPE_VALEUR_MANQUANTE = "Valeur manquante"
TYPE_VALEUR_INCOHERENTE = "Valeur incohérente"

CODES_VALEUR_MANQUANTE = {
    "CIN_MANQUANT_ADHERENT",
    "GENDRE_MANQUANT",
    "LIEN_MANQUANT",
    "RANG_DATE_MANQUANTE",
    "RANG_MANQUANT",
    "FAMILLE_SANS_ADHERENT",
    "NOM_ILLISIBLE",
    "LIGNE_FANTOME",
}

# --------------------------------------------------------------------------
# Registre des codes -> sévérité (§7.4)
# --------------------------------------------------------------------------

REGISTRE_SEVERITE: dict[str, str] = {
    "IMAGE_BASE64_DETECTEE": SEVERITE_ERREUR,
    "DATE_FUTURE": SEVERITE_ERREUR,
    "AGE_ADHERENT_SUSPECT": SEVERITE_ERREUR,
    "FILIATION_IMPOSSIBLE": SEVERITE_ERREUR,
    "FAMILLE_SANS_ADHERENT": SEVERITE_ERREUR,
    "ADHERENT_MULTIPLE": SEVERITE_ERREUR,
    "NOM_ILLISIBLE": SEVERITE_ERREUR,
    "COLLISION_NUM_FAMILLE": SEVERITE_ERREUR,
    "CIN_INVALIDE": SEVERITE_AVERTISSEMENT,
    "CIN_FACTICE": SEVERITE_AVERTISSEMENT,
    "RIB_INVALIDE": SEVERITE_AVERTISSEMENT,
    "DATE_INVALIDE": SEVERITE_AVERTISSEMENT,
    "DATE_ABERRANTE": SEVERITE_AVERTISSEMENT,
    "RANG_DATE_MANQUANTE": SEVERITE_AVERTISSEMENT,
    "RANG_MANQUANT": SEVERITE_AVERTISSEMENT,
    "RANG_INCOHERENT": SEVERITE_AVERTISSEMENT,
    "RANG_DUPLIQUE": SEVERITE_AVERTISSEMENT,
    "RANG_ENFANTS_DESORDONNES": SEVERITE_AVERTISSEMENT,
    "CONJOINT_MULTIPLE": SEVERITE_AVERTISSEMENT,
    "LIEN_MANQUANT": SEVERITE_AVERTISSEMENT,
    "DOUBLON_INTRA_FAMILLE": SEVERITE_AVERTISSEMENT,
    "DOUBLON_INTER_SOURCE": SEVERITE_AVERTISSEMENT,
    "NOM_ORDRE_SUSPECT": SEVERITE_AVERTISSEMENT,
    "CIN_MANQUANT_ADHERENT": SEVERITE_INFORMATION,
    "CIN_COMPLETE": SEVERITE_INFORMATION,
    "GENDRE_MANQUANT": SEVERITE_INFORMATION,
    "GENDRE_DEVINE": SEVERITE_INFORMATION,
    "NOM_NETTOYE": SEVERITE_INFORMATION,
    "LIGNE_FANTOME": SEVERITE_INFORMATION,
    "JUMEAUX_DEPARTAGES": SEVERITE_INFORMATION,
    "CHAMP_NON_REPRIS": SEVERITE_INFORMATION,
}

# En-têtes de la feuille "Anomalies", dans l'ordre exact du §7.1.
COLONNES_ANOMALIES = [
    "Fichier source",
    "Onglet source",
    "Ligne source",
    "Colonne source",
    "Type d'anomalie",
    "Code",
    "Sévérité",
    "N° Famille",
    "Nom",
    "Champ cible",
    "Valeur d'origine",
    "Valeur retenue",
    "Message",
]

# Caractères invisibles à faire apparaître explicitement dans "Valeur d'origine".
_CARACTERES_INVISIBLES = {
    chr(0x00A0): "·",  # espace insécable (NBSP)
    chr(0x202F): "·",  # espace fine insécable (NNBSP)
    chr(0x2007): "·",  # espace tabulaire
}


def formater_valeur_origine(valeur: object) -> str:
    """Rend visible une valeur brute, y compris ses caractères invisibles ou
    ses valeurs ambiguës (None, booléens), pour la colonne "Valeur d'origine"
    du rapport d'anomalies (§7.1, exigence de traçabilité).
    """
    if valeur is None:
        return "[vide]"
    if isinstance(valeur, bool):
        return "[True]" if valeur else "[False]"
    texte = str(valeur)
    if texte.strip() == "":
        return "[vide]"
    for invisible, remplacement in _CARACTERES_INVISIBLES.items():
        texte = texte.replace(invisible, remplacement)
    return texte


@dataclass
class Anomalie:
    """Une ligne de la feuille Anomalies."""

    fichier_source: str
    onglet_source: str
    ligne_source: int | str
    colonne_source: str
    code: str
    num_famille: str
    nom: str
    champ_cible: str
    valeur_origine: object
    valeur_retenue: object
    message: str

    @property
    def severite(self) -> str:
        return REGISTRE_SEVERITE.get(self.code, SEVERITE_INFORMATION)

    @property
    def type_anomalie(self) -> str:
        return TYPE_VALEUR_MANQUANTE if self.code in CODES_VALEUR_MANQUANTE else TYPE_VALEUR_INCOHERENTE

    def vers_ligne(self) -> list:
        return [
            self.fichier_source,
            self.onglet_source,
            self.ligne_source,
            self.colonne_source,
            self.type_anomalie,
            self.code,
            self.severite,
            self.num_famille,
            self.nom,
            self.champ_cible,
            formater_valeur_origine(self.valeur_origine),
            "" if self.valeur_retenue is None else self.valeur_retenue,
            self.message,
        ]


@dataclass
class CollecteurAnomalies:
    """Accumule les anomalies rencontrées pendant la conversion d'une ou
    plusieurs sources. Un seul collecteur est utilisé pour tout le lot importé
    afin de pouvoir produire à la fois les feuilles par fichier et le rapport
    global, simplement en filtrant sur `fichier_source`.
    """

    anomalies: list[Anomalie] = field(default_factory=list)

    def ajouter(
        self,
        *,
        fichier_source: str,
        onglet_source: str,
        ligne_source: int | str,
        colonne_source: str = "",
        code: str,
        num_famille: str = "",
        nom: str = "",
        champ_cible: str = "",
        valeur_origine: object = None,
        valeur_retenue: object = None,
        message: str = "",
    ) -> None:
        if code not in REGISTRE_SEVERITE:
            raise ValueError(f"Code d'anomalie inconnu : {code}")
        self.anomalies.append(
            Anomalie(
                fichier_source=fichier_source,
                onglet_source=onglet_source,
                ligne_source=ligne_source,
                colonne_source=colonne_source,
                code=code,
                num_famille=str(num_famille) if num_famille is not None else "",
                nom=nom or "",
                champ_cible=champ_cible,
                valeur_origine=valeur_origine,
                valeur_retenue=valeur_retenue,
                message=message,
            )
        )

    def pour_fichier(self, fichier_source: str) -> list[Anomalie]:
        return [a for a in self.anomalies if a.fichier_source == fichier_source]

    def par_severite(self) -> dict[str, int]:
        compte = {SEVERITE_ERREUR: 0, SEVERITE_AVERTISSEMENT: 0, SEVERITE_INFORMATION: 0}
        for a in self.anomalies:
            compte[a.severite] += 1
        return compte
