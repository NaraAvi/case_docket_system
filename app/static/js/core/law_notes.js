/**
 * South African law annotations: one lookup table, one renderer. Templates emit
 * `<span data-law-note="key">` placeholders (components/_statutory_badge.html
 * `law_note` macro) that bindLawNotes() fills in; JS-rendered markup calls
 * lawNoteHtml(key). Informational only -- where a section number is not
 * certain, the note cites the Act as a whole.
 */

export const LAW_DISCLAIMER = 'Informational only, not legal advice.';

export const LAW_NOTES = {
  popia_consent: {
    cite: 'POPIA s11',
    short: 'Your consent lets us process this personal information.',
    title: 'Protection of Personal Information Act 4 of 2013, s11',
    body: 'Personal information may be processed only with a lawful justification. Consent is one such justification, and you may withdraw it or object to the processing.',
  },
  popia_correction: {
    cite: 'POPIA s24',
    short: 'You may ask for inaccurate personal information to be corrected.',
    title: 'Protection of Personal Information Act 4 of 2013, s24',
    body: 'A data subject may ask for personal information that is inaccurate, irrelevant, excessive, out of date, incomplete, misleading or unlawfully obtained to be corrected or deleted.',
  },
  popia_act: {
    cite: 'POPIA (Act 4 of 2013)',
    short: 'Personal information here is processed under POPIA.',
    title: 'Protection of Personal Information Act 4 of 2013',
    body: 'POPIA regulates how personal information is collected, used, stored and shared. Cited at Act level; see the Act for the specific conditions for lawful processing.',
  },
  popia_withdrawal: {
    cite: 'POPIA (Act 4 of 2013)',
    short: 'Withdrawal is recorded; the audit history is kept.',
    title: 'Withdrawing a submission under POPIA',
    body: 'POPIA lets you withdraw consent to processing. Records that must be kept for accountability and the audit trail are preserved, so a withdrawal is logged as a request and not a deletion. Cited at Act level.',
  },
  popia_voice: {
    cite: 'POPIA s11',
    short: 'Submitting a recording means consenting to processing of your voice.',
    title: 'POPIA s11: consent to process a voice recording',
    body: 'A voice recording is personal information. By submitting it you consent to it being stored and processed, including automatic transcription. See the ECTA s15 note for how the recording may count as evidence.',
  },
  ecta_s15: {
    cite: 'ECTA s15',
    short: 'A recording is a data message and may be admitted as evidence.',
    title: 'Electronic Communications and Transactions Act 25 of 2002, s15',
    body: 'Section 15 says a data message (such as an audio file or a transcript) may not be denied admissibility only because it is electronic. Its evidential weight depends on things like how reliably it was stored and whether it is unaltered.',
  },
  transcript: {
    cite: 'ECTA s15 / POPIA',
    short: 'The transcript is a data message; processing it falls under POPIA.',
    title: 'Transcripts: ECTA s15 and POPIA',
    body: 'A transcript is a data message for ECTA s15 purposes (admissibility and evidential weight). Processing the words of a transcript is processing of personal information under POPIA (cited at Act level). The recording, not the automatic transcript, is the primary record.',
  },
  recording_comparison: {
    cite: 'POPIA s24 / PAJA s3',
    short: 'Automated aid only, not a finding. Errors can be corrected.',
    title: 'Recording comparison: POPIA s24 and PAJA s3',
    body: 'This comparison is generated automatically as an aid and is not a finding. POPIA s24 gives a right to have inaccurate information corrected. Any administrative decision that relies on it must still be procedurally fair (PAJA 3 of 2000, s3), which includes a chance to respond.',
  },
  cpa_s212: {
    cite: 'CPA s212 / ECTA s15',
    short: 'SHA-256 chain of custody; ECTA s15 covers electronic evidence.',
    title: 'Evidence: CPA s212 and ECTA s15',
    body: 'Files are hashed with SHA-256 to show they have not changed since upload. Criminal Procedure Act 51 of 1977, s212 deals with proof of certain facts by affidavit or certificate; the admissibility and weight of electronic evidence is governed by ECTA 25 of 2002, s15.',
  },
  paja_s3: {
    cite: 'PAJA s3',
    short: 'Decisions affecting you must be procedurally fair.',
    title: 'Promotion of Administrative Justice Act 3 of 2000, s3',
    body: 'Administrative action that materially affects a person must be procedurally fair: adequate notice, a reasonable opportunity to make representations, and a clear statement of the decision and reasons.',
  },
  paja_findings: {
    cite: 'PAJA s3 / ECTA s15',
    short: 'Findings must rest on admissible evidence and fair procedure.',
    title: 'Findings: PAJA s3, CPA s212 and ECTA s15',
    body: 'A finding is administrative action and must be procedurally fair (PAJA s3) and rest on evidence that can be admitted (electronic evidence: ECTA s15; certificates and affidavits: CPA s212).',
  },
  paia: {
    cite: 'PAIA (Act 2 of 2000)',
    short: 'You may request access to records held by public bodies.',
    title: 'Promotion of Access to Information Act 2 of 2000',
    body: 'PAIA gives effect to the constitutional right of access to information (Constitution s32). Cited at Act level.',
  },
  constitution: {
    cite: 'Constitution s14, s32, s33',
    short: 'Privacy, access to information and just administrative action.',
    title: 'Constitution of the Republic of South Africa, 1996',
    body: 'Section 14 protects privacy, s32 gives a right of access to information and s33 gives a right to lawful, reasonable and procedurally fair administrative action.',
  },
  ipid_s28: {
    cite: 'IPID Act s28',
    short: 'IPID must investigate specified serious police matters.',
    title: 'Independent Police Investigative Directorate Act 1 of 2011, s28',
    body: 'Section 28 lists matters IPID investigates, such as deaths in police custody or as a result of police action, torture, rape by a police officer and corruption. Other complaints of misconduct may also be referred.',
  },
  ipid_s29: {
    cite: 'IPID Act s29',
    short: 'Reports of police misconduct can be made to IPID.',
    title: 'Independent Police Investigative Directorate Act 1 of 2011, s29',
    body: 'Section 29 deals with reporting matters to the Directorate. Cited by section only; see the Act for who must report and how.',
  },
  saps_act: {
    cite: 'SAPS Act (68 of 1995)',
    short: 'Police functions and conduct are governed by the SAPS Act.',
    title: 'South African Police Service Act 68 of 1995',
    body: 'The SAPS Act sets out the functions, powers and duties of the police service and its members. Cited at Act level.',
  },
  precca_s34: {
    cite: 'PRECCA s34',
    short: 'Certain corruption offences must be reported.',
    title: 'Prevention and Combating of Corrupt Activities Act 12 of 2004, s34',
    body: 'Section 34 places a duty on persons in positions of authority to report certain corrupt transactions and offences to the police.',
  },
  harassment: {
    cite: 'PHA 17 of 2011 / DVA 116 of 1998',
    short: 'Harassment and domestic violence have specific protection orders.',
    title: 'Protection from Harassment Act 17 of 2011 and Domestic Violence Act 116 of 1998',
    body: 'If you are being harassed or are at risk of domestic violence, these Acts provide for protection orders. Cited at Act level; tell the officer if you are at risk.',
  },
  ni_3_2011: {
    cite: 'SAPS NI 3/2011',
    short: 'A docket must be registered within 72 hours.',
    title: 'SAPS National Instruction 3/2011',
    body: 'The instruction sets the 72-hour service level used here for registering and progressing a docket. The period is shown as a live countdown.',
  },
  saps_discipline: {
    cite: 'SAPS Discipline Regs 2016',
    short: 'Disciplinary outcomes follow the SAPS Discipline Regulations.',
    title: 'SAPS Discipline Regulations, 2016',
    body: 'Disciplinary proceedings against SAPS members follow these regulations. Cited at instrument level.',
  },
};

const escapeHtml = (value) => String(value ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/** Markup for one law note (inline text plus an info button and popover). */
export function lawNoteHtml(key) {
  const note = LAW_NOTES[key];
  if (!note) {
    return '';
  }
  return `<span class="law-note"><span class="law-note-text"><strong>${escapeHtml(note.cite)}</strong>: ${escapeHtml(note.short)}</span>`
    + `<button type="button" class="law-note-btn" aria-expanded="false" aria-label="More about ${escapeHtml(note.cite)}">i</button>`
    + `<span class="law-note-pop hidden" role="note"><strong>${escapeHtml(note.title)}</strong><p>${escapeHtml(note.body)}</p><small>${LAW_DISCLAIMER}</small></span></span>`;
}

/** Fill every empty `[data-law-note]` placeholder under `root`. */
export function bindLawNotes(root = document) {
  root.querySelectorAll('[data-law-note]:empty').forEach((slot) => {
    slot.innerHTML = lawNoteHtml(slot.dataset.lawNote);
  });
}

let popoverBound = false;

/** One delegated handler toggles popovers for template and JS-rendered notes. */
export function initLawNotes() {
  bindLawNotes(document);
  if (popoverBound) {
    return;
  }
  popoverBound = true;
  document.addEventListener('click', (event) => {
    const button = event.target.closest ? event.target.closest('.law-note-btn') : null;
    document.querySelectorAll('.law-note-pop:not(.hidden)').forEach((pop) => {
      if (pop.previousElementSibling !== button) {
        pop.classList.add('hidden');
        pop.previousElementSibling?.setAttribute('aria-expanded', 'false');
      }
    });
    if (button && button.nextElementSibling) {
      const open = button.nextElementSibling.classList.toggle('hidden') === false;
      button.setAttribute('aria-expanded', String(open));
    }
  });
}
