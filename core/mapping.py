"""
core.mapping
============
Constantes partagées par tous les autres modules : libellés des colonnes du
format cible, alias des colonnes sources V0/V1, et fonctions utilitaires de
normalisation d'en-tête. Aucune logique métier ici : uniquement des données
et des petites fonctions pures, pour que detection.py, convert_v0.py et
convert_v1.py partagent une seule source de vérité sur les noms de colonnes.
"""
from __future__ import annotations

import unicodedata

# --------------------------------------------------------------------------
# Format cible (§1 du cahier des charges)
# --------------------------------------------------------------------------

COL_CLIENT = "Client"
COL_NUM_FAMILLE_B = "N° Famille"
COL_LIEN = "Lien"
COL_GENDRE = "Gendre"
COL_NOM = "Nom"
COL_DATE_NAISSANCE = "Date de naissance"
COL_DATE_AFFILIATION = "Date d'affiliation"
COL_NUM_FAMILLE_H = "N° Famille"
COL_RANG = "Rang"
COL_RIB = "RIB"
COL_CIN = "Identité gouvernementale"

# Ordre exact des 11 colonnes du format cible (B et H portent le même
# libellé "N° Famille" mais sont bien deux colonnes distinctes dans le
# fichier Excel : on les indexe par position, pas par nom, à l'export).
TARGET_COLUMNS = [
    "Client",
    "N° Famille",
    "Lien",
    "Gendre",
    "Nom",
    "Date de naissance",
    "Date d'affiliation",
    "N° Famille",
    "Rang",
    "RIB",
    "Identité gouvernementale",
]

# Noms de champs internes (utilisés comme clés de dict / colonnes pandas
# pendant tout le pipeline, avant l'écriture finale où B et H sont dupliqués
# depuis "num_famille").
F_CLIENT = "client"
F_NUM_FAMILLE = "num_famille"
F_LIEN = "lien"
F_GENDRE = "gendre"
F_NOM = "nom"
F_DATE_NAISSANCE = "date_naissance"
F_DATE_AFFILIATION = "date_affiliation"
F_RANG = "rang"
F_RIB = "rib"
F_CIN = "cin"

# Colonnes techniques de traçabilité, présentes tout au long du pipeline
# mais jamais écrites dans la feuille "Données" du fichier cible.
F_FICHIER_SOURCE = "_fichier_source"
F_ONGLET_SOURCE = "_onglet_source"
F_LIGNE_SOURCE = "_ligne_source"
F_COLONNE_SOURCE = "_colonne_source"
F_INDEX_SOURCE = "_index_source"
F_RANG_SOURCE = "_rang_source"  # Rang tel que fourni par la source V1 (jamais réutilisé, seulement comparé)

INTERNAL_FIELDS = [
    F_CLIENT, F_NUM_FAMILLE, F_LIEN, F_GENDRE, F_NOM, F_DATE_NAISSANCE,
    F_DATE_AFFILIATION, F_RANG, F_RIB, F_CIN,
    F_FICHIER_SOURCE, F_ONGLET_SOURCE, F_LIGNE_SOURCE, F_COLONNE_SOURCE,
    F_INDEX_SOURCE, F_RANG_SOURCE,
]

# --------------------------------------------------------------------------
# Liens reconnus
# --------------------------------------------------------------------------

LIEN_ADHERENT = "Adhérent"
LIEN_CONJOINT = "Conjoint"
LIEN_ENFANT = "Enfant"

# --------------------------------------------------------------------------
# Signatures de détection (cellule A1)
# --------------------------------------------------------------------------

SIGNATURE_V0 = "MATRICULE_SOCIETE"
SIGNATURE_V1 = "Client"

# --------------------------------------------------------------------------
# Format V0 — colonnes sources (§2)
# --------------------------------------------------------------------------

V0_COL_MATRICULE = "MATRICULE_SOCIETE"
V0_COL_COUPLE_ASSURE = "COUPLE ASSURE"
V0_COL_NUM_FAMILLE = "Num de famille"
V0_COL_ADHERENT = "ADHERENT"
V0_COL_DATE_NAISS = "DATE_NAISS"
V0_COL_CIN = "CIN"
V0_COL_DATE_EXPIRATION = "DATE_EXPIRATION"
V0_COL_CLIENT = "Client"
V0_COL_CONJOINT = "CONJOINT"
V0_COL_DATE_NAISS_CONJ = "DATE_NAISS_CONJ"
V0_NB_ENFANTS_MAX = 5
V0_COL_IMAGE = "IMAGE"


def v0_col_enfant(n: int) -> str:
    return f"ENFANT-{n}"


def v0_col_date_naiss_enfant(n: int) -> str:
    return f"DATE_NAISS_ENF-{n}"


# Colonnes V0 qui ne sont jamais reprises dans la cible.
V0_COLONNES_NON_REPRISES = {
    V0_COL_MATRICULE, V0_COL_COUPLE_ASSURE, V0_COL_DATE_EXPIRATION, V0_COL_IMAGE,
}

# --------------------------------------------------------------------------
# Format V1 — colonnes sources (§3)
# --------------------------------------------------------------------------

V1_COL_CLIENT = "Client"
V1_COL_NUM_FAMILLE = "N° Famille"
V1_COL_CODE_IDENTIFICATION = "Code d'identification"
V1_COL_RANG = "Rang"
V1_COL_LIEN = "Lien"
V1_COL_NOM = "Nom"
V1_COL_DATE_NAISSANCE = "Date de naissance"
V1_COL_GENDRE = "Gendre"
V1_COL_DATE_AFFILIATION = "Date d'affiliation"
V1_COL_RIB = "RIB"
V1_COL_CIN = "Identité gouvernementale"

# Colonnes surnuméraires (variables selon les fichiers), non reprises.
V1_COL_ETAT_CIVIL = "État civil"
V1_COL_COLLEGE = "Collége"  # orthographe telle que constatée dans les sources
V1_COL_COUPLE_ASSURE = "Couple assuré"
V1_COL_DATE_RADIATION = "Date de radiation"

V1_NOYAU = [
    V1_COL_CLIENT, V1_COL_NUM_FAMILLE, V1_COL_CODE_IDENTIFICATION, V1_COL_RANG,
    V1_COL_LIEN, V1_COL_NOM, V1_COL_DATE_NAISSANCE, V1_COL_GENDRE,
    V1_COL_DATE_AFFILIATION, V1_COL_RIB, V1_COL_CIN,
]

V1_COLONNES_NON_REPRISES = {
    V1_COL_CODE_IDENTIFICATION, V1_COL_ETAT_CIVIL, V1_COL_COLLEGE,
    V1_COL_COUPLE_ASSURE, V1_COL_DATE_RADIATION,
}


def construire_index_entetes(en_tetes: list[object]) -> dict[str, int]:
    """Associe chaque intitulé de colonne à son index de position. En cas
    d'en-têtes dupliqués (ex. "Date de radiation" x2 chez benetton/esol) ou
    vides (colonne finale sans nom chez HUTCHINSON/SEWS), seule la première
    occurrence est retenue et les colonnes sans nom sont ignorées — le
    lecteur ne doit jamais planter sur ces cas.
    """
    index: dict[str, int] = {}
    for i, brut in enumerate(en_tetes):
        nom = normaliser_entete(brut)
        if nom and nom not in index:
            index[nom] = i
    return index


LIENS_CONNUS = {
    "adherent": LIEN_ADHERENT,
    "conjoint": LIEN_CONJOINT,
    "enfant": LIEN_ENFANT,
}


def normaliser_lien(valeur: object) -> str | None:
    """Normalise une valeur de Lien vers Adhérent/Conjoint/Enfant, de façon
    insensible à la casse et aux accents. Renvoie None si vide ou non reconnu
    (-> LIEN_MANQUANT côté appelant)."""
    if valeur is None:
        return None
    texte = str(valeur).strip()
    if texte == "":
        return None
    return LIENS_CONNUS.get(_cle_recherche(texte))


def normaliser_entete(valeur: object) -> str:
    """Normalise un intitulé de colonne pour une comparaison robuste :
    supprime les espaces superflus. Ne touche pas aux accents (les fichiers
    sources sont en UTF-8 propre) mais tolère None et les types non str.
    """
    if valeur is None:
        return ""
    texte = str(valeur).strip()
    texte = " ".join(texte.split())
    return texte


def _cle_recherche(valeur: str) -> str:
    """Clé insensible à la casse et aux accents, pour un repêchage tolérant
    si une variante orthographique inattendue apparaît dans un nouveau fichier.
    """
    txt = unicodedata.normalize("NFKD", valeur.lower())
    return "".join(c for c in txt if not unicodedata.combining(c))
