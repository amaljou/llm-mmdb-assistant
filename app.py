import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings


# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Assistant AQL — Yelp / ArangoDB",
    page_icon="🧠",
    layout="wide",
)

PROJECT_ROOT = Path(__file__).resolve().parent

BENCHMARK_PATH = (
    PROJECT_ROOT
    / "data"
    / "benchmark"
    / "yelp_benchmark.json"
)

SCHEMA_PATH = (
    PROJECT_ROOT
    / "arangodb"
    / "schema_description.json"
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================
# IMPORTS DU PROJET
# ============================================================

from src.prompt_builder import PromptBuilder
from src.query_generator import QueryGenerator
from src.query_validator import QueryValidator
from src.privacy_filter import PrivacyFilter
from src.query_executor import QueryExecutor
from src.db_connector import get_database


MODELS = {
    "Mistral": "mistral:latest",
    "DeepSeek-Coder": "deepseek-coder:6.7b",
}


# ============================================================
# CHARGEMENT RAG
# ============================================================

@st.cache_resource(show_spinner="Initialisation du RAG...")
def load_rag_resources():

    if not BENCHMARK_PATH.exists():
        raise FileNotFoundError(
            f"Benchmark introuvable : {BENCHMARK_PATH}"
        )

    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(
            f"Schéma introuvable : {SCHEMA_PATH}"
        )

    with open(
        BENCHMARK_PATH,
        "r",
        encoding="utf-8"
    ) as f:
        benchmark = json.load(f)

    with open(
        SCHEMA_PATH,
        "r",
        encoding="utf-8"
    ) as f:
        schema = json.load(f)

    # --------------------------------------------------------
    # Documents du schéma
    # --------------------------------------------------------

    schema_documents = []

    for name, info in (
        schema["document_collections"].items()
    ):

        fields = info.get("fields", {})

        if isinstance(fields, dict):
            fields_text = ", ".join(fields.keys())
        else:
            fields_text = ", ".join(fields)

        content = f"""
Document collection: {name}

Description:
{info.get("description", "")}

Fields:
{fields_text}
""".strip()

        schema_documents.append(
            Document(
                page_content=content,
                metadata={
                    "name": name,
                    "kind": "document_collection",
                },
            )
        )

    for name, info in (
        schema["edge_collections"].items()
    ):

        content = f"""
Edge collection: {name}

Description:
{info.get("description", "")}

From:
{info.get("from", "")}

To:
{info.get("to", "")}
""".strip()

        schema_documents.append(
            Document(
                page_content=content,
                metadata={
                    "name": name,
                    "kind": "edge_collection",
                },
            )
        )

    # --------------------------------------------------------
    # Documents des exemples
    # --------------------------------------------------------

    example_documents = []

    for item in benchmark:

        content = f"""
Question:
{item["question"]}

Gold AQL:

{item["gold_aql"]}
""".strip()

        example_documents.append(
            Document(
                page_content=content,
                metadata={
                    "question_id": item["id"]
                },
            )
        )

    # --------------------------------------------------------
    # Embeddings + Chroma
    # --------------------------------------------------------

    embeddings = HuggingFaceEmbeddings(
        model_name=(
            "sentence-transformers/"
            "all-MiniLM-L6-v2"
        )
    )

    schema_store = Chroma.from_documents(
        documents=schema_documents,
        embedding=embeddings,
        collection_name="streamlit_yelp_schema",
    )

    examples_store = Chroma.from_documents(
        documents=example_documents,
        embedding=embeddings,
        collection_name="streamlit_yelp_examples",
    )

    return {
        "benchmark": benchmark,
        "schema": schema,
        "schema_documents": schema_documents,
        "schema_store": schema_store,
        "examples_store": examples_store,
    }


def detect_question_id(
    question,
    benchmark
):
    """
    Si l'utilisateur saisit exactement une question du benchmark,
    on récupère son ID afin d'exclure son Gold AQL du RAG.
    """

    normalized = question.strip().lower()

    for item in benchmark:

        if (
            item["question"]
            .strip()
            .lower()
            == normalized
        ):
            return item["id"]

    return "USER_QUERY"


def retrieve_rag_context(
    question,
    rag_resources,
    top_k_examples=5,
    top_k_schema=4,
):
    """
    Même logique RAG que dans l'expérimentation finale :
    - top_k_examples = 5
    - top_k_schema = 4
    - exclusion de la question courante
    - expansion du schéma via les exemples récupérés
    """

    benchmark = rag_resources["benchmark"]
    schema = rag_resources["schema"]
    schema_documents = (
        rag_resources["schema_documents"]
    )
    schema_store = rag_resources["schema_store"]
    examples_store = (
        rag_resources["examples_store"]
    )

    question_id = detect_question_id(
        question,
        benchmark
    )

    # --------------------------------------------------------
    # 1. Exemples similaires
    # --------------------------------------------------------

    retrieved_examples = (
        examples_store
        .similarity_search_with_score(
            question,
            k=top_k_examples + 5,
        )
    )

    filtered_examples = []

    for doc, score in retrieved_examples:

        if (
            doc.metadata.get("question_id")
            != question_id
        ):
            filtered_examples.append(
                (doc, score)
            )

        if (
            len(filtered_examples)
            >= top_k_examples
        ):
            break

    # --------------------------------------------------------
    # 2. Schéma sémantique
    # --------------------------------------------------------

    retrieved_schema = (
        schema_store
        .similarity_search_with_score(
            question,
            k=top_k_schema,
        )
    )

    selected_names = {
        doc.metadata.get("name")
        for doc, _ in retrieved_schema
    }

    # --------------------------------------------------------
    # 3. Expansion à partir des exemples
    # --------------------------------------------------------

    examples_text = "\n\n".join(
        doc.page_content
        for doc, _ in filtered_examples
    )

    for collection_name in (
        schema["document_collections"]
    ):

        if collection_name in examples_text:
            selected_names.add(
                collection_name
            )

    for edge_name, edge_info in (
        schema["edge_collections"].items()
    ):

        if edge_name in examples_text:

            selected_names.add(edge_name)

            from_collection = (
                edge_info.get("from")
            )

            to_collection = (
                edge_info.get("to")
            )

            if from_collection:
                selected_names.add(
                    from_collection
                )

            if to_collection:
                selected_names.add(
                    to_collection
                )

    # --------------------------------------------------------
    # 4. Contexte final
    # --------------------------------------------------------

    final_schema_documents = []

    for doc in schema_documents:

        if (
            doc.metadata.get("name")
            in selected_names
        ):
            final_schema_documents.append(
                doc
            )

    schema_context = "\n\n".join(
        doc.page_content
        for doc in final_schema_documents
    )

    examples_context = "\n\n".join(
        doc.page_content
        for doc, _ in filtered_examples
    )

    return {
        "question_id": question_id,
        "schema_context": schema_context,
        "examples_context": examples_context,
        "retrieved_schema": (
            final_schema_documents
        ),
        "retrieved_examples": (
            filtered_examples
        ),
    }


def build_rag_prompt(
    question,
    rag_resources
):

    rag_input = retrieve_rag_context(
        question=question,
        rag_resources=rag_resources,
        top_k_examples=5,
        top_k_schema=4,
    )

    prompt = PromptBuilder.build_rag_prompt(
        question=question,
        schema_context=(
            rag_input["schema_context"]
        ),
        examples_context=(
            rag_input["examples_context"]
        ),
    )

    return prompt, rag_input


# ============================================================
# ARANGODB
# ============================================================

@st.cache_resource(show_spinner=False)
def connect_arangodb(
    host,
    database,
    username,
    password,
):
    db = get_database(
        host=host,
        database=database,
        username=username,
        password=password,
    )

    # Force une vraie requête afin de vérifier la connexion.
    db.version()

    return db


# ============================================================
# INTERFACE
# ============================================================

st.title(
    "🧠 Assistant intelligent NL → AQL"
)

st.caption(
    "Question en langage naturel → RAG → LLM → "
    "Agent de validation/correction → PrivacyFilter "
    "→ ArangoDB"
)


# ------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------

with st.sidebar:

    st.header("Configuration")

    model_label = st.selectbox(
        "Modèle",
        list(MODELS.keys()),
        index=0,
    )

    model_name = MODELS[model_label]

    st.code(
        model_name,
        language="text"
    )

    st.divider()

    use_database = st.checkbox(
        "Exécuter sur ArangoDB",
        value=True,
    )

    if use_database:

        db_host = st.text_input(
            "Host ArangoDB",
            value="http://localhost:8529",
        )

        db_name = st.text_input(
            "Base",
            value="YelpDB",
        )

        db_user = st.text_input(
            "Utilisateur",
            value="root",
        )

        db_password = st.text_input(
            "Mot de passe",
            value="root",
            type="password",
        )

        execution_corrections = (
            st.checkbox(
                "Correction après erreur d'exécution",
                value=True,
            )
        )

    else:

        db_host = ""
        db_name = ""
        db_user = ""
        db_password = ""
        execution_corrections = False

    st.divider()

    show_rag = st.checkbox(
        "Afficher le contexte RAG",
        value=False,
    )

    show_history = st.checkbox(
        "Afficher l'historique Agent",
        value=False,
    )


# ------------------------------------------------------------
# Chargement des ressources
# ------------------------------------------------------------

try:

    rag_resources = load_rag_resources()

except Exception as exc:

    st.error(
        "Impossible d'initialiser le RAG."
    )

    st.exception(exc)

    st.stop()


# ------------------------------------------------------------
# Saisie utilisateur
# ------------------------------------------------------------

question = st.text_area(
    "Question utilisateur",
    height=110,
    placeholder=(
        "Exemple : Give me all the Moroccan "
        "restaurants in Texas"
    ),
)

run_button = st.button(
    "🚀 Générer la requête AQL",
    type="primary",
    use_container_width=True,
)


# ============================================================
# PIPELINE
# ============================================================

if run_button:

    if not question.strip():

        st.warning(
            "Veuillez saisir une question."
        )

        st.stop()

    # --------------------------------------------------------
    # Validator + Privacy
    # --------------------------------------------------------

    validator = QueryValidator(
        str(SCHEMA_PATH)
    )

    privacy_filter = PrivacyFilter()

    # --------------------------------------------------------
    # QueryGenerator
    # --------------------------------------------------------

    generator = QueryGenerator(
        model_name=model_name
    )

    # --------------------------------------------------------
    # ArangoDB / Executor
    # --------------------------------------------------------

    executor = None
    database_status = "Non demandée"

    if use_database:

        try:

            db = connect_arangodb(
                db_host,
                db_name,
                db_user,
                db_password,
            )

            executor = QueryExecutor(
                db,
                validator,
            )

            database_status = "Connectée"

        except Exception as exc:

            database_status = "Échec"

            st.warning(
                "ArangoDB n'est pas accessible. "
                "La génération continue sans exécution."
            )

            st.caption(str(exc))

            executor = None

    # --------------------------------------------------------
    # RAG
    # --------------------------------------------------------

    try:

        with st.spinner(
            "Récupération du contexte RAG..."
        ):

            prompt, rag_input = (
                build_rag_prompt(
                    question,
                    rag_resources,
                )
            )

    except Exception as exc:

        st.error(
            "Erreur pendant la construction du RAG."
        )

        st.exception(exc)

        st.stop()

    # --------------------------------------------------------
    # Agent
    # --------------------------------------------------------

    try:

        with st.spinner(
            f"Génération avec {model_label}..."
        ):

            result = (
                generator
                .generate_with_correction(
                    prompt=prompt,
                    question=question,
                    validator=validator,
                    schema_context=(
                        rag_input[
                            "schema_context"
                        ]
                    ),
                    examples_context=(
                        rag_input[
                            "examples_context"
                        ]
                    ),
                    max_corrections=2,
                    use_schema_repair=True,
                    executor=executor,
                    privacy_filter=(
                        privacy_filter
                    ),
                    max_execution_corrections=(
                        1
                        if (
                            executor is not None
                            and execution_corrections
                        )
                        else 0
                    ),
                )
            )

    except Exception as exc:

        st.error(
            "Erreur pendant la génération."
        )

        st.exception(exc)

        st.stop()

    # --------------------------------------------------------
    # Résumé
    # --------------------------------------------------------

    validation = (
        result.get("validation")
        or {}
    )

    privacy = (
        result.get("privacy")
        or {}
    )

    execution = (
        result.get("execution")
        or {}
    )

    valid = bool(
        result.get("valid")
    )

    privacy_allowed = (
        privacy.get("allowed")
        if privacy
        else None
    )

    executed = (
        result.get("executed")
    )

    col1, col2, col3, col4, col5 = (
        st.columns(5)
    )

    col1.metric(
        "Modèle",
        model_label,
    )

    col2.metric(
        "Validité",
        "✅ Valide"
        if valid
        else "❌ Invalide",
    )

    col3.metric(
        "Correction",
        "Oui"
        if result.get("corrected")
        else "Non",
    )

    col4.metric(
        "Privacy",
        (
            "✅ Autorisée"
            if privacy_allowed is True
            else (
                "⛔ Bloquée"
                if privacy_allowed is False
                else "—"
            )
        ),
    )

    col5.metric(
        "Temps",
        (
            f"{result.get('generation_time', 0):.2f} s"
        ),
    )

    st.caption(
        f"ArangoDB : {database_status}"
    )

    # --------------------------------------------------------
    # AQL
    # --------------------------------------------------------

    st.subheader(
        "Requête AQL finale"
    )

    st.code(
        result.get("aql", ""),
        language="text",
    )

    if result.get("corrected"):

        with st.expander(
            "Voir la requête initiale"
        ):

            st.code(
                result.get(
                    "original_aql",
                    "",
                ),
                language="text",
            )

            st.write(
                "Tentatives de correction LLM :",
                result.get(
                    "correction_attempts",
                    0,
                ),
            )

            st.write(
                "Tentatives de correction "
                "après exécution :",
                result.get(
                    "execution_correction_attempts",
                    0,
                ),
            )

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    st.subheader(
        "Validation"
    )

    if valid:

        st.success(
            "La requête respecte les contrôles "
            "statiques du validateur."
        )

    else:

        st.error(
            "La requête finale reste invalide."
        )

    if validation.get("errors"):

        st.write(
            "**Erreurs :**"
        )

        for error in validation["errors"]:
            st.write(f"- {error}")

    if validation.get("warnings"):

        st.write(
            "**Avertissements :**"
        )

        for warning in (
            validation["warnings"]
        ):
            st.write(f"- {warning}")

    # --------------------------------------------------------
    # Privacy
    # --------------------------------------------------------

    st.subheader(
        "Confidentialité"
    )

    if privacy_allowed is False:

        st.error(
            "La requête a été bloquée par "
            "le PrivacyFilter."
        )

        fields = privacy.get(
            "sensitive_fields",
            [],
        )

        if fields:
            st.write(
                "Champs sensibles détectés :",
                ", ".join(fields),
            )

    elif privacy_allowed is True:

        st.success(
            "Aucun champ sensible bloquant "
            "n'a été détecté."
        )

    # --------------------------------------------------------
    # Résultats ArangoDB
    # --------------------------------------------------------

    st.subheader(
        "Résultat"
    )

    if executor is None:

        st.info(
            "La requête n'a pas été exécutée. "
            "Activez ArangoDB dans la barre latérale "
            "pour afficher les données."
        )

    elif executed is True:

        # ----------------------------------------------------
        # Récupération robuste des données renvoyées
        # ----------------------------------------------------
        rows = execution.get("results")

        # Certaines versions du pipeline peuvent utiliser
        # un autre nom de clé.
        if rows is None:
            rows = execution.get("result")

        if rows is None:
            rows = execution.get("data")

        # Si l'Agent indique que la requête a été exécutée,
        # mais ne conserve pas réellement les lignes, on
        # ré-exécute uniquement l'AQL finale pour l'affichage.
        if rows is None:
            try:
                final_aql = result.get("aql", "")
                cursor = db.aql.execute(final_aql)
                rows = list(cursor)
            except Exception as exc:
                rows = []
                st.warning(
                    "La requête a été exécutée, mais les données "
                    "n'ont pas pu être récupérées pour l'affichage."
                )
                st.caption(str(exc))

        # Toujours convertir en liste pour simplifier l'affichage.
        if not isinstance(rows, list):
            rows = [rows]

        st.success(
            f"Exécution réussie — {len(rows)} résultat(s)."
        )

        if rows:

            st.markdown("### Données retournées")

            # Limiter l'aperçu pour éviter de surcharger Streamlit.
            max_display = 100
            preview = rows[:max_display]

            try:
                # Cas 1 : résultats sous forme de documents/dictionnaires.
                if all(
                    isinstance(row, dict)
                    for row in preview
                ):
                    df_results = pd.DataFrame(preview)

                # Cas 2 : résultats scalaires (noms, nombres, chaînes...).
                else:
                    df_results = pd.DataFrame(
                        {"resultat": preview}
                    )

                st.dataframe(
                    df_results,
                    use_container_width=True,
                    hide_index=True,
                    height=420,
                )

                if len(rows) > max_display:
                    st.info(
                        f"Affichage des {max_display} premiers "
                        f"résultats sur {len(rows)}."
                    )

                # Export CSV pratique pour la démonstration.
                csv_data = df_results.to_csv(
                    index=False
                ).encode("utf-8")

                st.download_button(
                    "⬇️ Télécharger l'aperçu en CSV",
                    data=csv_data,
                    file_name="arangodb_results.csv",
                    mime="text/csv",
                )

            except Exception as exc:
                # Fallback : affichage brut si DataFrame échoue.
                st.warning(
                    "Affichage tabulaire impossible. "
                    "Affichage brut des premiers résultats."
                )
                st.write(preview)
                st.caption(str(exc))

        else:

            st.info(
                "La requête a été exécutée "
                "mais n'a retourné aucun résultat."
            )

    else:

        execution_error = execution.get(
            "error"
        )

        if execution_error:

            st.error(
                "La requête n'a pas été exécutée."
            )

            st.code(
                str(execution_error),
                language="text",
            )

        elif privacy_allowed is False:

            st.warning(
                "Exécution interdite par le "
                "PrivacyFilter."
            )

        elif not valid:

            st.warning(
                "Exécution interdite par le "
                "QueryValidator."
            )

    # --------------------------------------------------------
    # Informations RAG
    # --------------------------------------------------------

    if show_rag:

        st.subheader(
            "Contexte RAG"
        )

        with st.expander(
            "Schéma récupéré",
            expanded=False,
        ):

            st.text(
                rag_input[
                    "schema_context"
                ]
            )

        with st.expander(
            "Exemples récupérés",
            expanded=False,
        ):

            for index, (
                doc,
                score,
            ) in enumerate(
                rag_input[
                    "retrieved_examples"
                ],
                start=1,
            ):

                st.write(
                    f"**Exemple {index} "
                    f"— score {score:.4f}**"
                )

                st.code(
                    doc.page_content,
                    language="text",
                )

    # --------------------------------------------------------
    # Historique Agent
    # --------------------------------------------------------

    if show_history:

        st.subheader(
            "Historique Agent"
        )

        st.json(
            result.get(
                "history",
                [],
            )
        )
