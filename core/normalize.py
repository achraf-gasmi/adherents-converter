"""
core.normalize
================
Règles de normalisation des valeurs individuelles (§5) : nettoyage des noms,
validation/complétion des CIN et RIB, parsing tolérant des dates, et
normalisation du genre. Ce module ne connaît ni les fichiers ni les
familles : il expose des fonctions pures, valeur en entrée -> valeur nettoyée
+ éventuel code d'anomalie en sortie. C'est aux modules appelants
(convert_v0, convert_v1, ranking) d'enrichir ces résultats avec le contexte
(fichier, ligne, colonne, personne) avant de les journaliser dans le
CollecteurAnomalies.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

# --------------------------------------------------------------------------
# Noms
# --------------------------------------------------------------------------

# Liste volontairement réduite de prénoms fréquents, utilisée en heuristique
# de dernier recours pour repérer un nom probablement inversé (Prénom Nom au
# lieu de NOM Prénom). Cette détection reste indicative : elle alimente
# NOM_ORDRE_SUSPECT pour validation humaine, jamais une correction automatique.
_PRENOMS_FREQUENTS = {
    "MOHAMED", "AHMED", "FATMA", "SONIA", "KARIM", "NIZAR", "SAMI", "RIM",
    "YASMINE", "IMEN", "SANA", "NADIA", "HELA", "EMNA", "RANIA", "WIEM",
    "MERYEM", "AYA", "CHAIMA", "SIRINE", "MARWA", "INES", "DHOUHA", "DORRA",
    "LEILA", "SALMA", "AMEL", "MOUNA", "HOUDA", "NAJET", "RADHIA", "NABIL",
    "SAMIR", "RIADH", "HICHEM", "WALID", "KHALED", "TAREK", "ZIED", "GHAZI",
    "MONCEF", "ADEL", "YOUSSEF", "BILEL", "OUSSAMA", "RAYEN", "MALEK", "FIRAS",
}


def nettoyer_nom(valeur: object, uppercase: bool) -> tuple[str, bool]:
    """Nettoie un nom source : espaces, astérisques, point final, suffixe
    numérique. Renvoie (nom_nettoye, modifie) où `modifie` indique si la
    valeur a changé par rapport à l'original (pour journaliser NOM_NETTOYE).
    """
    original = "" if valeur is None else str(valeur)
    texte = original.strip()
    texte = re.sub(r"\s+", " ", texte)
    texte = texte.replace("*", "")
    texte = re.sub(r"\.+$", "", texte)
    texte = re.sub(r"\d+$", "", texte)
    texte = re.sub(r"\s+", " ", texte).strip()
    if uppercase:
        texte = texte.upper()
    return texte, texte != original


def nom_ordre_suspect(nom_nettoye: str) -> bool:
    """Heuristique : deux mots dont seul le premier est un prénom fréquent
    connu -> ordre "Prénom Nom" probable au lieu de "NOM Prénom".
    """
    mots = nom_nettoye.split()
    if len(mots) != 2:
        return False
    premier, second = mots
    return premier in _PRENOMS_FREQUENTS and second not in _PRENOMS_FREQUENTS


# --------------------------------------------------------------------------
# CIN / Identité gouvernementale (§5.3)
# --------------------------------------------------------------------------

_ESPACES_A_RETIRER = [chr(0x00A0), chr(0x202F), chr(0x2007), " "]
_BOOLEENS_TEXTE = {"false", "true"}
_MOTIF_FACTICE = re.compile(r"^0{3,}\d{1,5}$")


@dataclass
class ResultatCin:
    valeur: str  # "" si le champ a été vidé
    code: str | None  # None si aucune anomalie
    message: str = ""


def nettoyer_cin(valeur: object, *, completer_cin: bool = True, vider_cin_factices: bool = True) -> ResultatCin:
    """Applique l'algorithme de nettoyage du CIN décrit au §5.3, dans
    l'ordre : suppression des espaces (y compris insécables), suppression
    des astérisques, rejet des booléens, rejet des motifs factices, puis
    validation par longueur (8 conservé, 7 complété, sinon vidé).
    """
    if isinstance(valeur, bool):
        return ResultatCin("", "CIN_INVALIDE", "CIN égal à un booléen Excel non résolu (formule non calculée).")

    if valeur is None:
        return ResultatCin("", None, "")

    brut = str(valeur).strip()
    if brut == "":
        return ResultatCin("", None, "")

    texte = brut
    for espace in _ESPACES_A_RETIRER:
        texte = texte.replace(espace, "")
    texte = texte.strip("*")

    if texte == "":
        return ResultatCin("", "CIN_INVALIDE", "CIN illisible après nettoyage (ne contenait que des astérisques) ; champ vidé.")

    if texte.lower() in _BOOLEENS_TEXTE:
        return ResultatCin("", "CIN_INVALIDE", "CIN égal à un booléen Excel non résolu (formule non calculée).")

    if not texte.isdigit():
        return ResultatCin("", "CIN_INVALIDE", "CIN non numérique après nettoyage.")

    if len(texte) != 8 and vider_cin_factices and _MOTIF_FACTICE.match(texte):
        return ResultatCin("", "CIN_FACTICE", "CIN factice (zéros de tête suivis d'un nombre court) ; champ vidé.")

    if len(texte) == 8:
        return ResultatCin(texte, None, "")

    if len(texte) == 7:
        if completer_cin:
            return ResultatCin("0" + texte, "CIN_COMPLETE", "CIN à 7 chiffres complété par un zéro à gauche (Excel a supprimé le zéro initial).")
        return ResultatCin("", "CIN_INVALIDE", "CIN à 7 chiffres non complété (option de complétion désactivée) ; champ vidé.")

    return ResultatCin("", "CIN_INVALIDE", f"CIN de longueur {len(texte)} (attendu : 8 chiffres) ; champ vidé.")


# --------------------------------------------------------------------------
# RIB (§5.4)
# --------------------------------------------------------------------------

_MOTIF_RIB = re.compile(r"^\d{20}$")


@dataclass
class ResultatRib:
    valeur: str
    code: str | None
    message: str = ""


def nettoyer_rib(valeur: object) -> ResultatRib:
    if valeur is None:
        return ResultatRib("", None, "")
    texte = str(valeur).strip()
    for espace in _ESPACES_A_RETIRER:
        texte = texte.replace(espace, "")
    if texte == "":
        return ResultatRib("", None, "")
    if _MOTIF_RIB.match(texte):
        return ResultatRib(texte, None, "")
    return ResultatRib("", "RIB_INVALIDE", "RIB non conforme (20 chiffres attendus) ; champ vidé.")


# --------------------------------------------------------------------------
# Dates (§5.5)
# --------------------------------------------------------------------------

_EPOCH_EXCEL = date(1899, 12, 30)


def parser_date(valeur: object) -> tuple[date | None, bool]:
    """Parse une date tolérante : datetime natif, dd/mm/yyyy, yyyy-mm-dd,
    puis sérial Excel. Renvoie (date_obj, etait_invalide). `etait_invalide`
    est True uniquement si une valeur non vide n'a pas pu être interprétée
    (-> DATE_INVALIDE côté appelant) ; une valeur vide n'est pas une anomalie
    de ce module (elle peut l'être ailleurs, ex. RANG_DATE_MANQUANTE).
    """
    if valeur is None:
        return None, False
    if isinstance(valeur, datetime):
        return valeur.date(), False
    if isinstance(valeur, date):
        return valeur, False
    if isinstance(valeur, (int, float)):
        try:
            return _EPOCH_EXCEL + timedelta(days=float(valeur)), False
        except (OverflowError, ValueError):
            return None, True

    texte = str(valeur).strip()
    if texte == "":
        return None, False

    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texte, fmt).date(), False
        except ValueError:
            continue

    if texte.isdigit():
        try:
            return _EPOCH_EXCEL + timedelta(days=float(texte)), False
        except (OverflowError, ValueError):
            pass

    return None, True


# --------------------------------------------------------------------------
# Genre (§5.6)
# --------------------------------------------------------------------------

def normaliser_gendre(valeur: object) -> str:
    """Normalise le genre en H/F. Toute valeur non reconnue (y compris vide)
    devient une chaîne vide ; c'est à l'appelant de journaliser
    GENDRE_MANQUANT si la ligne le justifie."""
    if valeur is None:
        return ""
    texte = str(valeur).strip().upper()
    if texte in ("H", "M"):
        return "H"
    if texte == "F":
        return "F"
    return ""


# --------------------------------------------------------------------------
# Lignes fantômes (§5.1)
# --------------------------------------------------------------------------

def est_ligne_fantome(lien: object, nom: object, date_naissance: object, rang_source: object = None) -> bool:
    """Une ligne est fantôme si Rang, Lien, Nom et Date de naissance sont
    tous vides — seuls Client et N° Famille sont renseignés."""
    def _vide(v: object) -> bool:
        return v is None or str(v).strip() == ""

    return _vide(lien) and _vide(nom) and _vide(date_naissance) and _vide(rang_source)
