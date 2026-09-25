"""Authoritative legal reference catalog for regulated case workflow controls."""

from __future__ import annotations


class LegalReferenceService:
    """Controlled legal-reference catalog used by system rules.

    This boundary stores authoritative South African legislation references. It is
    not an admin UI and no runtime user may mutate the corpus through APIs.
    """

    LEGAL_REFERENCES = {
        "RSA-CONSTITUTION-1996": {
            "legislation_id": "RSA-CONSTITUTION-1996",
            "act_name": "Constitution of the Republic of South Africa",
            "act_number": "Constitution",
            "year": 1996,
            "section": "Section 33",
            "subsection": None,
            "title": "Just administrative action",
            "description": "Administrative action must be lawful, reasonable, and procedurally fair.",
            "source_reference": "Constitution of the Republic of South Africa, 1996",
            "effective_from": "1996-02-04",
            "effective_to": None,
            "version": "1996",
            "status": "ACTIVE",
            "source_type": "official_legislation",
            "source_provenance": "South African Government / Constitution",
        },
        "RSA-CPA-1977": {
            "legislation_id": "RSA-CPA-1977",
            "act_name": "Criminal Procedure Act",
            "act_number": "51",
            "year": 1977,
            "section": "Section 2 and related procedural safeguards",
            "subsection": None,
            "title": "Procedural fairness in criminal process",
            "description": "Procedural authority and lawful process for criminal matters.",
            "source_reference": "Criminal Procedure Act 51 of 1977",
            "effective_from": "1977-01-01",
            "effective_to": None,
            "version": "1977",
            "status": "ACTIVE",
            "source_type": "official_legislation",
            "source_provenance": "South African Government / Department of Justice",
        },
        "RSA-SAPS-1995": {
            "legislation_id": "RSA-SAPS-1995",
            "act_name": "South African Police Service Act",
            "act_number": "68",
            "year": 1995,
            "section": "Section 13 and role mandate",
            "subsection": None,
            "title": "Police mandate and role boundaries",
            "description": "Police powers and operational role boundaries.",
            "source_reference": "South African Police Service Act 68 of 1995",
            "effective_from": "1995-10-01",
            "effective_to": None,
            "version": "1995",
            "status": "ACTIVE",
            "source_type": "official_legislation",
            "source_provenance": "South African Government / Police legislation",
        },
        "RSA-PACA-2004": {
            "legislation_id": "RSA-PACA-2004",
            "act_name": "Prevention and Combating of Corrupt Activities Act",
            "act_number": "12",
            "year": 2004,
            "section": "Sections 4 to 12",
            "subsection": None,
            "title": "Anti-corruption and integrity controls",
            "description": "Deters corruption and requires integrity-sensitive workflow controls.",
            "source_reference": "Prevention and Combating of Corrupt Activities Act 12 of 2004",
            "effective_from": "2004-01-01",
            "effective_to": None,
            "version": "2004",
            "status": "ACTIVE",
            "source_type": "official_legislation",
            "source_provenance": "South African Government / Anti-corruption legislation",
        },
        "RSA-POPIA-2013": {
            "legislation_id": "RSA-POPIA-2013",
            "act_name": "Protection of Personal Information Act",
            "act_number": "4",
            "year": 2013,
            "section": "Section 1 and privacy-by-design principles",
            "subsection": None,
            "title": "Personal information protection",
            "description": "Protects personal information and limits unfettered access to personal records.",
            "source_reference": "Protection of Personal Information Act 4 of 2013",
            "effective_from": "2020-07-01",
            "effective_to": None,
            "version": "2013",
            "status": "ACTIVE",
            "source_type": "official_legislation",
            "source_provenance": "South African Government / Information protection legislation",
        },
        "RSA-PAJA-2000": {
            "legislation_id": "RSA-PAJA-2000",
            "act_name": "Promotion of Administrative Justice Act",
            "act_number": "3",
            "year": 2000,
            "section": "Section 1 to 3 and procedural fairness principles",
            "subsection": None,
            "title": "Procedural fairness in administrative action",
            "description": "Requires fair and reviewable administrative action.",
            "source_reference": "Promotion of Administrative Justice Act 3 of 2000",
            "effective_from": "2000-01-01",
            "effective_to": None,
            "version": "2000",
            "status": "ACTIVE",
            "source_type": "official_legislation",
            "source_provenance": "South African Government / Administrative justice legislation",
        },
    }

    def list_references(self):
        return [dict(item) for item in self.LEGAL_REFERENCES.values()]

    def get_reference(self, legislation_id):
        ref = self.LEGAL_REFERENCES.get(str(legislation_id))
        if ref is None:
            return None
        return dict(ref)
