"""
app.py
=======
Interface Streamlit du convertisseur de fichiers adhérents BH Assurance.
Page unique en 4 sections : Import (upload + détection V0/V1 + bandeaux
d'alerte), Configuration (options de normalisation), Conversion (pipeline +
aperçu), Export (téléchargement par fichier, consolidé, rapport global, ZIP).
Toute la logique métier vit dans core/ ; ce module ne fait que l'orchestrer
et l'afficher.
"""
from __future__ import annotations

import io
import zipfile
from datetime import date
from io import BytesIO

import openpyxl
import pandas as pd
import streamlit as st

from core.anomalies import (
    COLONNES_ANOMALIES, SEVERITE_AVERTISSEMENT, SEVERITE_ERREUR,
    SEVERITE_INFORMATION, CollecteurAnomalies,
)
from core.convert_v0 import convertir_v0
from core.convert_v1 import convertir_v1
from core.detection import VERSION_INCONNUE, VERSION_V0, VERSION_V1, OngletDetecte, detecter_classeur
from core.export import calculer_resume, construire_fichier_cible, construire_rapport_anomalies
from core.mapping import (
    F_CIN, F_CLIENT, F_DATE_AFFILIATION, F_DATE_NAISSANCE, F_FICHIER_SOURCE,
    F_GENDRE, F_LIEN, F_NOM, F_NUM_FAMILLE, F_ONGLET_SOURCE, F_RANG, F_RIB,
)
from core.ranking import (
    calculer_rangs, detecter_doublons_inter_source, finaliser_champs_rang0,
    verifier_num_famille_unique,
)

st.set_page_config(page_title="Convertisseur adhérents BH Assurance", layout="wide")


# --------------------------------------------------------------------------
# Détection (mise en cache pour ne pas relire les fichiers à chaque interaction)
# --------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _detecter(contenu: bytes, nom_fichier: str) -> list[OngletDetecte]:
    return detecter_classeur(contenu, nom_fichier)


def _nom_base(nom_fichier: str) -> str:
    return nom_fichier.rsplit(".", 1)[0]


def _lire_lignes_donnees(contenu: bytes, nom_onglet: str) -> list[tuple]:
    classeur = openpyxl.load_workbook(BytesIO(contenu), read_only=True, data_only=True)
    feuille = classeur[nom_onglet]
    lignes = []
    for ligne in feuille.iter_rows(min_row=2, values_only=True):
        if any(c is not None and str(c).strip() != "" for c in ligne):
            lignes.append(ligne)
    return lignes


# --------------------------------------------------------------------------
# Pipeline de conversion
# --------------------------------------------------------------------------

def _executer_conversion(
    contenus: dict[str, bytes],
    sources_a_traiter: list[dict],
    detections_par_cle: dict[tuple, OngletDetecte],
    options: dict,
    barre_progression,
) -> tuple[list[dict], CollecteurAnomalies]:
    collecteur = CollecteurAnomalies()
    toutes_lignes: list[dict] = []

    for i, source in enumerate(sources_a_traiter):
        fichier, onglet, version = source["Fichier"], source["Onglet"], source["Version effective"]
        barre_progression.progress((i) / max(len(sources_a_traiter), 1), text=f"Conversion de {fichier} / {onglet}...")

        detection = detections_par_cle[(fichier, onglet)]
        contenu = contenus[fichier]
        lignes_source = _lire_lignes_donnees(contenu, onglet)

        if version == VERSION_V0:
            lignes = convertir_v0(
                lignes_source, detection.en_tetes_bruts, fichier, onglet, collecteur,
                uppercase_noms=options["uppercase_noms"], completer_cin=options["completer_cin"],
                vider_cin_factices=options["vider_cin_factices"],
            )
        elif version == VERSION_V1:
            lignes = convertir_v1(
                lignes_source, detection.en_tetes_bruts, fichier, onglet, collecteur,
                uppercase_noms=options["uppercase_noms"],
                supprimer_lignes_fantomes=options["supprimer_lignes_fantomes"],
                completer_cin=options["completer_cin"], vider_cin_factices=options["vider_cin_factices"],
            )
        else:
            continue

        toutes_lignes.extend(lignes)

    barre_progression.progress(0.9, text="Calcul des rangs et vérifications de cohérence...")
    calculer_rangs(toutes_lignes, collecteur, date_reference=date.today())
    finaliser_champs_rang0(toutes_lignes, collecteur)
    verifier_num_famille_unique(toutes_lignes, collecteur)
    detecter_doublons_inter_source(toutes_lignes, collecteur)
    barre_progression.progress(1.0, text="Terminé.")

    return toutes_lignes, collecteur


# --------------------------------------------------------------------------
# Présentation
# --------------------------------------------------------------------------

_CHAMPS_AFFICHAGE = [
    (F_CLIENT, "Client"), (F_NUM_FAMILLE, "N° Famille"), (F_LIEN, "Lien"),
    (F_GENDRE, "Gendre"), (F_NOM, "Nom"), (F_DATE_NAISSANCE, "Date de naissance"),
    (F_DATE_AFFILIATION, "Date d'affiliation"), (F_NUM_FAMILLE, "N° Famille (H)"),
    (F_RANG, "Rang"), (F_RIB, "RIB"), (F_CIN, "Identité gouvernementale"),
]


def _lignes_vers_dataframe(lignes: list[dict]) -> pd.DataFrame:
    donnees = []
    for ligne in lignes:
        donnees.append({label: ligne.get(champ) for champ, label in _CHAMPS_AFFICHAGE})
    df = pd.DataFrame(donnees, columns=[label for _, label in _CHAMPS_AFFICHAGE])
    if not df.empty:
        df = df.sort_values(by=["N° Famille", "Rang"], na_position="last")
    return df


def _anomalies_vers_dataframe(anomalies: list) -> pd.DataFrame:
    return pd.DataFrame([a.vers_ligne() for a in anomalies], columns=COLONNES_ANOMALIES)


def _construire_exports(lignes: list[dict], collecteur: CollecteurAnomalies, export_consolide: bool) -> dict[str, bytes]:
    """Construit en mémoire tous les classeurs à proposer au téléchargement."""
    fichiers: dict[str, bytes] = {}

    groupes: dict[str, set[str]] = {}
    for ligne in lignes:
        groupes.setdefault(ligne[F_FICHIER_SOURCE], set()).add(ligne[F_ONGLET_SOURCE])

    for fichier_source, onglets in groupes.items():
        for onglet in onglets:
            lignes_groupe = [l for l in lignes if l[F_FICHIER_SOURCE] == fichier_source and l[F_ONGLET_SOURCE] == onglet]
            anomalies_groupe = [
                a for a in collecteur.anomalies
                if a.fichier_source == fichier_source and a.onglet_source == onglet
            ]
            suffixe = f"_{onglet}" if len(onglets) > 1 else ""
            nom_sortie = f"{_nom_base(fichier_source)}{suffixe}_CIBLE.xlsx".replace("/", "-")
            tampon = construire_fichier_cible(lignes_groupe, anomalies_groupe)
            fichiers[nom_sortie] = tampon.getvalue()

    if export_consolide:
        tampon = construire_fichier_cible(lignes, collecteur.anomalies)
        fichiers["CONSOLIDE_CIBLE.xlsx"] = tampon.getvalue()

    tampon_rapport = construire_rapport_anomalies(lignes, collecteur.anomalies)
    fichiers["RAPPORT_ANOMALIES.xlsx"] = tampon_rapport.getvalue()

    return fichiers


def _construire_zip(fichiers: dict[str, bytes]) -> bytes:
    tampon = BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
        for nom, contenu in fichiers.items():
            archive.writestr(nom, contenu)
    return tampon.getvalue()


# --------------------------------------------------------------------------
# Interface
# --------------------------------------------------------------------------

st.title("Convertisseur de fichiers adhérents — BH Assurance")
st.caption(
    "Direction Organisation et Qualité — convergence des formats source V0/V1 vers le format cible unique. "
    "Toute valeur corrigée, complétée ou rejetée est journalisée dans le rapport d'anomalies avec sa valeur d'origine."
)

st.header("1. Import")
fichiers_uploades = st.file_uploader(
    "Fichiers Excel des entreprises clientes", type=["xlsx"], accept_multiple_files=True,
)

contenus: dict[str, bytes] = {}
detections: list[OngletDetecte] = []

if fichiers_uploades:
    for f in fichiers_uploades:
        contenu = f.getvalue()
        contenus[f.name] = contenu
        detections.extend(_detecter(contenu, f.name))

if detections:
    lignes_tableau = []
    for d in detections:
        lignes_tableau.append({
            "Fichier": d.nom_fichier,
            "Onglet": d.nom_onglet,
            "Version détectée": d.version,
            "Lignes": d.nb_lignes,
            "Familles": d.nb_familles,
            "Inclure": d.erreur is None and d.version != VERSION_INCONNUE,
            "Version forcée": "Auto",
        })
    df_import = pd.DataFrame(lignes_tableau)

    edite = st.data_editor(
        df_import,
        column_config={
            "Inclure": st.column_config.CheckboxColumn("Inclure", default=True),
            "Version forcée": st.column_config.SelectboxColumn("Version forcée", options=["Auto", "V0", "V1"]),
        },
        disabled=["Fichier", "Onglet", "Version détectée", "Lignes", "Familles"],
        hide_index=True,
        use_container_width=True,
        key="editeur_import",
    )

    for d in detections:
        if d.erreur:
            st.error(f"**{d.nom_fichier}** : {d.erreur}")
        if d.image_non_vide:
            st.error(
                f"**{d.nom_fichier} / {d.nom_onglet}** contient une colonne IMAGE non vide "
                "(photos encodées en base64 — données personnelles). Ces données ne seront jamais exportées."
            )
        if d.cin_absente:
            st.warning(f"**{d.nom_fichier} / {d.nom_onglet}** : ce fichier source ne comporte aucune colonne CIN.")
        elif d.pct_sans_cin is not None and d.pct_sans_cin > 30:
            st.warning(f"**{d.nom_fichier} / {d.nom_onglet}** : {d.pct_sans_cin} % des adhérents sont sans CIN.")
        if d.version == VERSION_INCONNUE and not d.erreur:
            st.warning(
                f"**{d.nom_fichier} / {d.nom_onglet}** : version non détectée automatiquement. "
                f"En-têtes trouvées : {d.en_tetes}. Vous pouvez forcer une version dans le tableau ci-dessus "
                "si ces en-têtes correspondent malgré tout à un format connu."
            )
else:
    st.info("Importez un ou plusieurs fichiers Excel (.xlsx) pour commencer.")

st.header("2. Configuration")
with st.expander("Options de normalisation", expanded=False):
    col1, col2, col3 = st.columns(3)
    completer_cin = col1.checkbox("Compléter les CIN à 7 chiffres", value=True, help="Ajoute un zéro à gauche (Excel supprime le zéro initial d'un CIN à 8 chiffres stocké en nombre).")
    uppercase_noms = col1.checkbox("Mettre les noms en majuscules", value=True)
    supprimer_lignes_fantomes = col2.checkbox("Supprimer les lignes fantômes", value=True, help="Lignes où Rang, Lien, Nom et Date de naissance sont tous vides.")
    vider_cin_factices = col2.checkbox("Vider les CIN factices", value=True, help="Séquences de zéros de tête suivies d'un nombre court (ex. 000000023).")
    export_consolide = col3.checkbox("Générer un export consolidé", value=True)

options = {
    "completer_cin": completer_cin,
    "uppercase_noms": uppercase_noms,
    "supprimer_lignes_fantomes": supprimer_lignes_fantomes,
    "vider_cin_factices": vider_cin_factices,
}

st.header("3. Conversion")

if st.button("Convertir", type="primary", disabled=not detections):
    detections_par_cle = {(d.nom_fichier, d.nom_onglet): d for d in detections}
    sources_a_traiter = []
    for _, ligne in edite.iterrows():
        if not ligne["Inclure"]:
            continue
        version_effective = ligne["Version détectée"] if ligne["Version forcée"] == "Auto" else ligne["Version forcée"]
        if version_effective not in (VERSION_V0, VERSION_V1):
            continue
        sources_a_traiter.append({
            "Fichier": ligne["Fichier"], "Onglet": ligne["Onglet"], "Version effective": version_effective,
        })

    barre = st.progress(0.0, text="Démarrage...")
    lignes, collecteur = _executer_conversion(contenus, sources_a_traiter, detections_par_cle, options, barre)
    st.session_state["lignes"] = lignes
    st.session_state["collecteur"] = collecteur
    st.session_state["export_consolide"] = export_consolide

if "lignes" in st.session_state:
    lignes = st.session_state["lignes"]
    collecteur: CollecteurAnomalies = st.session_state["collecteur"]
    severites = collecteur.par_severite()
    familles = {(l[F_FICHIER_SOURCE], l[F_ONGLET_SOURCE], l[F_NUM_FAMILLE]) for l in lignes}

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Lignes en sortie", len(lignes))
    c2.metric("Familles", len(familles))
    c3.metric("Erreurs", severites[SEVERITE_ERREUR])
    c4.metric("Avertissements", severites[SEVERITE_AVERTISSEMENT])
    c5.metric("Informations", severites[SEVERITE_INFORMATION])

    onglet_apercu, onglet_anomalies, onglet_synthese = st.tabs(
        ["Aperçu des données", "Anomalies", "Synthèse par fichier"]
    )

    with onglet_apercu:
        st.dataframe(_lignes_vers_dataframe(lignes), use_container_width=True, hide_index=True)

    with onglet_anomalies:
        df_anomalies = _anomalies_vers_dataframe(collecteur.anomalies)
        if df_anomalies.empty:
            st.success("Aucune anomalie détectée.")
        else:
            fc1, fc2, fc3 = st.columns(3)
            fichiers_dispo = sorted(df_anomalies["Fichier source"].unique())
            codes_dispo = sorted(df_anomalies["Code"].unique())
            severites_dispo = sorted(df_anomalies["Sévérité"].unique())
            filtre_fichier = fc1.multiselect("Fichier source", fichiers_dispo)
            filtre_code = fc2.multiselect("Code", codes_dispo)
            filtre_severite = fc3.multiselect("Sévérité", severites_dispo)

            df_filtre = df_anomalies
            if filtre_fichier:
                df_filtre = df_filtre[df_filtre["Fichier source"].isin(filtre_fichier)]
            if filtre_code:
                df_filtre = df_filtre[df_filtre["Code"].isin(filtre_code)]
            if filtre_severite:
                df_filtre = df_filtre[df_filtre["Sévérité"].isin(filtre_severite)]
            st.dataframe(df_filtre, use_container_width=True, hide_index=True)

    with onglet_synthese:
        resume = calculer_resume(lignes, collecteur.anomalies)
        df_resume = pd.DataFrame([
            {"Fichier source": f, "Lignes": r["lignes"], "Erreurs": r[SEVERITE_ERREUR],
             "Avertissements": r[SEVERITE_AVERTISSEMENT], "Informations": r[SEVERITE_INFORMATION],
             "% sans anomalie bloquante": r["pct_sans_erreur"]}
            for f, r in sorted(resume.items())
        ])
        st.dataframe(df_resume, use_container_width=True, hide_index=True)

    st.header("4. Export")
    if "exports" not in st.session_state or st.session_state.get("exports_export_consolide") != st.session_state.get("export_consolide"):
        st.session_state["exports"] = _construire_exports(lignes, collecteur, st.session_state.get("export_consolide", True))
        st.session_state["exports_export_consolide"] = st.session_state.get("export_consolide")

    exports: dict[str, bytes] = st.session_state["exports"]
    for nom_fichier, contenu in sorted(exports.items()):
        st.download_button(
            label=f"Télécharger {nom_fichier}", data=contenu, file_name=nom_fichier,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"dl_{nom_fichier}",
        )

    st.download_button(
        label="Tout télécharger (ZIP)", data=_construire_zip(exports), file_name="conversion_BH_assurance.zip",
        mime="application/zip", key="dl_zip",
    )
