"""Validation helpers for the citizen docket workflow."""


class RequestValidator:
    """Base validator contract for request payloads."""

    @staticmethod
    def validate(data):
        if data is None:
            raise ValueError("Input payload is required.")
        return data


class CitizenDocketValidator:
    """Validates the minimal docket payload for citizen submission."""

    @staticmethod
    def validate(payload):
        if not isinstance(payload, dict):
            raise ValueError("Docket payload must be a JSON object.")

        title = (payload.get("title") or "").strip()
        description = (payload.get("description") or "").strip()

        if not title:
            raise ValueError("Title is required.")
        if not description:
            raise ValueError("Description is required.")
        if len(title) < 3:
            raise ValueError("Title must be at least 3 characters long.")
        if len(description) < 10:
            raise ValueError("Description must be at least 10 characters long.")

        clean_payload = {
            "title": title,
            "description": description,
            "incident_date": payload.get("incident_date"),
            "location": payload.get("location"),
        }

        return clean_payload
