class PromptBuilder:

    @staticmethod
    def build_direct_prompt(question):
        """
        Baseline : question uniquement, sans schéma.
        """
        return f"""
You are an expert in ArangoDB AQL.

Convert the following natural language question into one valid AQL query.

Return ONLY the AQL query.
Do not provide explanations.
Do not use SQL.
Do not use INSERT, UPDATE, REMOVE or REPLACE.

Question:
{question}

AQL:
""".strip()

    @staticmethod
    def build_rag_prompt(question, schema_context, examples_context):
        """
        Prompt utilisé par le pipeline RAG.
        """
        return f"""
You are an expert in ArangoDB AQL.

Convert the following natural language question into one valid AQL query.

Use ONLY the retrieved schema information provided below.

RETRIEVED SCHEMA:
{schema_context}

RETRIEVED EXAMPLES:
{examples_context}

Return ONLY the AQL query.
Do not provide explanations.
Do not use SQL.
Do not use INSERT, UPDATE, REMOVE or REPLACE.
Do not invent collections, attributes or relations.

Question:
{question}

AQL:
""".strip()