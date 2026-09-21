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
        # --- Milestone 4: Objective Deterministic Decision Engine references ---
        "RSA-IPID-2011": {
            "legislation_id": "RSA-IPID-2011",
            "act_name": "Independent Police Investigative Directorate Act",
            "act_number": "1",
            "year": 2011,
            "section": "Section 28(1)",
            "subsection": "(a)-(h)",
            "title": "Matters the Directorate must investigate",
            "description": (
                "Deaths in police custody or as a result of police action, discharge of an official "
                "firearm, rape by or in the custody of police, torture or assault, corruption within the "
                "police, and matters prescribed by the Minister must be referred to and investigated by IPID."
            ),
            "source_reference": "Independent Police Investigative Directorate Act 1 of 2011",
            "effective_from": "2012-04-01",
            "effective_to": None,
            "version": "2011",
            "status": "ACTIVE",
            "source_type": "official_legislation",
            "source_provenance": "South African Government / Police oversight legislation",
            "verification_status": "CODIFIED_FROM_STATUTE_TEXT",
        },
        "RSA-SAPS-DISCIPLINE-2016": {
            "legislation_id": "RSA-SAPS-DISCIPLINE-2016",
            "act_name": "South African Police Service Discipline Regulations",
            "act_number": "Regulations",
            "year": 2016,
            "section": "Misconduct and sanctions",
            "subsection": None,
            "title": "Misconduct tiers and disciplinary sanctions",
            "description": "Defines categories of misconduct and the sanctions available for members of the Service.",
            "source_reference": "SAPS Discipline Regulations, 2016",
            "effective_from": "2016-01-01",
            "effective_to": None,
            "version": "2016",
            "status": "ACTIVE",
            "source_type": "official_regulation",
            "source_provenance": "South African Government / SAPS Act 68 of 1995 regulations",
            "verification_status": "PROTOTYPE_CODIFICATION",
            "verification_note": (
                "The misconduct tiers and sanction progression matrix are a prototype codification and "
                "must be confirmed against the gazetted Regulations before production use."
            ),
        },
        "RSA-SAPS-NI-3-2011": {
            "legislation_id": "RSA-SAPS-NI-3-2011",
            "act_name": "SAPS National Instruction 3 of 2011",
            "act_number": "National Instruction 3/2011",
            "year": 2011,
            "section": "Docket inspection and registration window",
            "subsection": None,
            "title": "72-hour docket registration and attendance window",
            "description": "Sets the 72-hour window within which a docket must be registered and attended to.",
            "source_reference": "SAPS National Instruction 3/2011",
            "effective_from": "2011-01-01",
            "effective_to": None,
            "version": "2011",
            "status": "ACTIVE",
            "source_type": "internal_instruction",
            "source_provenance": "South African Police Service / National Instructions",
            "verification_status": "PROTOTYPE_CODIFICATION",
            "verification_note": "Cited as specified by the project roadmap; confirm the instruction text before production use.",
        },
        "RSA-PRECCA-S34": {
            "legislation_id": "RSA-PRECCA-S34",
            "act_name": "Prevention and Combating of Corrupt Activities Act",
            "act_number": "12",
            "year": 2004,
            "section": "Section 34",
            "subsection": "(1)-(2)",
            "title": "Duty to report corrupt transactions",
            "description": (
                "A person in a position of authority who knows or ought reasonably to have known or suspected "
                "an offence of corruption must report it to a police official; failure to do so is an offence."
            ),
            "source_reference": "Prevention and Combating of Corrupt Activities Act 12 of 2004, section 34",
            "effective_from": "2004-04-27",
            "effective_to": None,
            "version": "2004",
            "status": "ACTIVE",
            "source_type": "official_legislation",
            "source_provenance": "South African Government / Anti-corruption legislation",
            "verification_status": "CODIFIED_FROM_STATUTE_TEXT",
        },
    }

    def list_references(self):
        return [dict(item) for item in self.LEGAL_REFERENCES.values()]

    def get_reference(self, legislation_id):
        ref = self.LEGAL_REFERENCES.get(str(legislation_id))
        if ref is None:
            return None
        return dict(ref)
