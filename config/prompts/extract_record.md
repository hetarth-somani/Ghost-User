# Extraction Prompts for Unstructured Evidence Chunks

## Record Extraction Schema
Extract records matching this exact JSON schema:
```json
[
  {
    "system_id": "exact_system_id",
    "resource_id": "exact_resource_id",
    "data_category": "USER_PROFILE|SUPPORT_MESSAGE|ANALYTICS_PROFILE|...",
    "user_id": "user_id_if_present_or_null",
    "identifiers": {
      "email": "email_if_present",
      "phone": "phone_if_present",
      "name": "name_if_present"
    },
    "state": "PRESENT|ABSENT|REDACTED|ANONYMIZED",
    "timestamp": "ISO-8601_or_null"
  }
]
```
Do not invent any identifier, system_id, or resource_id. Return valid JSON only.
