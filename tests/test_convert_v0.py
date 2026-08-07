from core.anomalies import CollecteurAnomalies
from core.convert_v0 import convertir_v0

EN_TETES_V0 = [
    "MATRICULE_SOCIETE", "COUPLE ASSURE", "Num de famille", "ADHERENT", "DATE_NAISS",
    "CIN", "DATE_EXPIRATION", "Client", "CONJOINT", "DATE_NAISS_CONJ",
    "ENFANT-1", "DATE_NAISS_ENF-1", "ENFANT-2", "DATE_NAISS_ENF-2",
    "ENFANT-3", "DATE_NAISS_ENF-3", "ENFANT-4", "DATE_NAISS_ENF-4",
    "ENFANT-5", "DATE_NAISS_ENF-5", "IMAGE",
]


def _ligne_vide(num_famille, adherent="ADHERENT X", date_naiss="01/01/1980"):
    return (
        "1", None, num_famille, adherent, date_naiss, "12345678", "31/12/2026", "CLIENT",
        None, None, None, None, None, None, None, None, None, None, None, None, None,
    )


def test_depivotage_produit_cinq_lignes():
    ligne = (
        "1", None, "F100", "ADHERENT UN", "01/01/1980", "12345678", "31/12/2026", "CLIENT",
        "CONJOINT UN", "01/01/1982",
        "ENFANT UN", "01/01/2005", "ENFANT DEUX", "01/01/2007", "ENFANT TROIS", "01/01/2009",
        None, None, None, None, None,
    )
    collecteur = CollecteurAnomalies()
    resultats = convertir_v0([ligne], EN_TETES_V0, "TEST.xlsx", "Export Familles", collecteur)
    assert len(resultats) == 5


def test_tracabilite_v0_ligne_et_colonne_source():
    lignes = [_ligne_vide(f"F10{i}") for i in range(4)]
    cinquieme = (
        "1", None, "F105", "ADHERENT CINQ", "01/01/1975", "12345678", None, "CLIENT",
        None, None,
        None, None, "ENFANT DEUX BIS", "date-invalide", None, None, None, None, None, None, None,
    )
    lignes.append(cinquieme)

    collecteur = CollecteurAnomalies()
    convertir_v0(lignes, EN_TETES_V0, "TEST.xlsx", "Export Familles", collecteur)

    anomalies_date = [a for a in collecteur.anomalies if a.code == "DATE_INVALIDE"]
    assert len(anomalies_date) == 1
    anomalie = anomalies_date[0]
    assert anomalie.ligne_source == 6
    assert anomalie.colonne_source == "DATE_NAISS_ENF-2"


def test_colonne_cin_absente_signale_sans_planter():
    # BOBA/COATS (19 colonnes) : pas de colonne CIN -> champ vidé sans
    # anomalie par personne (l'alerte est portée au niveau du fichier par
    # OngletDetecte.cin_absente, affichée par l'interface).
    en_tetes_sans_cin = [h for h in EN_TETES_V0 if h not in ("CIN", "DATE_EXPIRATION")]
    ligne = (
        "1", None, "F200", "ADHERENT SANS CIN", "01/01/1980", "CLIENT",
        None, None, None, None, None, None, None, None, None, None, None, None, None,
    )
    collecteur = CollecteurAnomalies()
    resultats = convertir_v0([ligne], en_tetes_sans_cin, "BOBA.xlsx", "Export Familles", collecteur)
    assert len(resultats) == 1
    assert resultats[0]["cin"] == ""
    assert not any(a.code == "CIN_MANQUANT_ADHERENT" for a in collecteur.anomalies)


def test_image_non_vide_detectee():
    ligne = list(_ligne_vide("F300"))
    ligne[-1] = "data:image/jpeg;base64,AAAA"
    collecteur = CollecteurAnomalies()
    convertir_v0([tuple(ligne)], EN_TETES_V0, "AKWEL.xlsx", "Export Familles", collecteur)
    assert any(a.code == "IMAGE_BASE64_DETECTEE" for a in collecteur.anomalies)


def test_colonne_finale_sans_entete_ignoree():
    en_tetes = EN_TETES_V0 + [None]
    ligne = _ligne_vide("F400") + ("valeur ignoree",)
    collecteur = CollecteurAnomalies()
    resultats = convertir_v0([ligne], en_tetes, "HUTCHINSON.xlsx", "Export Familles", collecteur)
    assert len(resultats) == 1
