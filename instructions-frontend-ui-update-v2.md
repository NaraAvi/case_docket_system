# Frontend UI update (v2): re-implement on `mohammed-ui-changes`

This replaces the earlier instructions file. The presentation work is **re-implemented from scratch** on this branch. Do **not** cherry-pick or merge `96d03c2` / `mohammed-frontend-presentation`. You may read that branch for reference only (`git show origin/mohammed-frontend-presentation:<path>`), but every change must be written against the current code.

## What changed since the original plan (read before starting)
This branch is `26044a1` plus one commit, `341ee11` "Fix detective workflow and recording transcription". It touched these frontend files, so **all line numbers and function locations in the old plan are stale. Re-locate everything by name.**

1. **Recording features (new cards and content)**
   - Citizen docket detail: a new `#citizenRecordingComparison` box inside the Interview Recording card; `citizen.js` now renders inline audio and transcript (`renderInlineMedia`, `resolveTranscriptText`, `resolveTranscriptError`, `renderRecordingComparison`, `resolveCitizenInterviewId`, `isInterviewComplete`), and imports `fetchMediaBlobUrl` from `core/api.js`.
   - Constable docket: a `#constableRecordingComparison` box plus inline media and transcript in `constable.js`.
   - Detective: `renderDetectiveInterviewDetails` now shows recordings, transcript status and the "Recording consistency check" report.
   - CSS additions in `pdas.css`: `.interview-media-holder`, `.transcript-box`, and `audio` rules, and `min-width:0` on `.mini-case-card`. **Keep these rules.**
2. **Detective workflow rail changed** in both `detective_case_workspace.html` and `detective.js`: step 2 is now **Case Facts Verification** (was "Statements & Evidence"); the steps are Case Review, Case Facts Verification, Investigation (six required actions), Findings, Final Reasoning, Completion.
3. **Detective gating**: `syncFindingsGateState` and `syncCompletionGateState` now show and hide or disable `#openFindingModal`, `#openCompleteInvestigationModal`, `#openNoteEntryModal`, and `#proceedToFindingsButton` / `[data-proceed-to-findings]` based on stage and completed actions. **Do not override `hidden` or `disabled` on these buttons from CSS or new JS.**
4. Tests grew a lot (`modules.detective.test.js` +495 lines, plus citizen and constable tests). Backend changed heavily (frozen scope, see below).

## Scope rules (unchanged)
- **No backend changes.** Only `.html`, `.css`, `.js`. Do not touch any `.py` file, `requirements.txt` or `tests/*.py`.
- **No functional or workflow changes** to any card or field: presentation, order and visibility only. Payload keys, ids, `data-*` attributes and `[data-action-field]` keys are never renamed or removed.
- Keep JS changes minimal. All existing vitest and pytest tests must keep passing with no weakened assertions; adjust only fixtures if a new wrapper element is required.
- User decisions carried over: "car" means *card*; country code and email domain are combined in JS into the existing `contact_phone` and `contact_email`; a milestone means status/stage changes and key actions.
- Classes and wrappers go on **outer template cards**, never inside JS-rendered containers (`innerHTML` re-renders will wipe them).

## Approach

### SHARED
1. **Card borders**: add a `--line-strong` variable and a subtle shadow on `.detail-card, .panel-card, .section-block, .mini-case-card, .docket-card, .section-wrap, .wizard-card, .case-card`. Layout unchanged. Preserve `min-width:0` on `.mini-case-card`.
2. **Collapsible nav**: toggle button in the `base.html` brand block; `--sidebar-w` variable used by both `.pdas-sidebar` and `.pdas-main` margin; `.pdas-shell.nav-collapsed` at about 68px hides `.brand-copy` and nav label text (nav items need an icon or short letter in a span); state in `localStorage` inside try/catch; new `core/nav.js` imported once from `pdas_app.js`; leave the `@media (max-width:900px)` behaviour intact.
3. **Generic collapsible helper**: `bindCollapsibles(root)` in `core/ui.js` using `[data-collapsible]` cards, a header toggle button, `aria-expanded`, and `.hidden` on the body (same pattern as `#citizenSubmissionToggle`). Toggle only the outer wrapper.
4. **Audit trails: milestones plus "Show full trail (N)"**
   - Extend `renderTimelineList` (`core/ui.js`) with an optional `milestoneTypes` Set and a toggle button. Default view shows milestones only; if none match, or there are 5 or fewer entries, show everything.
   - Convert the inline citizen timeline renderer in `citizen.js` (find by searching the timeline rendering code) to the same helper.
   - Milestones: `submission_created, submitted, docket_submitted, docket_created, incident_candidate_case_created, docket_registered, interview_completed, investigation_opened, detective_investigation_completed, statutory_ipid_referral, case_frozen, case_unfrozen, withdrawal_requested, correction_logged, escalation_created, ipid_escalation_upheld, ipid_escalation_dismissed, assignment_created, station_commander_force_reassigned_docket, disciplinary_case_created, disciplinary_case_closed`.
   - **First step:** grep the current backend event names (`app/modules`, `app/api/v1/routes.py`) for any event types added by `341ee11` (for example recording submitted, transcription completed, recording comparison, case facts verified, finding documented, action completed, investigation completed). Add clearly key ones to the milestone set and list them in your final report. Presentation-time filtering only; keep raw event strings visible in the text (citizen tests assert on them).
   - Apply to: citizen timeline, detective "Procedural / Audit History", IPID timeline and audit, station commander audit trail.
5. **South African law annotations** (small inline note plus an info button opening a popover with a fuller plain-language description)
   - Extend `components/_statutory_badge.html` into a `law_note(key)` macro plus a JS helper for JS-rendered markup. One lookup table holds all text. Footer disclaimer: "Informational only, not legal advice."
   - Verified provisions: POPIA 4 of 2013 s11 (consent) and s24 (correction/deletion); PAIA 2 of 2000 (Act level); Constitution s14, s32, s33; PAJA 3 of 2000 s3; IPID Act 1 of 2011 s28 and s29; CPA 51 of 1977 s212; **ECTA 25 of 2002 s15** (admissibility of data messages); SAPS Act 68 of 1995 (Act level); PRECCA 12 of 2004 s34; Protection from Harassment Act 17 of 2011 and Domestic Violence Act 116 of 1998 (Harassment incident type and harm/risk); SAPS National Instruction 3/2011 (72-hour SLA); SAPS Discipline Regulations 2016.
   - Do not invent section numbers; cite at Act level if unsure. Existing text pairs CPA s212 with SHA-256 chain of custody, which s212 does not cover: keep the wording, add ECTA s15 as the correct basis for electronic evidence, and flag it in the report.
   - **New placements for the recording features (POPIA/ECTA)**: citizen Interview Recording card and "Submit My Recording" (POPIA s11 consent to processing of a voice recording; ECTA s15 evidential weight of the recording); transcript and transcript-status display on citizen, constable and detective (ECTA s15 for the data message; POPIA Act level for processing of a transcript); recording comparison / "Recording consistency check" (POPIA s24 accuracy and correction; note it is an automated aid, not a finding, and PAJA s3 procedural fairness for any decision reliant on it).
   - Other placements: citizen contact section and consent (POPIA s11); correction request (s24); withdrawal (POPIA); escalate-to-IPID modal (IPID Act s28); constable registration/72h (NI 3/2011); invalidity flags (PAJA, already there); detective evidence and findings (CPA s212 plus ECTA s15, PAJA); station commander SLA; IPID decisions (IPID Act s28, Discipline Regs); footer Privacy link (POPIA).

### Citizen dashboard (`citizen_docket_form.html` + `citizen.js`)
Cards that start **collapsed** are the long or read-only ones (protected source groups, full audit trail, completed investigation cards). Forms and action cards start open.

6. **Green completion for cards 1-5** (rule: every visible question answered; optional free-text does not count): `.section-block.is-complete` driven by a read-only `evaluateCardCompletion()` on input/change. Does not gate submit or touch payload building.
   - Card 1: relationship, `canContact`, contact rule below.
   - Card 2: incident type, date certainty plus dependent date, location known plus dependent location, description.
   - Card 3: `otherPeopleInvolved`, plus `peopleCount` if Yes.
   - Card 4: `wasAnyoneHarmed` plus dependents for Yes answers.
   - Card 5: evidence available, previous report, current safety, plus dependents.
   - Re-read `bindConditionalCitizenForm` first; it may have changed. List any assumptions in the report.
7. **Preferred Contact Method**: "No preference" renders as today; otherwise show the chosen method's input first. Consent Yes needs at least one contact box filled; Consent No counts as complete. Add a country-code `<select>` (default +27, short list of common codes) beside phone, and an email-domain input with "@" between it and the local part. Strip a leading 0 from the local number, no spaces or dashes. In `buildStructuredSubmissionPayload` combine into the **same keys** (`contact_phone = cc + digits`, `contact_email = local@domain`). Update the review summary and reset logic in `syncContact`.
8. **Card 4 injury dropdown**: hide `#wasAnyoneInjured`; when `#wasAnyoneHarmed` is Yes, set it to Yes automatically and show `#injuryFields`; otherwise keep the cleared behaviour. Payload keys unchanged.

### Citizen docket detail (`citizen_docket_detail.html`)
9. Order after Current Status: (Submission Information + Timeline/History side by side) → **Interview Recording** → Evidence or Supporting Material → Additional Information → (Correction Request + Withdrawal Request side by side). Keep Submitted Information, My Escalations and the submit footer next to their closest card. **The Interview Recording card keeps everything inside it**, including inline audio and transcript, the submit-recording controls and `#citizenRecordingComparison`, and stays hidden until JS unhides it. Make the comparison sub-section collapsible inside that card (`data-collapsible`, collapsed by default). Move card wrappers only, and keep all ids.
10. Sticky, collapsible right-hand section nav with anchor links (HTML/CSS, optional scrollspy), one link per card wrapper.

### Constable docket (`constable_docket_review.html`)
11. Stack cards vertically. Evidence and Related Cases stay in a shared two-column `.cards-grid`; Interview & Recording is full width (`grid-column:1/-1`) below and **contains** inline media, transcript and `#constableRecordingComparison`, with the comparison collapsible and collapsed by default.
12. Protected citizen source: regroup `renderProtectedSource` in `constable.js` under subheadings (About the reporter, Incident, Harm & injury, People, Evidence, Contact, Safety, Other) via a key-to-group map, each as a native `<details>`. Keep `formatProtectedSourceValue` and every key and value. Move the renderer to `core/ui.js` for sharing with the detective page. Re-check first whether `341ee11` changed this function.

### Detective docket (`detective_case_workspace.html`)
13. Original protected submission: reuse the shared grouped renderer, collapsed by default.
14. Order (positions only), following the new rail: Status → Workflow rail → Investigation Control Board → Case/Docket details + Original submission (collapsed) → Deposition + Protected Evidence → Recordings/Statements (including the interview details and "Recording consistency check", collapsible) + Audit History (milestones) → **Case Facts Verification** → Investigation → Investigation Order/Actions → Findings → Final Reasoning.
    - Keep the tested order: actions list before findings before final reasoning; keep the hidden "Complete <Action>" div and `id="openFindingModal" hidden`.
    - Do not restyle or unhide the gated buttons (`#openFindingModal`, `#openCompleteInvestigationModal`, `#openNoteEntryModal`, proceed-to-findings). Their visibility belongs to `syncFindingsGateState` / `syncCompletionGateState`.
    - Do not edit the rail step labels or `detective.js` rail logic, which are already updated.
15. Every moved card keeps its ids and handlers.

### Detective active investigation
16. `.is-complete` (light green background and border) on: each of the six required-action cards (in `renderInvestigationOrder`, based on `getCompletedRequiredActions`), Findings (1+ findings), Final Reasoning (investigation COMPLETED), Case Facts Verification (`verified`). Optionally add live "form complete" hints in action modals by calling `buildActionModalPayload` and `validateActionModalPayload` read-only. Re-read those functions first: `validateActionModalPayload` gained new rules (Record Request now requires a date or date range and a relevance reason).
17. **Witness Contact**: `relationship_to_incident` becomes a `<select>` (Eyewitness, Victim, Family member, Bystander, Colleague, Other), same `data-action-field` key; `lead_description` shown only when `lead_generated` is Yes (small `change` listener toggling `.hidden`).
18. Same conditional reveal for the other forms wherever validation already implies it (Interview lead description, contradiction explanation, outcome explanation; Evidence Collection result explanation; Record Request response explanation). Values submit exactly as today. Confirm each trigger against the current validation code.
19. Restyle action-modal forms for readability: grouped rows, subheadings, hints, required markers, spacing. No change to `data-action-field` names. Add required markers to the new Record Request date and relevance fields.

## Files to modify
- CSS: `app/static/css/pdas.css`
- Templates: `base.html`, `citizen_docket_form.html`, `citizen_docket_detail.html`, `constable_docket_review.html`, `detective_case_workspace.html`, `ipid_escalation_detail.html`, `station_commander_docket_detail.html`, `components/_statutory_badge.html`, `components/_timeline.html`
- JS: `core/ui.js`, new `core/nav.js`, `pdas_app.js`, `modules/citizen.js`, `modules/constable.js`, `modules/detective.js`, `modules/station_commander.js`, `modules/ipid.js` (timeline call sites only). `core/api.js` is untouched.
- JS tests: fixtures only.

## Verification
1. `npm test` and the relevant pytest suites must pass, at minimum `tests/test_milestone3.py`, `tests/test_frontend_modularization.py`, and the detective, constable and transcription suites added in `341ee11`. If a Python test fails for a reason unrelated to the UI (environment, missing transcription dependency), say so and do not edit it.
2. Run the preview server and log in with seeded identities from `seed_data/test_citizens.py`. Screenshot each of:
   - Nav collapse and persistence, card borders, collapsibles, mobile width.
   - Citizen form: card green states, contact reordering, country code and email-domain boxes, card 4 auto-yes, and a real submit whose request payload has the combined contact values (also check the constable protected view).
   - Citizen docket detail: card order, right nav, Interview Recording card with audio, transcript and comparison collapsible.
   - Constable: order, Evidence/Related side by side, Interview & Recording full width with comparison, grouped protected source.
   - Detective: new order, grouped protected submission, start an investigation, complete all six actions, gated Findings and Complete buttons still unlock correctly, green states, Witness Contact select and conditional lead box.
   - Audit trails default to milestones and "Show full trail" reveals everything.
   - Law-note inline text and popovers, including the new recording and transcript notes, and the footer disclaimer.
3. Confirm `git diff --stat` shows no `.py`, `requirements.txt` or `tests/*.py` changes, and that no id or `data-action-field` was removed or renamed (diff the id sets before and after).

## Prompt to give Claude Code
```
Perform a presentation-only frontend update on this Flask app (case_docket_system), branch mohammed-ui-changes. Follow instructions-frontend-ui-update-v2.md in the repo root exactly. Re-implement from scratch; do NOT cherry-pick or merge mohammed-frontend-presentation. Edit only .html, .css and .js files; do NOT touch any .py file, requirements.txt or tests/*.py. Do not change functionality, workflow, payload keys, ids, data-* attributes, or the detective flow (actions -> findings -> final reasoning). Do not override the hidden/disabled state of the gated detective buttons (#openFindingModal, #openCompleteInvestigationModal, #openNoteEntryModal, proceed-to-findings) or the updated workflow rail. The latest commit added inline recording audio/transcripts and recording-comparison boxes on citizen, constable and detective screens: fold them into the Interview Recording card on each role (comparison collapsible and collapsed by default) and add POPIA/ECTA law notes for them. Locate everything by function/id name because line numbers have changed. Keep JS minimal, keep npm test and pytest passing, verify every screen in the preview server with seeded users and screenshots, then report the screenshots, any new milestone event names you added, the CPA s212 vs ECTA s15 flag, and any assumptions.
```
