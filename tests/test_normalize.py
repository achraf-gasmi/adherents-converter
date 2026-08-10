from datetime import date

from core.normalize import (
    deviner_gendre, est_ligne_fantome, nettoyer_cin, nettoyer_nom,
    nettoyer_rib, normaliser_gendre, parser_date, resoudre_gendre,
)


def test_nettoyer_nom_asterisques():
    nom, modifie = nettoyer_nom("DUPONT** MARTIN**", uppercase=True)
    assert nom == "DUPONT MARTIN"
    assert modifie is True


def test_nettoyer_nom_point_final():
    nom, _ = nettoyer_nom("DURAND ALICE.", uppercase=True)
    assert nom == "DURAND ALICE"


def test_nettoyer_nom_suffixe_numerique():
    nom, _ = nettoyer_nom("LEROY SOPHIE3", uppercase=True)
    assert nom == "LEROY SOPHIE"


def test_nettoyer_nom_espaces_multiples_et_bords():
    nom, _ = nettoyer_nom(" PETIT  JULIE", uppercase=True)
    assert nom == "PETIT JULIE"


def test_nettoyer_nom_entierement_masque():
    nom, _ = nettoyer_nom("* *", uppercase=True)
    assert nom == ""


def test_nettoyer_nom_sans_modification():
    nom, modifie = nettoyer_nom("MOREAU PAUL", uppercase=True)
    assert nom == "MOREAU PAUL"
    assert modifie is False


def test_cin_7_chiffres_complete():
    resultat = nettoyer_cin("5705239")
    assert resultat.valeur == "05705239"
    assert resultat.code == "CIN_COMPLETE"


def test_cin_espaces_insecables():
    resultat = nettoyer_cin("9 292 762")
    assert resultat.valeur == "09292762"
    assert resultat.code == "CIN_COMPLETE"


def test_cin_booleen_false():
    resultat = nettoyer_cin(False)
    assert resultat.valeur == ""
    assert resultat.code == "CIN_INVALIDE"


def test_cin_asterisque_seul():
    resultat = nettoyer_cin("*")
    assert resultat.valeur == ""
    assert resultat.code == "CIN_INVALIDE"


def test_cin_court():
    resultat = nettoyer_cin("47")
    assert resultat.valeur == ""
    assert resultat.code == "CIN_INVALIDE"


def test_cin_factice():
    resultat = nettoyer_cin("000000023")
    assert resultat.valeur == ""
    assert resultat.code == "CIN_FACTICE"


def test_cin_8_chiffres_conserve():
    resultat = nettoyer_cin("05705239")
    assert resultat.valeur == "05705239"
    assert resultat.code is None


def test_cin_vide_aucune_anomalie():
    resultat = nettoyer_cin(None)
    assert resultat.valeur == ""
    assert resultat.code is None


def test_cin_completer_desactive():
    resultat = nettoyer_cin("5705239", completer_cin=False)
    assert resultat.valeur == ""
    assert resultat.code == "CIN_INVALIDE"


def test_rib_zeros_initiaux_preserves():
    resultat = nettoyer_rib("05206000051500152949")
    assert resultat.valeur == "05206000051500152949"
    assert resultat.code is None


def test_rib_invalide():
    resultat = nettoyer_rib("123")
    assert resultat.valeur == ""
    assert resultat.code == "RIB_INVALIDE"


def test_parser_date_dd_mm_yyyy():
    d, invalide = parser_date("29/05/1972")
    assert d == date(1972, 5, 29)
    assert invalide is False


def test_parser_date_invalide():
    d, invalide = parser_date("pas une date")
    assert d is None
    assert invalide is True


def test_parser_date_vide():
    d, invalide = parser_date(None)
    assert d is None
    assert invalide is False


def test_normaliser_gendre():
    assert normaliser_gendre("h") == "H"
    assert normaliser_gendre("M") == "H"
    assert normaliser_gendre("f") == "F"
    assert normaliser_gendre(None) == ""
    assert normaliser_gendre("X") == ""


def test_est_ligne_fantome():
    assert est_ligne_fantome(None, None, None, None) is True
    assert est_ligne_fantome("Adhérent", None, None, None) is False
    assert est_ligne_fantome(None, "DURAND PIERRE", None, None) is False


def test_deviner_gendre_masculin_et_feminin_confiant():
    resultat_h = deviner_gendre("DUPONT MOHAMED")
    assert resultat_h.valeur == "H"
    assert resultat_h.confiant is True

    resultat_f = deviner_gendre("DUPONT FATMA")
    assert resultat_f.valeur == "F"
    assert resultat_f.confiant is True


def test_deviner_gendre_prenom_compose_avant_dernier_mot():
    # "MOHAMED" (avant-dernier mot) est reconnu même si "ALI" (dernier mot)
    # ne l'est pas dans le dictionnaire.
    resultat = deviner_gendre("DUPONT MOHAMED ALI")
    assert resultat.valeur == "H"
    assert resultat.confiant is True


def test_deviner_gendre_jamais_vide_meme_sans_signal():
    # Ni dictionnaire ni suffixe indicatif : repli sur la valeur par défaut,
    # mais JAMAIS de chaîne vide (règle métier : la colonne Gendre ne doit
    # jamais rester vide).
    resultat = deviner_gendre("DUPONT XYZQWK")
    assert resultat.valeur in ("H", "F")
    assert resultat.confiant is False

    resultat_vide = deviner_gendre("")
    assert resultat_vide.valeur in ("H", "F")
    assert resultat_vide.confiant is False


def test_deviner_gendre_heuristique_suffixe_feminin():
    resultat = deviner_gendre("DUPONT ZANOUBA")
    assert resultat.valeur == "F"
    assert resultat.confiant is False


def test_resoudre_gendre_valeur_source_prioritaire():
    resultat = resoudre_gendre("F", "DUPONT MOHAMED")
    assert resultat.valeur == "F"
    assert resultat.code is None


def test_resoudre_gendre_deduit_du_prenom_quand_source_vide():
    resultat = resoudre_gendre(None, "DUPONT MOHAMED")
    assert resultat.valeur == "H"
    assert resultat.code == "GENDRE_DEVINE"


def test_resoudre_gendre_jamais_vide_meme_incertain():
    resultat = resoudre_gendre(None, "DUPONT XYZQWK")
    assert resultat.valeur in ("H", "F")
    assert resultat.valeur != ""
    assert resultat.code == "GENDRE_DEVINE_INCERTAIN"
