class QueryExecutor:

    def __init__(self, db, validator):
        self.db = db
        self.validator = validator

    def execute(self, query, bind_vars=None):
        validation = self.validator.validate(query)

        if not validation["valid"]:
            return {
                "executed": False,
                "validation": validation,
                "results": None,
                "error": "Query rejected by validator."
            }

        try:
            cursor = self.db.aql.execute(
                query,
                bind_vars=bind_vars or {}
            )

            results = list(cursor)

            return {
                "executed": True,
                "validation": validation,
                "results": results,
                "error": None
            }

        except Exception as e:
            return {
                "executed": False,
                "validation": validation,
                "results": None,
                "error": str(e)
            }