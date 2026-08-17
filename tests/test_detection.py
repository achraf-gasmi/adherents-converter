from io import BytesIO

import openpyxl

from core.detection import VERSION_INCONNUE, VERSION_V0, VERSION_V1, detecter_classeur


def _classeur_bytes(entetes, lignes):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(entetes)
    for ligne in lignes:
        ws.append(ligne)
    tampon = BytesIO()
    wb.save(tampon)
    return tampon.getvalue()


def test_detection_v0():
    entetes = ["MATRICULE_SOCIETE", "COUPLE ASSURE", "Num de famille", "ADHERENT", "DATE_NAISS"]
    contenu = _classeur_bytes(entetes, [["1", None, "F1", "ADHERENT UN", "01/01/1980"]])
    resultats = detecter_classeur(contenu, "TEST.xlsx")
    assert resultats[0].version == VERSION_V0


def test_detection_v1():
    entetes = ["Client", "N° Famille", "Code d'identification", "Rang", "Lien", "Nom"]
    contenu = _classeur_bytes(entetes, [["CLIENT", "F1", 1, 0, "Adhérent", "ADHERENT UN"]])
    resultats = detecter_classeur(contenu, "TEST.xlsx")
    assert resultats[0].version == VERSION_V1


def test_detection_inconnue():
    entetes = ["Colonne A", "Colonne B"]
    contenu = _classeur_bytes(entetes, [["x", "y"]])
    resultats = detecter_classeur(contenu, "TEST.xlsx")
    assert resultats[0].version == VERSION_INCONNUE


def test_fichier_illisible_ne_plante_pas():
    resultats = detecter_classeur(b"ceci n'est pas un fichier xlsx", "CORROMPU.xlsx")
    assert len(resultats) == 1
    assert resultats[0].erreur is not None


def test_ligne_vide_au_milieu_ne_decale_pas_les_numeros_de_ligne_suivants():
    # Bug : une ligne entièrement vide au milieu des données (fréquent dans
    # les exports réels) était retirée avant d'être numérotée, décalant le
    # "Ligne source" de toutes les lignes suivantes -> traçabilité fausse
    # dans le rapport d'anomalies (on ne retrouve plus la bonne cellule en
    # ouvrant le fichier source et en tapant le numéro de ligne indiqué).
    from core.anomalies import CollecteurAnomalies
    from core.convert_v1 import convertir_v1
    from core.detection import lire_lignes_donnees

    entetes = ["Client", "N° Famille", "Code d'identification", "Rang", "Lien", "Nom",
               "Date de naissance", "Gendre", "Date d'affiliation", "RIB", "Identité gouvernementale"]
    ligne_vide = tuple([None] * len(entetes))
    lignes = [
        ["CLIENT", "F1", 1, 0, "Adhérent", "PERSONNE UN", "01/01/1980", "H", "01/01/2020", None, "05705239"],
        list(ligne_vide),  # ligne 3 dans le fichier Excel : entièrement vide
        # ligne 4 : CIN invalide, doit être signalée avec Ligne source = 4
        ["CLIENT", "F2", 1, 0, "Adhérent", "PERSONNE DEUX", "01/01/1980", "H", "01/01/2020", None, "pas-un-cin"],
    ]
    contenu = _classeur_bytes(entetes, lignes)

    lignes_source = lire_lignes_donnees(contenu, "Sheet")
    collecteur = CollecteurAnomalies()
    convertir_v1(lignes_source, entetes, "TEST.xlsx", "Sheet", collecteur)

    anomalie_cin = next(a for a in collecteur.anomalies if a.code == "CIN_INVALIDE")
    assert anomalie_cin.ligne_source == 4
