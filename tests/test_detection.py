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
