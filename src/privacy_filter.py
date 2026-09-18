import re


class PrivacyFilter:

    SENSITIVE_FIELDS = {
        "full_address",
        "latitude",
        "longitude",
        "text"
    }

    def __init__(self, sensitive_fields=None):
        if sensitive_fields is not None:
            self.sensitive_fields = set(sensitive_fields)
        else:
            self.sensitive_fields = self.SENSITIVE_FIELDS

    def detect_sensitive_fields(self, query):
        detected = []

        for field in self.sensitive_fields:
            pattern = rf"\b{re.escape(field)}\b"

            if re.search(pattern, query, flags=re.IGNORECASE):
                detected.append(field)

        return sorted(detected)

    def check(self, query):
        detected_fields = self.detect_sensitive_fields(query)

        if detected_fields:
            return {
                "allowed": False,
                "sensitive_fields": detected_fields,
                "reason": "Sensitive field(s) detected."
            }

        return {
            "allowed": True,
            "sensitive_fields": [],
            "reason": None
        }