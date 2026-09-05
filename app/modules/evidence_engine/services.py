"""Evidence engine service layer placeholder."""


class EvidenceManagementService:
    """Boundary for evidence records, media, and geo-tagged proof."""

    def __init__(self):
        self._evidence = []

    def add_evidence(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Evidence payload must be a JSON object.")
        entry = dict(payload)
        self._evidence.append(entry)
        return entry

    def list_evidence(self):
        return [dict(item) for item in self._evidence]

    def add_recording(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Recording payload must be a JSON object.")
        record = dict(payload)
        self._evidence.append(record)
        return record
