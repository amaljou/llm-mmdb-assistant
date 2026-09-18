import time
import re
import requests


class QueryGenerator:

    def __init__(
        self,
        model_name="gemma3:4b",
        ollama_url="http://localhost:11434/api/generate"
    ):
        self.model_name = model_name
        self.ollama_url = ollama_url

    # =====================================================
    # NETTOYAGE SORTIE LLM
    # =====================================================

    def clean_aql_output(self, text):
        """
        Nettoie la sortie du LLM et conserve uniquement la requête AQL.
        """

        if not text:
            return ""

        text = text.strip()

        # 1. Extraire un éventuel bloc Markdown ```aql ... ```
        code_block = re.search(
            r"```(?:aql|AQL)?\s*(.*?)```",
            text,
            flags=re.DOTALL
        )

        if code_block:
            text = code_block.group(1).strip()

        # 2. Supprimer un éventuel préfixe "AQL:" / "aql:"
        text = re.sub(
            r"^\s*AQL\s*:?\s*",
            "",
            text,
            flags=re.IGNORECASE
        )

        # 3. Couper les explications ajoutées après la requête
        explanation_patterns = [
            r"\n\s*This query\b",
            r"\n\s*This AQL\b",
            r"\n\s*The query\b",
            r"\n\s*Explanation\s*:?",
            r"\n\s*Cette requête\b",
            r"\n\s*La requête\b",
        ]

        cut_positions = []

        for pattern in explanation_patterns:
            match = re.search(
                pattern,
                text,
                flags=re.IGNORECASE
            )

            if match:
                cut_positions.append(match.start())

        if cut_positions:
            text = text[:min(cut_positions)]

        # 4. Retirer d'éventuelles balises Markdown restantes
        text = text.replace("```aql", "")
        text = text.replace("```AQL", "")
        text = text.replace("```", "")

        return text.strip()

    # =====================================================
    # APPEL OLLAMA
    # =====================================================

    def generate(self, prompt):

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False
        }

        start_time = time.time()

        response = requests.post(
            self.ollama_url,
            json=payload,
            timeout=900
        )

        response.raise_for_status()

        generation_time = time.time() - start_time

        result = response.json()

        generated_aql = self.clean_aql_output(
            result["response"]
        )

        return {
            "aql": generated_aql,
            "generation_time": generation_time,
            "model": self.model_name
        }

    # =====================================================
    # PROMPT CORRECTION LLM
    # =====================================================

    def build_correction_prompt(
        self,
        question,
        invalid_aql,
        validation_errors,
        schema_context,
        examples_context
    ):

        errors_text = "\n".join(
            f"- {error}"
            for error in validation_errors
        )

        return f"""
You are an expert in ArangoDB AQL.

Generate a NEW correct AQL query for the original
natural language question.

Do NOT simply repair the syntax of the previous query.

Reconstruct the query from:
1. the original question,
2. the available schema,
3. the retrieved examples,
4. the validation errors.

ORIGINAL QUESTION:
{question}

PREVIOUS INCORRECT AQL:
{invalid_aql}

VALIDATION ERRORS:
{errors_text}

AVAILABLE SCHEMA:
{schema_context}

RETRIEVED EXAMPLES:
{examples_context}

IMPORTANT RULES:

- Preserve ALL semantic constraints from the original question.
- Identify the correct document collections.
- Identify the correct attributes.
- Identify the correct graph relations.
- Use retrieved examples as structural guidance.
- Do not blindly copy an example.
- Return ONLY the corrected AQL query.
- Do not provide explanations.
- Do not use SQL.
- Do not invent collections.
- Do not invent attributes.
- Do not invent relations.
- Respect names exactly.
- Do not use INSERT, UPDATE, REMOVE, REPLACE or UPSERT.

CORRECTED AQL:
""".strip()

    # =====================================================
    # CORRECTION PAR LLM
    # =====================================================

    def correct_invalid_query(
        self,
        question,
        invalid_aql,
        validation,
        schema_context,
        examples_context
    ):

        correction_prompt = self.build_correction_prompt(
            question=question,
            invalid_aql=invalid_aql,
            validation_errors=validation["errors"],
            schema_context=schema_context,
            examples_context=examples_context
        )

        return self.generate(
            correction_prompt
        )

    # =====================================================
    # REPARATION : CASSE DES ATTRIBUTS
    # =====================================================

    def repair_attribute_case(
        self,
        query,
        validator
    ):

        repaired_query = query

        aliases, _, _ = validator.check_collections(
            query
        )

        attribute_matches = re.findall(
            r"\b([A-Za-z_][A-Za-z0-9_]*)"
            r"\.([A-Za-z_][A-Za-z0-9_]*)\b",
            query
        )

        for alias, attribute in attribute_matches:

            if alias not in aliases:
                continue

            collection = aliases[alias]

            allowed_fields = (
                validator.collection_fields.get(
                    collection,
                    set()
                )
            )

            if attribute in allowed_fields:
                continue

            # Recherche du même attribut avec casse différente
            matching_field = None

            for field in allowed_fields:

                if field.lower() == attribute.lower():
                    matching_field = field
                    break

            if matching_field:

                repaired_query = re.sub(
                    rf"\b{re.escape(alias)}"
                    rf"\.{re.escape(attribute)}\b",
                    f"{alias}.{matching_field}",
                    repaired_query
                )

        return repaired_query

    # =====================================================
    # DETECTION QUESTION DE COMPTAGE
    # =====================================================

    def is_count_question(self, question):

        question_lower = question.lower()

        count_patterns = [
            "how many",
            "number of",
            "find the number of",
            "count "
        ]

        return any(
            pattern in question_lower
            for pattern in count_patterns
        )

    # =====================================================
    # EXTRACTION SIMPLE DE LA VILLE
    # =====================================================

    def extract_location_after_in(
        self,
        question
    ):

        match = re.search(
            r"\bin\s+([A-Za-z][A-Za-z\s\-']*)[?.!]*$",
            question.strip(),
            flags=re.IGNORECASE
        )

        if not match:
            return None

        location = match.group(1).strip()

        return location

    # =====================================================
    # EXTRACTION DE L'ENTITE RECHERCHEE
    # =====================================================

    def extract_count_entity(
        self,
        question
    ):

        q = question.strip()

        patterns = [
            r"find\s+the\s+number\s+of\s+(.+?)\s+in\s+",
            r"how\s+many\s+(.+?)\s+are\s+there\s+in\s+",
            r"how\s+many\s+(.+?)\s+in\s+",
            r"number\s+of\s+(.+?)\s+in\s+"
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                q,
                flags=re.IGNORECASE
            )

            if match:

                entity = match.group(1).strip()

                return entity

        return None

    # =====================================================
    # NORMALISATION NOM DE CATEGORIE
    # =====================================================

    def normalize_category_name(
        self,
        entity
    ):

        if not entity:
            return None

        # Exemple :
        # preschools -> Preschools
        # escape games -> Escape Games
        words = entity.split()

        normalized = " ".join(
            word.capitalize()
            for word in words
        )

        return normalized

    # =====================================================
    # REPARATION GUIDEE PAR LE SCHEMA
    # =====================================================

    def schema_guided_repair(
        self,
        question,
        query,
        validator
    ):

        # ---------------------------------------------
        # 1. Corriger d'abord la casse des attributs
        # ---------------------------------------------

        repaired_query = self.repair_attribute_case(
            query,
            validator
        )

        # ---------------------------------------------
        # 2. Vérifier si le cas peut être reconstruit
        # ---------------------------------------------

        if not self.is_count_question(question):

            return {
                "aql": repaired_query,
                "applied": repaired_query != query,
                "strategy": (
                    "attribute_case"
                    if repaired_query != query
                    else None
                )
            }

        city = self.extract_location_after_in(
            question
        )

        entity = self.extract_count_entity(
            question
        )

        category_name = self.normalize_category_name(
            entity
        )

        if not city or not category_name:

            return {
                "aql": repaired_query,
                "applied": repaired_query != query,
                "strategy": (
                    "attribute_case"
                    if repaired_query != query
                    else None
                )
            }

        # ---------------------------------------------
        # 3. Vérifier que le schéma permet ce parcours
        # ---------------------------------------------

        required_collections = {
            "Businesses",
            "Categories"
        }

        if not required_collections.issubset(
            validator.document_collections
        ):

            return {
                "aql": repaired_query,
                "applied": repaired_query != query,
                "strategy": None
            }

        if "BusinessCategory" not in validator.edge_collections:

            return {
                "aql": repaired_query,
                "applied": repaired_query != query,
                "strategy": None
            }

        business_fields = (
            validator.collection_fields.get(
                "Businesses",
                set()
            )
        )

        category_fields = (
            validator.collection_fields.get(
                "Categories",
                set()
            )
        )

        if (
            "city" not in business_fields
            or "category_name" not in category_fields
        ):

            return {
                "aql": repaired_query,
                "applied": repaired_query != query,
                "strategy": None
            }

        # ---------------------------------------------
        # 4. Construire une AQL guidée par le schéma
        # ---------------------------------------------

        schema_repaired_aql = f"""
LET matching_businesses = (
    FOR b IN Businesses
        FILTER b.city == "{city}"

        FOR c IN 1..1 OUTBOUND b BusinessCategory
            FILTER c.category_name == "{category_name}"

            RETURN DISTINCT b._id
)

RETURN LENGTH(matching_businesses)
""".strip()

        return {
            "aql": schema_repaired_aql,
            "applied": True,
            "strategy": "schema_guided_category_count"
        }

    # =====================================================
    # PROMPT DE CORRECTION APRES ERREUR ARANGODB
    # =====================================================

    def build_execution_correction_prompt(
        self,
        question,
        invalid_aql,
        execution_error,
        schema_context,
        examples_context
    ):

        return f"""
You are an expert in ArangoDB AQL.

The following AQL query passed the local static validator,
but ArangoDB rejected it during execution.

Generate a NEW valid AQL query for the ORIGINAL QUESTION.

ORIGINAL QUESTION:
{question}

PREVIOUS AQL:
{invalid_aql}

ARANGODB ERROR:
{execution_error}

AVAILABLE SCHEMA:
{schema_context}

RETRIEVED EXAMPLES:
{examples_context}

IMPORTANT RULES:

- Preserve ONLY the semantic constraints present in the original question.
- Do not introduce conditions copied from retrieved examples unless they are required by the original question.
- Use retrieved examples only as structural guidance.
- Use valid ArangoDB AQL syntax.
- Use CONTAINS(value, search) as a function if text containment is required.
- Never write: field CONTAINS value.
- Never write: field NOT CONTAINS value.
- Do not invent collections.
- Do not invent attributes.
- Do not invent relations.
- Respect schema names exactly.
- Do not use INSERT, UPDATE, REMOVE, REPLACE or UPSERT.
- Return ONLY the corrected AQL query.
- Do not provide explanations.
- Do not use Markdown fences.

CORRECTED AQL:
""".strip()

    def correct_execution_error(
        self,
        question,
        invalid_aql,
        execution_error,
        schema_context,
        examples_context
    ):

        correction_prompt = self.build_execution_correction_prompt(
            question=question,
            invalid_aql=invalid_aql,
            execution_error=execution_error,
            schema_context=schema_context,
            examples_context=examples_context
        )

        return self.generate(correction_prompt)

    # =====================================================
    # PIPELINE COMPLET
    # =====================================================

    def generate_with_correction(
        self,
        prompt,
        question,
        validator,
        schema_context,
        examples_context,
        max_corrections=1,
        use_schema_repair=True,
        executor=None,
        privacy_filter=None,
        max_execution_corrections=1
    ):
        """
        Pipeline de génération/correction.

        Etapes :
        1. Génération LLM.
        2. Nettoyage de la sortie.
        3. Validation statique.
        4. Réparation déterministe guidée par le schéma.
        5. Correction LLM si la validation statique échoue.
        6. Contrôle de confidentialité si privacy_filter est fourni.
        7. Exécution ArangoDB si executor est fourni.
        8. Si ArangoDB retourne une erreur de syntaxe/exécution,
           renvoi de l'erreur au LLM puis nouvelle validation/exécution.

        Si executor/privacy_filter ne sont pas fournis, le comportement
        reste compatible avec les anciens appels.
        """

        # ---------------------------------------------
        # 1. GENERATION INITIALE
        # ---------------------------------------------

        generation = self.generate(prompt)

        original_aql = generation["aql"]
        current_aql = original_aql

        total_generation_time = generation["generation_time"]

        validation = validator.validate(current_aql)

        history = []

        # ---------------------------------------------
        # 2. REPARATION DETERMINISTE
        # ---------------------------------------------

        if use_schema_repair:

            schema_repair = self.schema_guided_repair(
                question=question,
                query=current_aql,
                validator=validator
            )

            if schema_repair["applied"]:

                previous_aql = current_aql
                current_aql = self.clean_aql_output(
                    schema_repair["aql"]
                )

                validation = validator.validate(current_aql)

                history.append({
                    "step": "schema_repair",
                    "strategy": schema_repair["strategy"],
                    "previous_aql": previous_aql,
                    "aql": current_aql,
                    "validation": validation
                })

        # ---------------------------------------------
        # 3. CORRECTION LLM SI VALIDATION INVALIDE
        # ---------------------------------------------

        correction_attempts = 0

        while (
            not validation["valid"]
            and correction_attempts < max_corrections
        ):

            correction_attempts += 1
            previous_aql = current_aql

            correction = self.correct_invalid_query(
                question=question,
                invalid_aql=current_aql,
                validation=validation,
                schema_context=schema_context,
                examples_context=examples_context
            )

            current_aql = self.clean_aql_output(
                correction["aql"]
            )

            total_generation_time += correction["generation_time"]

            validation = validator.validate(current_aql)

            history.append({
                "step": "llm_validation_correction",
                "attempt": correction_attempts,
                "previous_aql": previous_aql,
                "aql": current_aql,
                "validation": validation,
                "generation_time": correction["generation_time"]
            })

        # ---------------------------------------------
        # 4. CONFIDENTIALITE
        # ---------------------------------------------

        privacy = None

        if privacy_filter is not None:
            privacy = privacy_filter.check(current_aql)

            history.append({
                "step": "privacy_check",
                "aql": current_aql,
                "privacy": privacy
            })

        # ---------------------------------------------
        # 5. EXECUTION ARANGODB
        # ---------------------------------------------

        execution = None
        execution_correction_attempts = 0

        can_execute = validation["valid"]

        if privacy is not None:
            can_execute = can_execute and privacy["allowed"]

        if executor is not None and can_execute:

            execution = executor.execute(current_aql)

            history.append({
                "step": "execution",
                "attempt": 0,
                "aql": current_aql,
                "executed": execution.get("executed", False),
                "error": execution.get("error")
            })

            # -----------------------------------------
            # 6. CORRECTION APRES ERREUR ARANGODB
            # -----------------------------------------

            while (
                not execution.get("executed", False)
                and execution.get("error")
                and execution_correction_attempts
                    < max_execution_corrections
            ):

                execution_correction_attempts += 1

                previous_aql = current_aql
                previous_error = execution.get("error")

                correction = self.correct_execution_error(
                    question=question,
                    invalid_aql=current_aql,
                    execution_error=previous_error,
                    schema_context=schema_context,
                    examples_context=examples_context
                )

                current_aql = self.clean_aql_output(
                    correction["aql"]
                )

                total_generation_time += correction["generation_time"]

                # Revalider la requête corrigée
                validation = validator.validate(current_aql)

                # Recontrôler la confidentialité
                if privacy_filter is not None:
                    privacy = privacy_filter.check(current_aql)
                else:
                    privacy = None

                history.append({
                    "step": "llm_execution_correction",
                    "attempt": execution_correction_attempts,
                    "previous_aql": previous_aql,
                    "previous_error": previous_error,
                    "aql": current_aql,
                    "validation": validation,
                    "privacy": privacy,
                    "generation_time": correction[
                        "generation_time"
                    ]
                })

                can_execute = validation["valid"]

                if privacy is not None:
                    can_execute = (
                        can_execute
                        and privacy["allowed"]
                    )

                if not can_execute:
                    execution = {
                        "executed": False,
                        "results": None,
                        "error": (
                            "Corrected query blocked before execution "
                            "by validation or privacy."
                        ),
                        "validation": validation
                    }
                    break

                execution = executor.execute(current_aql)

                history.append({
                    "step": "execution",
                    "attempt": execution_correction_attempts,
                    "aql": current_aql,
                    "executed": execution.get(
                        "executed",
                        False
                    ),
                    "error": execution.get("error")
                })

        elif executor is not None and not can_execute:

            if not validation["valid"]:
                error_message = (
                    "Blocked by QueryValidator"
                )
            elif (
                privacy is not None
                and not privacy["allowed"]
            ):
                error_message = (
                    "Blocked by PrivacyFilter"
                )
            else:
                error_message = (
                    "Execution blocked"
                )

            execution = {
                "executed": False,
                "results": None,
                "error": error_message,
                "validation": validation
            }

        # ---------------------------------------------
        # 7. RESULTAT FINAL
        # ---------------------------------------------

        return {
            "original_aql": original_aql,
            "aql": current_aql,
            "valid": validation["valid"],
            "validation": validation,
            "privacy": privacy,
            "execution": execution,
            "executed": (
                execution.get("executed", False)
                if execution is not None
                else None
            ),
            "corrected": current_aql != original_aql,
            "correction_attempts": correction_attempts,
            "execution_correction_attempts": (
                execution_correction_attempts
            ),
            "history": history,
            "generation_time": total_generation_time,
            "model": self.model_name
        }
