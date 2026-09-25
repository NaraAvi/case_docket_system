"""Codified statutory corpus consumed by the Objective Deterministic Decision Engine.

This module is *pure data*: no I/O, no Flask, no database. Everything the
decision engine (``app.modules.decision_engine``) decides is a function of the
tables below plus the inputs it is handed, which is what makes every outcome
reproducible and auditable.

Provenance
----------
Each table cites the instrument it codifies through ``legal_reference_id``
(see ``LegalReferenceService``). The IPID Act 1 of 2011 section 28(1)
categories and the PRECCA section 34 reporting duty are codified from the
statute text. The SAPS Discipline Regulations 2016 misconduct schedule and
sanction matrix, and the National Instruction 3/2011 windows, are a *prototype
codification* as specified by the project roadmap: they must be checked against
the gazetted instruments before any production use. The corpus is controlled
by the release process (see ``RegulatoryRuleService.update_rule``) and is never
editable at runtime.
"""

from __future__ import annotations

CORPUS_VERSION = 2
ENGINE_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Police-actor vocabulary
# ---------------------------------------------------------------------------
# IPID's jurisdiction is conduct *by members of the police*. An offence keyword
# on its own ("someone assaulted me") is a crime report, not an s28 referral,
# so every category below (unless it says otherwise) additionally requires a
# police actor in the same sentence -- or in the immediately preceding
# sentence when the offence sentence refers back to them with a pronoun.
POLICE_ACTOR_PATTERN = (
    r"\b(?:police(?:man|woman|men|women)?|police\s+officers?|cops?|constables?|"
    r"sergeants?|captains?|colonels?|lieutenants?|brigadiers?|generals?|detectives?|"
    r"saps|officers?|inspectors?|warrant\s+officers?|station\s+commanders?|"
    r"station\s+commissioners?|members?\s+of\s+the\s+(?:police|saps|service)|"
    r"metro\s+police|traffic\s+officers?|flying\s+squad|tactical\s+response\s+team|"
    r"public\s+order\s+police|task\s+force)\b"
)

PRONOUN_PATTERN = r"\b(?:he|she|they|him|her|them|his|their|the\s+(?:officer|constable|detective|sergeant|member))\b"

# A match preceded (within four words) by one of these is a denial or a
# hypothetical, not an allegation: "he did NOT demand a bribe".
NEGATORS = frozenset(
    {
        "no", "not", "never", "didn't", "didnt", "wasn't", "wasnt", "isn't", "isnt",
        "hasn't", "hasnt", "haven't", "havent", "without", "denies", "denied", "deny",
        "nothing", "neither", "nor", "if", "whether", "cannot", "can't", "cant",
    }
)
NEGATION_WINDOW_WORDS = 4

# ---------------------------------------------------------------------------
# IPID Act 1 of 2011, section 28(1) -- mandatory investigation categories
# ---------------------------------------------------------------------------
# `patterns`         : regexes (case-insensitive) that indicate the offence.
# `requires_police_actor`: see POLICE_ACTOR_PATTERN above.
# `context_patterns` : optional regexes that must ALSO appear in the same
#                      sentence (used by s28(1)(e), rape *in custody*).
# `standalone`       : the pattern already implies police involvement
#                      (e.g. "died in police custody") so no actor is needed.
# `infraction_type`  : key into MISCONDUCT_SCHEDULE (the tier-3 conduct the
#                      category maps to when an implicated officer is upheld).
IPID_28_V2011 = {
    "IPID.S28.DEATH_IN_CUSTODY": {
        "subsection": "28(1)(a)",
        "title": "Death in police custody",
        "legal_reference_id": "RSA-IPID-2011",
        "patterns": [
            r"\b(?:died|dies|death|dead|killed|hanged|found\s+dead)\b[^.!?\n]{0,50}\b(?:in|inside|at|while\s+in)\s+(?:the\s+)?(?:police\s+)?(?:custody|cells?|holding\s+cells?|police\s+station|police\s+van)\b",
            r"\b(?:custodial|in-custody)\s+death\b",
            r"\bdeath\s+in\s+(?:police\s+)?custody\b",
        ],
        "requires_police_actor": False,
        "standalone": True,
        "infraction_type": "DEATH_IN_CUSTODY",
        "auto_detect": True,
    },
    "IPID.S28.DEATH_BY_POLICE_ACTION": {
        "subsection": "28(1)(b)",
        "title": "Death as a result of police action",
        "legal_reference_id": "RSA-IPID-2011",
        "patterns": [
            r"\b(?:killed|kills|murdered|shot\s+dead|beaten\s+to\s+death|fatally\s+(?:shot|injured|wounded|stabbed))\b",
            r"\b(?:died|dies)\s+(?:after|because|as\s+a\s+result)\b",
            r"\b(?:caused|causing|resulting\s+in)\s+(?:the\s+|his\s+|her\s+|their\s+)?death\b",
            r"\bdeath\s+of\b",
        ],
        "requires_police_actor": True,
        "infraction_type": "DEATH_BY_POLICE_ACTION",
        "auto_detect": True,
    },
    "IPID.S28.FIREARM_DISCHARGE": {
        "subsection": "28(1)(c)",
        "title": "Discharge of an official firearm by a police officer",
        "legal_reference_id": "RSA-IPID-2011",
        "patterns": [
            r"\bdischarg(?:e|ed|es|ing)\b[^.!?\n]{0,40}\b(?:firearm|gun|pistol|rifle|shotgun|revolver|weapon|service\s+weapon)\b",
            r"\b(?:firearm|gun|pistol|rifle|shotgun|revolver|weapon|service\s+weapon)\b[^.!?\n]{0,40}\bdischarg(?:e|ed|es|ing)\b",
            r"\b(?:shot|shoot|shoots|shooting|gunshots?|gunfire|opened\s+fire)\b",
            r"\bfir(?:ed|es|ing)\s+(?:a\s+|his\s+|her\s+|their\s+|the\s+)?(?:gun|firearm|pistol|rifle|weapon|shots?|rounds?|bullets?)\b",
        ],
        "requires_police_actor": True,
        "infraction_type": "UNLAWFUL_FIREARM_DISCHARGE",
        "auto_detect": True,
    },
    "IPID.S28.RAPE_BY_POLICE": {
        "subsection": "28(1)(d)",
        "title": "Rape by a police officer, on or off duty",
        "legal_reference_id": "RSA-IPID-2011",
        "patterns": [
            r"\b(?:rape[ds]?|raping|sexual(?:ly)?\s+(?:assault(?:ed|s|ing)?|violen\w+|abus\w+))\b",
        ],
        "requires_police_actor": True,
        "infraction_type": "RAPE_OR_SEXUAL_VIOLENCE",
        "auto_detect": True,
    },
    "IPID.S28.RAPE_IN_CUSTODY": {
        "subsection": "28(1)(e)",
        "title": "Rape of a person while in police custody",
        "legal_reference_id": "RSA-IPID-2011",
        "patterns": [
            r"\b(?:rape[ds]?|raping|sexual(?:ly)?\s+(?:assault(?:ed|s|ing)?|violen\w+|abus\w+))\b",
        ],
        "context_patterns": [
            r"\b(?:custody|in\s+(?:the\s+)?cells?|holding\s+cells?|police\s+station|police\s+van|detained|detention)\b",
        ],
        "requires_police_actor": False,
        "infraction_type": "RAPE_OR_SEXUAL_VIOLENCE",
        "auto_detect": True,
    },
    "IPID.S28.TORTURE_OR_ASSAULT": {
        "subsection": "28(1)(f)",
        "title": "Torture or assault by a police officer in the execution of duty",
        "legal_reference_id": "RSA-IPID-2011",
        "patterns": [
            r"\btortur(?:e|ed|es|ing)\b",
            r"\bassault(?:ed|s|ing)?\b",
            r"\bbeat(?:en|ing|s)?\b",
            r"\b(?:punch(?:ed|es|ing)?|kick(?:ed|s|ing)?|slap(?:ped|s|ping)?|strangl(?:e|ed|es|ing)|suffocat(?:e|ed|es|ing)|electr(?:ic|o)[\s-]?shock(?:ed|s)?|brutali[sz](?:e|ed|es|ing)|brutality)\b",
            r"\bhit\s+(?:me|him|her|them)\b",
        ],
        "requires_police_actor": True,
        "infraction_type": "ASSAULT_OR_TORTURE",
        "auto_detect": True,
    },
    "IPID.S28.CORRUPTION": {
        "subsection": "28(1)(g)",
        "title": "Corruption within the police",
        "legal_reference_id": "RSA-IPID-2011",
        "patterns": [
            r"\bbrib(?:e|es|ed|ery|ing)\b",
            r"\bcorrupt(?:ion|ed|ly)?\b",
            r"\bkick[\s-]?backs?\b",
            r"\bextort(?:ed|s|ing|ion)?\b",
            r"\b(?:demand(?:ed|s|ing)?|ask(?:ed|s|ing)?\s+for|request(?:ed|s|ing)?|solicit(?:ed|s|ing)?)\s+(?:some\s+|a\s+|the\s+)?(?:money|cash|payment|bribe|gift|favou?r)\b",
            r"\bprotection\s+money\b",
            r"\bpaid\s+(?:him|her|them|the\s+officer)\b[^.!?\n]{0,40}\b(?:to|so\s+that)\b",
        ],
        "requires_police_actor": True,
        "infraction_type": "CORRUPTION",
        "precca_s34": True,
        "auto_detect": True,
    },
    "IPID.S28.PRESCRIBED_MATTER": {
        "subsection": "28(1)(h)",
        "title": "Any other matter prescribed by the Minister in the Gazette",
        "legal_reference_id": "RSA-IPID-2011",
        "patterns": [],
        "requires_police_actor": False,
        "infraction_type": "DEFEATING_ENDS_OF_JUSTICE",
        "auto_detect": False,
    },
}

# The Amendment Act corpus is intentionally kept separate until its
# commencement date is configured. Existing callers continue to use V2011.
IPID_28_V2024 = {key: dict(value) for key, value in IPID_28_V2011.items() if key != "IPID.S28.FIREARM_DISCHARGE"}
IPID_28_V2024["IPID.S28.DEATH_BY_POLICE_ACTION"] = {
    **IPID_28_V2024["IPID.S28.DEATH_BY_POLICE_ACTION"],
    "title": "Death as a result of police or municipal police action, on or off duty",
}
IPID_28_V2024["IPID.S28.RAPE_BY_POLICE"] = {
    **IPID_28_V2024["IPID.S28.RAPE_BY_POLICE"],
    "title": "Rape by a SAPS or municipal police officer, on or off duty",
}
IPID_28_V2024["IPID.S28.TORTURE_OR_ASSAULT"] = {
    **IPID_28_V2024["IPID.S28.TORTURE_OR_ASSAULT"],
    "title": "Torture under Act 13 of 2013 or assault with intent to cause grievous bodily harm",
}
IPID_28_V2024["IPID.S28.CORRUPTION"] = {
    **IPID_28_V2024["IPID.S28.CORRUPTION"],
    "title": "Corruption within SAPS or municipal police under PRECCA",
    "legal_reference_id": "RSA-PRECCA-2004",
}
IPID_28_V2024["IPID.S28.ATTEMPTED_MURDER_FIREARM"] = {
    "subsection": "28(1)(gA)",
    "title": "Attempted murder by firearm or other weapon",
    "legal_reference_id": "RSA-IPID-2011",
    "patterns": [r"\battempt(?:ed|ing)?\s+murder\b[^.!?\n]{0,80}\b(?:firearm|gun|pistol|rifle|shotgun|revolver|weapon)\b"],
    "requires_police_actor": True,
    "infraction_type": "DEFEATING_ENDS_OF_JUSTICE",
    "auto_detect": True,
}

IPID_S16_COMMENCEMENT_DATE = None


def active_s28_table(at=None):
    """Return the s28 table in force at ``at`` without changing global state."""
    if IPID_S16_COMMENCEMENT_DATE is None:
        return IPID_28_V2011
    from datetime import UTC, datetime

    moment = at or datetime.now(UTC)
    commencement = IPID_S16_COMMENCEMENT_DATE
    if isinstance(commencement, str):
        commencement = datetime.fromisoformat(commencement.replace("Z", "+00:00"))
    if commencement.tzinfo is None:
        commencement = commencement.replace(tzinfo=UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return IPID_28_V2024 if moment >= commencement else IPID_28_V2011


S28_CATEGORIES = IPID_28_V2011

# Human-readable statutory basis strings stamped on every automatic referral.
IPID_ACT_CITATION = "IPID Act 1 of 2011"
IPID_SECTION_28_BASIS = f"{IPID_ACT_CITATION}, section 28(1)"

# ---------------------------------------------------------------------------
# SAPS National Instruction 3/2011 -- service windows
# ---------------------------------------------------------------------------
SLA_THRESHOLDS = {
    "registration_hours": 72,   # submission -> constable registration
    "attendance_hours": 72,     # assignment/registration -> investigation opened
    "at_risk_ratio": 0.75,      # >= 75 % of the window elapsed => AT_RISK
    "minor_overdue_hours": 24,  # overdue by < 24 h => tier-1 delay, else tier-2
    "legal_reference_id": "RSA-SAPS-NI-3-2011",
}

# ---------------------------------------------------------------------------
# SAPS Discipline Regulations 2016 -- misconduct schedule (prototype codification)
# ---------------------------------------------------------------------------
MISCONDUCT_SCHEDULE = {
    # Tier 1: minor / procedural
    "SLA_BREACH_MINOR": {"tier": 1, "description": "Docket window overrun by less than 24 hours."},
    "INCOMPLETE_RECORD_KEEPING": {"tier": 1, "description": "Incomplete or late docket record keeping."},
    "UNBECOMING_CONDUCT": {"tier": 1, "description": "Conduct unbecoming of a member, without aggravation."},
    "GENERAL_MISCONDUCT": {"tier": 1, "description": "Other non-specific breach of a disciplinary rule."},
    # Tier 2: serious
    "SLA_BREACH_SERIOUS": {"tier": 2, "description": "Docket window overrun by 24 hours or more."},
    "UNLAWFUL_DELAY": {"tier": 2, "description": "Unlawful delay in attending to a docket."},
    "REFUSAL_TO_REGISTER": {"tier": 2, "description": "Refusal or failure to register a lawful docket."},
    "NEGLECT_OF_DUTY": {"tier": 2, "description": "Neglect of duty in the handling of a docket."},
    "MALPRACTICE": {"tier": 2, "description": "Suspected malpractice in the handling of a docket."},
    "UNAUTHORISED_DISCLOSURE": {"tier": 2, "description": "Unauthorised disclosure of docket information."},
    "CONFLICT_OF_INTEREST_BREACH": {"tier": 2, "description": "Handling a docket despite a disqualifying conflict of interest."},
    # Tier 3: gross misconduct / criminal conduct (IPID s28 matters)
    "CORRUPTION": {"tier": 3, "description": "Corruption (PRECCA / IPID Act s28(1)(g))."},
    "ASSAULT_OR_TORTURE": {"tier": 3, "description": "Assault or torture (IPID Act s28(1)(f))."},
    "UNLAWFUL_FIREARM_DISCHARGE": {"tier": 3, "description": "Unlawful discharge of an official firearm (IPID Act s28(1)(c))."},
    "DEATH_IN_CUSTODY": {"tier": 3, "description": "Death in police custody (IPID Act s28(1)(a))."},
    "DEATH_BY_POLICE_ACTION": {"tier": 3, "description": "Death as a result of police action (IPID Act s28(1)(b))."},
    "RAPE_OR_SEXUAL_VIOLENCE": {"tier": 3, "description": "Rape or sexual violence (IPID Act s28(1)(d)/(e))."},
    "EVIDENCE_TAMPERING": {"tier": 3, "description": "Tampering with, destroying or falsifying evidence."},
    "DEFEATING_ENDS_OF_JUSTICE": {"tier": 3, "description": "Conduct defeating or obstructing the ends of justice."},
}
MISCONDUCT_LEGAL_REFERENCE_ID = "RSA-SAPS-DISCIPLINE-2016"

# How an IPID escalation category maps onto the schedule when it is upheld and
# the evidence context does not name a more specific infraction.
ESCALATION_CATEGORY_TO_INFRACTION = {
    "REFUSAL_TO_REGISTER": "REFUSAL_TO_REGISTER",
    "UNLAWFUL_DELAY": "UNLAWFUL_DELAY",
    "OFFICER_CONDUCT": "UNBECOMING_CONDUCT",
    "SUSPECTED_MALPRACTICE": "MALPRACTICE",
    "OTHER": "GENERAL_MISCONDUCT",
}

# Objective aggravators. Each may only *raise* the tier, and only by the rule
# stated -- never by an officer's rank, name or any discretionary field.
AGGRAVATORS = {
    "evidence_tampering": "Evidence integrity failure detected: infraction becomes EVIDENCE_TAMPERING (tier 3).",
    "statutory_referral": "The matter falls in an IPID Act s28(1) category: tier 3 floor.",
    "concealment": "Concealment or obstruction of the matter: tier raised by one (max 3).",
}
MAX_TIER = 3

# ---------------------------------------------------------------------------
# Sanction matrix
# ---------------------------------------------------------------------------
# tier -> ordered sanctions by number of qualifying prior determinations
# (index = prior count, capped at the last entry).
SANCTION_MATRIX = {
    1: ["WARNING", "FINAL_WARNING", "SUSPENSION"],
    2: ["FINAL_WARNING", "SUSPENSION", "DISMISSAL"],
    3: ["DISMISSAL"],
}
SANCTION_DESCRIPTIONS = {
    "WARNING": "Warning recorded on the officer's disciplinary file.",
    "FINAL_WARNING": "Final warning: any further qualifying misconduct escalates the sanction.",
    "SUSPENSION": "Suspension from operational duty for the period set by the disciplinary hearing.",
    "DISMISSAL": "Dismissal from the Service.",
}
SANCTION_SEVERITY = {"WARNING": 1, "FINAL_WARNING": 2, "SUSPENSION": 3, "DISMISSAL": 4}

# A prior determination only counts towards progression if it is at least as
# serious as the current tier and was made within this rolling window.
PRIOR_HISTORY_WINDOW_MONTHS = 24

# The engine determines the *minimum mandatory* sanction; the disciplinary
# hearing keeps its PAJA procedural-fairness role. A hearing that departs from
# the determined sanction must record a justification (see DisciplinaryCase).
DEVIATION_REQUIRES_JUSTIFICATION = True
