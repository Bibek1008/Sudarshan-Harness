import json
def load_config(text):
    value = json.loads(text)
    if not isinstance(value, dict) or not isinstance(value.get("name"), str) or not value["name"].strip():
        raise ValueError("name required")
    return {"name": value["name"]}
