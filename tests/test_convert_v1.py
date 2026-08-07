from datetime import datetime

from core.anomalies import TYPE_VALEUR_MANQUANTE, CollecteurAnomalies
from core.convert_v1 import convertir_v1
from core.ranking import calculer_rangs

EN_TETES_NOYAU = [
    "Client", "N° Famille", "Code d'identification", "Rang", "Lien", "Nom",
    "Date de naissance", "Gendre", "Date d'affiliation", "RIB", "Identité gouvernementale",
]

EN_TETES_AVEC_DOUBLON = EN_TETES_NOYAU + ["État civil", "Collége", "Couple assuré", "Date de radiation", "Date de radiation"]


def _ligne(num_famille, rang, lien, nom, naissance, gendre="H", cin="12345678", rib=""):
    return (
        "CLIENT", num_famille, 400000, rang, lien, nom, naissance, gendre,
        datetime(2020, 1, 1), rib, cin,
    )


def test_tracabilite_v1_ligne_source():
    lignes = [
        _ligne("F1", 0, "Adhérent", "PERSONNE UN", datetime(1980, 1, 1)),
        _ligne("F2", 0, "Adhérent", "PERSONNE DEUX", datetime(1980, 1, 1)),
        _ligne("F3", 0, "Adhérent", "PERSONNE TROIS", datetime(1980, 1, 1), cin="pas-un-cin-1"),
    ]
    collecteur = CollecteurAnomalies()
    convertir_v1(lignes, EN_TETES_NOYAU, "TEST.xlsx", "Sheet1", collecteur)
    anomalies_cin = [a for a in collecteur.anomalies if a.code == "CIN_INVALIDE"]
    assert len(anomalies_cin) == 1
    assert anomalies_cin[0].ligne_source == 4


def test_entete_duplique_ne_plante_pas():
    ligne = _ligne("F1", 0, "Adhérent", "PERSONNE UN", datetime(1980, 1, 1)) + ("Marié", "[1] ACTIF", None, datetime(2025, 1, 1), None)
    collecteur = CollecteurAnomalies()
    resultats = convertir_v1([ligne], EN_TETES_AVEC_DOUBLON, "benetton.xlsx", "Sheet1", collecteur)
    assert len(resultats) == 1


def test_cin_vide_enfant_aucune_anomalie_cin_vide_adherent_signale():
    lignes = [
        _ligne("F1", 0, "Adhérent", "ADH", datetime(1980, 1, 1), cin=""),
        _ligne("F1", 2, "Enfant", "ENF", datetime(2010, 1, 1), cin=""),
    ]
    collecteur = CollecteurAnomalies()
    convertir_v1(lignes, EN_TETES_NOYAU, "TEST.xlsx", "Sheet1", collecteur)

    codes_enfant = [a.code for a in collecteur.anomalies if a.nom == "ENF"]
    codes_adherent = [a.code for a in collecteur.anomalies if a.nom == "ADH"]
    assert "CIN_MANQUANT_ADHERENT" not in codes_enfant
    assert "CIN_MANQUANT_ADHERENT" in codes_adherent
    anomalie_adherent = next(a for a in collecteur.anomalies if a.code == "CIN_MANQUANT_ADHERENT")
    assert anomalie_adherent.type_anomalie == TYPE_VALEUR_MANQUANTE


def test_ligne_fantome_supprimee_par_defaut():
    lignes = [
        _ligne("F1", 0, "Adhérent", "ADH", datetime(1980, 1, 1)),
        ("CLIENT", "F1", None, None, None, None, None, None, None, None, None),
    ]
    collecteur = CollecteurAnomalies()
    resultats = convertir_v1(lignes, EN_TETES_NOYAU, "TEST.xlsx", "Sheet1", collecteur, supprimer_lignes_fantomes=True)
    assert len(resultats) == 1
    assert any(a.code == "LIGNE_FANTOME" for a in collecteur.anomalies)


def test_ligne_fantome_conservee_si_option_desactivee():
    lignes = [
        _ligne("F1", 0, "Adhérent", "ADH", datetime(1980, 1, 1)),
        ("CLIENT", "F1", None, None, None, None, None, None, None, None, None),
    ]
    collecteur = CollecteurAnomalies()
    resultats = convertir_v1(lignes, EN_TETES_NOYAU, "TEST.xlsx", "Sheet1", collecteur, supprimer_lignes_fantomes=False)
    assert len(resultats) == 2


def test_rang_source_incoherent_signale_apres_recalcul():
    lignes = [
        _ligne("F1", 5, "Adhérent", "ADH", datetime(1980, 1, 1)),
    ]
    collecteur = CollecteurAnomalies()
    resultats = convertir_v1(lignes, EN_TETES_NOYAU, "TEST.xlsx", "Sheet1", collecteur)
    calculer_rangs(resultats, collecteur)
    assert any(a.code == "RANG_RECALCULE" for a in collecteur.anomalies)
    assert resultats[0]["rang"] == 0
