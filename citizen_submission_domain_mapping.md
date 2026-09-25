# Citizen Protected Submission Domain Mapping

This mapping identifies the approved PDAS citizen-domain contract and confirms where the required information lives in the existing backend.

| UI field | Backend field / domain object | Provenance | Downstream use |
| --- | --- | --- | --- |
| Reporter relationship (victim / witness / on behalf / information provider / other / unknown) | `Submission.original_content.reporter_relationship` and, when derived, `Assertion` / `Claim` records describing the reporter account | `Submission.provenance` + `Assertion.provenance = CITIZEN_ASSERTED` | Used for narrative context, relationship classification and explainable review decisions; never treated as verified fact |
| Incident date and time | `Submission.incident_date`, `Submission.original_content.incident_time`, `Submission.original_content.approximate_time` | Citizen-authored provenance on `Submission` and `SubmissionEvent` | Drives duplicate/related clustering, relationship hypotheses and rule evaluation |
| Location + province / city / station / unit | `Submission.location`, `Submission.original_content.province`, `city`, `station`, `unit` | Citizen-authored, retained in `original_content` | Used to cluster candidate incidents and by later procedural review |
| Incident category / type | `Submission.original_content.incident_category` | Citizen-provided classification only | Labels the report for classification and triage; never promoted to official legal finding |
| Detailed description / before / after | `Submission.description`, `Submission.original_content.what_happened`, `Submission.original_content.before_after` | `Submission.description` is the base narrative; additional details remain citizen assertions | Used as source evidence for `Assertion` and `Claim` extraction and relationship analysis |
| Police member involvement | `Submission.original_content.police_member_involved`, `Submission.original_content.police_member_details` | Citizen-provided detail, not official verification | Provides context for candidate classification and procedural routing |
| Victims / affected persons | `Submission.original_content.victims` and `Submission.original_content.people_involved` | Citizen-authored dataset in the protected submission | Context for incident classification and evidence review; not converted into verified charge facts |
| Witnesses | `Submission.original_content.witnesses` | Citizen-authored dataset in the protected submission | Supports classification and operator follow-up; preserved immutably |
| Harm / injuries / medical attention | `Submission.original_content.harm`, `injuries`, `medical_attention` | Protected submission data, citizen-supplied | Supports impact analysis and downstream review decisions |
| Property / financial / other impact | `Submission.original_content.property_impact`, `financial_impact`, `impact_summary` | Citizen-authored | Used in incident evaluation and case review context |
| Evidence and evidence context | `SubmissionEvidence` rows plus `Submission.original_content.evidence` summary | `SubmissionEvidence.source_actor_id` and `Evidence.source = citizen_submission` with SHA-256 verification | Supports chain-of-custody, review and investigative follow-up |
| Previous report / case reference | `Submission.original_content.previous_report_reference`, `previous_report_belief` | Citizen-authored and preserved as immutable report metadata | Feeds `Relationship` and duplicate detection; never creates a case directly |
| Additional information / corrections / withdrawal | `SubmissionEvent`, `SubmissionCorrection`, `WithdrawalRequest` | Append-only provenance; no overwrite of original content | Enables immutable updates while preserving original report history |
| Protected `Submission` lifecycle | `Submission` model | `Submission.provenance` and `SubmissionEvent` history | Distinct source-of-truth for the original citizen report |
| Claims derived from assertion text | `Assertion` -> `Claim` | `Assertion.provenance = CITIZEN_ASSERTED`; `Claim.provenance = CITIZEN_ASSERTED` | Supports `IncidentCandidate` derivation and `Relationship` hypotheses |
| Incident candidate and relationship hypotheses | `IncidentCandidate`, `Relationship` | `SYSTEM_DERIVED` provenance | Determines repeated/same/related incident classification without mutating the original submission |
| Rule evaluation and control evaluation | `RuleEvaluation`, `ControlEvaluation` | System-generated, immutable log | Enforces the procedural gate and produces explainable review outcomes |
| Procedural case creation | `CaseDocket` only when allowed through `CaseCreationGate` | `case_origin = incident_candidate`, `gate_decision` recorded | Final procedural handling after review; never created directly by citizen |

## Existing domain coverage

The following objects already exist in the backend and can represent the required citizen information without inventing duplicate models:

- `Submission` for the protected report itself and immutable `original_content`
- `SubmissionEvent` for append-only lifecycle history
- `Assertion` and `Claim` for citizen statements and derived structured meaning
- `SubmissionEvidence` for evidence records and integrity metadata
- `SubmissionCorrection` and `WithdrawalRequest` for additional information and withdrawal flows
- `IncidentCandidate`, `Relationship`, `RuleEvaluation`, and `ControlEvaluation` for classification and gate evaluation
- `CaseDocket` as the only procedural case model created only after the gate allows it

## Implementation gap

The gap is not in the existing domain model. The gap is the UI and API contract: the form and detail page were still acting like a legacy docket workflow, and the backend validation was discarding rich structured fields because it only accepted a minimal subset of keys for `Submission`.

The required fix is to:

1. Preserve rich JSON in `Submission.original_content`.
2. Render the citizen UI around the protected submission process.
3. Keep citizen fields as citizen assertions, not official facts.
4. Trigger the backend review pipeline (`analyze_submission`) so `RuleEvaluation` and `ControlEvaluation` genuinely execute.
