import json
import os
from arango import ArangoClient


# =========================================================
# CONFIGURATION
# =========================================================

ARANGO_URL = "http://localhost:8529"
DATABASE_NAME = "YelpDB"
USERNAME = "root"
PASSWORD = "root"   # à modifier si nécessaire

GRAPH_NAME = "YelpGraph"

OUTPUT_FILE = os.path.join(
    os.path.dirname(__file__),
    "..",
    "arangodb",
    "schema_description.json"
)


# =========================================================
# CONNEXION À ARANGODB
# =========================================================

client = ArangoClient(
    hosts=ARANGO_URL,
    request_timeout=300
)

db = client.db(
    DATABASE_NAME,
    username=USERNAME,
    password=PASSWORD
)

print("Connexion à YelpDB réussie.")


# =========================================================
# FONCTION DE DÉTECTION DU TYPE
# =========================================================

def detect_type(value):

    if value is None:
        return "null"

    if isinstance(value, bool):
        return "boolean"

    if isinstance(value, int):
        return "integer"

    if isinstance(value, float):
        return "number"

    if isinstance(value, str):
        return "string"

    if isinstance(value, list):
        return "array"

    if isinstance(value, dict):
        return "object"

    return type(value).__name__


# =========================================================
# DESCRIPTION MANUELLE DES COLLECTIONS
# =========================================================

COLLECTION_DESCRIPTIONS = {

    "Businesses":
        "Businesses from the Yelp dataset.",

    "Users":
        "Users from the Yelp dataset.",

    "Reviews":
        "Reviews written by users about businesses.",

    "Tips":
        "Tips written by users about businesses.",

    "Categories":
        "Categories associated with businesses.",

    "Checkins":
        "Check-in information associated with businesses.",

    "Neighborhoods":
        "Neighborhood information associated with businesses."
}


EDGE_DESCRIPTIONS = {

    "WritesReview":
        "A user writes a review.",

    "ReviewsBusiness":
        "A review refers to a business.",

    "WritesTip":
        "A user writes a tip.",

    "TipsBusiness":
        "A tip refers to a business.",

    "BusinessCategory":
        "A business is associated with a category.",

    "BusinessCheckin":
        "A business has check-in records.",

    "BusinessNeighborhood":
        "A business is associated with a neighborhood."
}


# =========================================================
# EXTRACTION DES DOCUMENT COLLECTIONS
# =========================================================

def profile_document_collection(collection_name):

    collection = db.collection(collection_name)

    print(f"Analyse de {collection_name}...")

    # On récupère un petit échantillon
    query = f"""
    FOR doc IN {collection_name}
        LIMIT 100
        RETURN doc
    """

    documents = list(db.aql.execute(query))

    fields = {}

    for doc in documents:

        for field_name, value in doc.items():

            # On ignore les champs système ArangoDB
            if field_name in ["_id", "_key", "_rev"]:
                continue

            if field_name not in fields:

                fields[field_name] = {
                    "type": detect_type(value),
                    "example": value
                }

            else:

                # Si le premier exemple était null,
                # on essaye de récupérer un vrai type
                if fields[field_name]["type"] == "null" and value is not None:

                    fields[field_name]["type"] = detect_type(value)
                    fields[field_name]["example"] = value

    return {

        "type": "document",

        "description":
            COLLECTION_DESCRIPTIONS.get(
                collection_name,
                f"Document collection {collection_name}"
            ),

        "document_count":
            collection.count(),

        "fields":
            fields
    }


# =========================================================
# EXTRACTION DES EDGE COLLECTIONS
# =========================================================

def profile_edge_collection(edge_name):

    collection = db.collection(edge_name)

    print(f"Analyse de l'edge {edge_name}...")

    query = f"""
    FOR e IN {edge_name}
        LIMIT 1
        RETURN e
    """

    results = list(db.aql.execute(query))

    from_collection = None
    to_collection = None

    example = None

    if results:

        edge = results[0]

        from_id = edge.get("_from")
        to_id = edge.get("_to")

        if from_id:
            from_collection = from_id.split("/")[0]

        if to_id:
            to_collection = to_id.split("/")[0]

        example = {
            "_from": from_id,
            "_to": to_id
        }

    return {

        "type": "edge",

        "description":
            EDGE_DESCRIPTIONS.get(
                edge_name,
                f"Edge collection {edge_name}"
            ),

        "from":
            from_collection,

        "to":
            to_collection,

        "edge_count":
            collection.count(),

        "example":
            example
    }


# =========================================================
# COLLECTIONS DU PROJET
# =========================================================

DOCUMENT_COLLECTIONS = [
    "Businesses",
    "Users",
    "Reviews",
    "Tips",
    "Categories",
    "Checkins",
    "Neighborhoods"
]

EDGE_COLLECTIONS = [
    "WritesReview",
    "ReviewsBusiness",
    "WritesTip",
    "TipsBusiness",
    "BusinessCategory",
    "BusinessCheckin",
    "BusinessNeighborhood"
]


# =========================================================
# CONSTRUCTION DU SCHÉMA
# =========================================================

schema = {

    "database": DATABASE_NAME,

    "graph": GRAPH_NAME,

    "document_collections": {},

    "edge_collections": {},

    "relationships": []
}


# =========================================================
# PROFILAGE DES DOCUMENTS
# =========================================================

print("\nProfilage des collections Document...\n")

for collection_name in DOCUMENT_COLLECTIONS:

    if db.has_collection(collection_name):

        schema["document_collections"][collection_name] = \
            profile_document_collection(collection_name)

    else:

        print(
            f"ATTENTION : {collection_name} n'existe pas."
        )


# =========================================================
# PROFILAGE DES EDGES
# =========================================================

print("\nProfilage des Edge Collections...\n")

for edge_name in EDGE_COLLECTIONS:

    if db.has_collection(edge_name):

        edge_schema = profile_edge_collection(edge_name)

        schema["edge_collections"][edge_name] = edge_schema

        if edge_schema["from"] and edge_schema["to"]:

            schema["relationships"].append({

                "edge": edge_name,

                "from":
                    edge_schema["from"],

                "to":
                    edge_schema["to"]
            })

    else:

        print(
            f"ATTENTION : {edge_name} n'existe pas."
        )


# =========================================================
# CRÉATION DU DOSSIER SI NÉCESSAIRE
# =========================================================

output_directory = os.path.dirname(
    os.path.abspath(OUTPUT_FILE)
)

os.makedirs(
    output_directory,
    exist_ok=True
)


# =========================================================
# SAUVEGARDE JSON
# =========================================================

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as file:

    json.dump(
        schema,
        file,
        indent=4,
        ensure_ascii=False
    )


# =========================================================
# RÉSUMÉ
# =========================================================

print("\n==============================================")
print("SCHÉMA GÉNÉRÉ AVEC SUCCÈS")
print("==============================================")

print(
    f"Document collections : "
    f"{len(schema['document_collections'])}"
)

print(
    f"Edge collections : "
    f"{len(schema['edge_collections'])}"
)

print(
    f"Relations : "
    f"{len(schema['relationships'])}"
)

print(
    f"\nFichier créé : "
    f"{os.path.abspath(OUTPUT_FILE)}"
)