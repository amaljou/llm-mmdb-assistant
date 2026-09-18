class Evaluator:

    def __init__(self, db):
        self.db = db

    def execute_query(self, query):
        try:
            cursor = self.db.aql.execute(query)
            return {
                "success": True,
                "results": list(cursor),
                "error": None
            }

        except Exception as e:
            return {
                "success": False,
                "results": None,
                "error": str(e)
            }

    def normalize_results(self, results):
        if results is None:
            return None

        return sorted(
            [repr(result) for result in results]
        )

    def compare_results(self, gold_results, generated_results):
        gold_normalized = self.normalize_results(gold_results)
        generated_normalized = self.normalize_results(generated_results)

        return gold_normalized == generated_normalized

    def evaluate(self, gold_aql, generated_aql):
        gold_execution = self.execute_query(gold_aql)
        generated_execution = self.execute_query(generated_aql)

        if not gold_execution["success"]:
            return {
                "functional_correct": False,
                "gold_executed": False,
                "generated_executed": generated_execution["success"],
                "gold_result_count": None,
                "generated_result_count": (
                    len(generated_execution["results"])
                    if generated_execution["results"] is not None
                    else None
                ),
                "error": gold_execution["error"]
            }

        if not generated_execution["success"]:
            return {
                "functional_correct": False,
                "gold_executed": True,
                "generated_executed": False,
                "gold_result_count": len(gold_execution["results"]),
                "generated_result_count": None,
                "error": generated_execution["error"]
            }

        functional_correct = self.compare_results(
            gold_execution["results"],
            generated_execution["results"]
        )

        return {
            "functional_correct": functional_correct,
            "gold_executed": True,
            "generated_executed": True,
            "gold_result_count": len(gold_execution["results"]),
            "generated_result_count": len(generated_execution["results"]),
            "error": None
        }