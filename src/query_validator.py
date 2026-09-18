import re
import json


class QueryValidator:

    FORBIDDEN_OPERATIONS = {
        "INSERT",
        "UPDATE",
        "REMOVE",
        "REPLACE",
        "UPSERT"
    }

    SYSTEM_FIELDS = {
        "_id",
        "_key",
        "_rev",
        "_from",
        "_to"
    }

    def __init__(self, schema_path):
        with open(schema_path, "r", encoding="utf-8") as f:
            self.schema = json.load(f)

        self.document_collections = set(
            self.schema.get("document_collections", {}).keys()
        )

        self.edge_collections = set(
            self.schema.get("edge_collections", {}).keys()
        )

        self.allowed_collections = (
            self.document_collections |
            self.edge_collections
        )

        # Champs autorisés pour chaque collection
        self.collection_fields = {}

        for collection, info in self.schema.get(
            "document_collections", {}
        ).items():

            fields = set(
                info.get("fields", {}).keys()
            )

            fields.update(self.SYSTEM_FIELDS)

            self.collection_fields[collection] = fields

        for collection, info in self.schema.get(
            "edge_collections", {}
        ).items():

            fields = set(
                info.get("fields", {}).keys()
            )

            fields.update(self.SYSTEM_FIELDS)

            self.collection_fields[collection] = fields

    # =====================================================
    # OPERATIONS INTERDITES
    # =====================================================

    def check_forbidden_operations(self, query):

        query_upper = query.upper()

        detected = []

        for operation in self.FORBIDDEN_OPERATIONS:

            if re.search(
                rf"\b{operation}\b",
                query_upper
            ):
                detected.append(operation)

        return sorted(detected)

    # =====================================================
    # COLLECTIONS + ALIAS
    # =====================================================

    def extract_aliases_and_collections(self, query):

        aliases = {}
        used_collections = set()

        # Exemple :
        # FOR b IN Businesses

        standard_for_matches = re.findall(
            r"\bFOR\s+([A-Za-z_][A-Za-z0-9_]*)"
            r"\s+IN\s+([A-Za-z_][A-Za-z0-9_]*)",
            query,
            flags=re.IGNORECASE
        )

        for alias, collection in standard_for_matches:

            used_collections.add(collection)

            if collection in self.allowed_collections:
                aliases[alias] = collection

        # Exemple :
        # FOR c IN 1..1 OUTBOUND b BusinessCategory

        traversal_matches = re.findall(
            r"\bFOR\s+([A-Za-z_][A-Za-z0-9_]*)"
            r"\s+IN\s+\d+\.\.\d+\s+"
            r"(OUTBOUND|INBOUND|ANY)\s+"
            r"([A-Za-z_][A-Za-z0-9_\.]*)\s+"
            r"([A-Za-z_][A-Za-z0-9_]*)",
            query,
            flags=re.IGNORECASE
        )

        for (
            alias,
            direction,
            start_vertex,
            edge_collection
        ) in traversal_matches:

            used_collections.add(edge_collection)

            if edge_collection not in self.edge_collections:
                continue

            edge_info = self.schema[
                "edge_collections"
            ].get(edge_collection, {})

            from_collection = edge_info.get("from")
            to_collection = edge_info.get("to")

            direction = direction.upper()

            if direction == "OUTBOUND":
                target_collection = to_collection

            elif direction == "INBOUND":
                target_collection = from_collection

            else:
                target_collection = None

            if (
                target_collection
                and target_collection
                in self.allowed_collections
            ):
                aliases[alias] = target_collection

        return aliases, used_collections

    def check_collections(self, query):

        aliases, used_collections = (
            self.extract_aliases_and_collections(query)
        )

        invalid_collections = sorted([
            collection
            for collection in used_collections
            if collection not in self.allowed_collections
        ])

        return (
            aliases,
            used_collections,
            invalid_collections
        )

    # =====================================================
    # ATTRIBUTS
    # =====================================================

    def check_attributes(self, query, aliases):

        invalid_attributes = []

        # Cherche :
        # b.city
        # c.category_name
        # doc.City
        attribute_matches = re.findall(
            r"\b([A-Za-z_][A-Za-z0-9_]*)"
            r"\.([A-Za-z_][A-Za-z0-9_]*)\b",
            query
        )

        for alias, attribute in attribute_matches:

            if alias not in aliases:
                continue

            collection = aliases[alias]

            allowed_fields = self.collection_fields.get(
                collection,
                set()
            )

            if attribute not in allowed_fields:

                invalid_attributes.append({
                    "alias": alias,
                    "collection": collection,
                    "attribute": attribute
                })

        return invalid_attributes

    # =====================================================
    # REQUETES POTENTIELLEMENT COUTEUSES
    # =====================================================

    def check_cost(self, query):

        warnings = []

        # Traversée de profondeur élevée
        traversals = re.findall(
            r"\bIN\s+(\d+)\.\.(\d+)\s+"
            r"(?:OUTBOUND|INBOUND|ANY)",
            query,
            flags=re.IGNORECASE
        )

        for min_depth, max_depth in traversals:

            if int(max_depth) > 3:

                warnings.append(
                    "Traversal depth greater than 3 "
                    "may be costly."
                )

        # LIMIT recommandé pour les requêtes retournant
        # potentiellement beaucoup de documents
        has_for = bool(
            re.search(
                r"\bFOR\b",
                query,
                flags=re.IGNORECASE
            )
        )

        has_limit = bool(
            re.search(
                r"\bLIMIT\b",
                query,
                flags=re.IGNORECASE
            )
        )

        # Les requêtes d'agrégation comme RETURN LENGTH(...)
        # ne nécessitent pas forcément de LIMIT.
        aggregate_query = bool(
            re.search(
                r"\bRETURN\s+"
                r"(LENGTH|COUNT|SUM|AVG|MIN|MAX)\s*\(",
                query,
                flags=re.IGNORECASE
            )
        )

        if (
            has_for
            and not has_limit
            and not aggregate_query
        ):
            warnings.append(
                "No LIMIT detected. A LIMIT is recommended "
                "for queries that may return many documents."
            )

        return warnings

    # =====================================================
    # VALIDATION COMPLETE
    # =====================================================

    def validate(self, query):

        errors = []
        warnings = []

        if not query or not query.strip():

            return {
                "valid": False,
                "errors": ["Empty AQL query."],
                "warnings": [],
                "used_collections": [],
                "invalid_attributes": []
            }

        # 1. Opérations dangereuses
        forbidden = self.check_forbidden_operations(
            query
        )

        if forbidden:

            errors.append(
                "Forbidden operation(s): "
                + ", ".join(forbidden)
            )

        # 2. Collections
        (
            aliases,
            used_collections,
            invalid_collections
        ) = self.check_collections(query)

        if invalid_collections:

            errors.append(
                "Unknown collection(s): "
                + ", ".join(invalid_collections)
            )

        # 3. Attributs
        invalid_attributes = self.check_attributes(
            query,
            aliases
        )

        for item in invalid_attributes:

            errors.append(
                f"Unknown attribute "
                f"'{item['attribute']}' "
                f"in collection "
                f"'{item['collection']}'."
            )

        # 4. Coût
        warnings.extend(
            self.check_cost(query)
        )

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "used_collections": sorted(
                used_collections
            ),
            "invalid_attributes": invalid_attributes
        }