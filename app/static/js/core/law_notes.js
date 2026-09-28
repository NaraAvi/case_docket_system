/**
 * Plain-language South African law annotations shown beside fields and
 * sections. LAW_NOTES is the single lookup table for all of the text: the
 * Jinja macro components/_statutory_badge.html::law_note only emits a
 * `data-law-note` placeholder that hydrateLawNotes() fills from here, and JS
 * renderers call renderLawNote() directly.
 *
 * Only provisions that have been checked are cited by section; where a
 * specific section is not certain the note cites the Act as a whole.
 * Informational only, not legal advice.
 */

export const LAW_NOTE_DISCLAIMER = 'Informational only, not legal advice.';

export const LAW_NOTES = {
  popia_s11: {
    cite: 'POPIA s11',
    act: 'Protection of Personal Information Act 4 of 2013, section 11',
    short: 'Contact details are used only with your consent',
    detail: 'Section 11 of POPIA sets out when personal information may lawfully be processed, for example with the consent of the person it relates to, or where the processing is necessary to comply with a legal obligation or protect a legitimate interest. A person may withdraw consent or object to processing, although this does not affect processing that already took place lawfully. On this form, contact details are optional and are only asked for if you agree to be contacted.',
  },
  popia_s24: {
    cite: 'POPIA s24',
    act: 'Protection of Personal Information Act 4 of 2013, section 24',
    short: 'You may ask for inaccurate personal information to be corrected',
    detail: 'Section 24 of POPIA lets a person ask for personal information about them to be corrected or deleted if it is inaccurate, irrelevant, excessive, out of date, incomplete, misleading or obtained unlawfully. In PDAS a correction request is recorded as a new, linked entry so the original submission remains preserved in the audit trail.',
  },
  paia: {
    cite: 'PAIA',
    act: 'Promotion of Access to Information Act 2 of 2000',
    short: 'Right to request access to records',
    detail: 'PAIA gives effect to the constitutional right of access to information. It sets out how a person can request records held by public and private bodies, and the limited grounds on which access may be refused, for example to protect another person\'s privacy or the integrity of an investigation or legal proceedings.',
  },
  constitution_s14: {
    cite: 'Constitution s14',
    act: 'Constitution of the Republic of South Africa, 1996, section 14',
    short: 'Right to privacy',
    detail: 'Section 14 of the Constitution protects everyone\'s right to privacy, including the right not to have their person, home or property searched, their possessions seized, or the privacy of their communications infringed. It is one of the reasons the original citizen submission is shown read-only and handled with restricted access.',
  },
  constitution_s32: {
    cite: 'Constitution s32',
    act: 'Constitution of the Republic of South Africa, 1996, section 32',
    short: 'Right of access to information',
    detail: 'Section 32 of the Constitution gives everyone the right of access to information held by the State, and to information held by another person that is required to exercise or protect a right. PAIA is the national legislation that gives effect to this right.',
  },
  constitution_s33: {
    cite: 'Constitution s33',
    act: 'Constitution of the Republic of South Africa, 1996, section 33',
    short: 'Right to fair administrative action and reasons',
    detail: 'Section 33 of the Constitution gives everyone the right to administrative action that is lawful, reasonable and procedurally fair, and a person whose rights have been adversely affected has the right to be given written reasons. PAJA gives effect to this right.',
  },
  paja_s3: {
    cite: 'PAJA s3',
    act: 'Promotion of Administrative Justice Act 3 of 2000, section 3',
    short: 'Decisions must be procedurally fair, with reasons recorded',
    detail: 'Section 3 of PAJA requires administrative action that materially and adversely affects a person\'s rights to be procedurally fair. This generally includes adequate notice, a reasonable opportunity to make representations, a clear statement of the action, and notice of any right of review or appeal and of the right to request reasons. PDAS asks for a recorded justification for each status change.',
  },
  ipid_s28: {
    cite: 'IPID Act s28',
    act: 'Independent Police Investigative Directorate Act 1 of 2011, section 28',
    short: 'Matters IPID must investigate',
    detail: 'Section 28 of the IPID Act lists the matters IPID must investigate. These include deaths in police custody or as a result of police action, complaints about the discharge of an official firearm, rape by a police officer or of a person in police custody, torture or assault by a police officer, and corruption within the police, as well as certain other matters referred to IPID.',
  },
  ipid_s29: {
    cite: 'IPID Act s29',
    act: 'Independent Police Investigative Directorate Act 1 of 2011, section 29',
    short: 'Police must report section 28 matters to IPID',
    detail: 'Section 29 of the IPID Act requires SAPS and municipal police services to report matters that fall under section 28 to IPID immediately after becoming aware of them, followed by a written report, and requires their members to cooperate with IPID\'s investigation.',
  },
  cpa_s212: {
    cite: 'CPA s212',
    act: 'Criminal Procedure Act 51 of 1977, section 212',
    short: 'Certain facts may be proved by affidavit or certificate',
    detail: 'Section 212 of the Criminal Procedure Act allows certain facts to be proved in criminal proceedings by affidavit or certificate, for example the results of some technical examinations and the receipt, custody and handling of items. A documented, reliable handling record (chain of custody) supports this kind of proof.',
  },
  ecta_s15: {
    cite: 'ECTA s15',
    act: 'Electronic Communications and Transactions Act 25 of 2002, section 15',
    short: 'Electronic evidence is admissible; its integrity affects its weight',
    detail: 'Section 15 of ECTA provides that a data message may not be excluded as evidence merely because it is in electronic form. Its evidential weight depends on factors such as how reliably it was generated, stored or communicated, how its integrity was maintained, and how its originator is identified. Hashing each uploaded file helps show that the file has not changed since it was received.',
  },
  saps_act: {
    cite: 'SAPS Act',
    act: 'South African Police Service Act 68 of 1995',
    short: 'Establishes and regulates the SAPS',
    detail: 'The South African Police Service Act establishes, organises, regulates and controls the South African Police Service, and deals with matters such as the powers and duties of members and the management of the Service.',
  },
  precca_s34: {
    cite: 'PRECCA s34',
    act: 'Prevention and Combating of Corrupt Activities Act 12 of 2004, section 34',
    short: 'Duty to report certain corruption',
    detail: 'Section 34 of PRECCA requires a person who holds a position of authority, and who knows or ought reasonably to have known or suspected that certain offences (such as corruption, theft, fraud, extortion or forgery) involving R100 000 or more have been committed, to report this to a police official.',
  },
  harassment_act: {
    cite: 'Protection from Harassment Act',
    act: 'Protection from Harassment Act 17 of 2011',
    short: 'Protection orders against harassment',
    detail: 'The Protection from Harassment Act lets a person apply to a magistrate\'s court for a protection order against harassment, including harassment by someone they are not in a domestic relationship with. An interim protection order can be granted in urgent cases.',
  },
  domestic_violence_act: {
    cite: 'Domestic Violence Act',
    act: 'Domestic Violence Act 116 of 1998',
    short: 'Protection orders within domestic relationships',
    detail: 'The Domestic Violence Act provides for protection orders where abuse, harassment or violence happens within a domestic relationship, for example between partners, family members or people who share a home. It also places specific duties on the police to assist complainants.',
  },
  saps_ni_3_2011: {
    cite: 'SAPS NI 3/2011',
    act: 'SAPS National Instruction 3 of 2011',
    short: 'Reference for the 72-hour registration and investigation window',
    detail: 'SAPS National Instruction 3 of 2011 is an internal SAPS instruction. PDAS uses it as the reference for its 72-hour docket registration and investigation service-level window. This note does not summarise the full instruction.',
  },
  saps_discipline_regs: {
    cite: 'SAPS Discipline Regs 2016',
    act: 'South African Police Service Discipline Regulations, 2016',
    short: 'Rules for SAPS disciplinary proceedings',
    detail: 'The SAPS Discipline Regulations, 2016 set out how alleged misconduct by SAPS employees is dealt with, including the disciplinary process, hearings and the sanctions that may be imposed.',
  },
};

function escapeLawText(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[character]));
}

function renderLawNoteInner(key, { short = true } = {}) {
  const note = LAW_NOTES[key];
  if (!note) {
    return '';
  }
  return `<span class="law-note-cite">${escapeLawText(note.cite)}</span>${short ? `<span class="law-note-text">${escapeLawText(note.short)}</span>` : ''}<button type="button" class="law-info" data-law-info="${escapeLawText(key)}" aria-haspopup="dialog" aria-expanded="false" aria-label="About ${escapeLawText(note.cite)}">i</button>`;
}

/**
 * HTML for one inline law note (visible short text plus an info button that
 * opens the fuller description). Unknown keys render nothing.
 */
export function renderLawNote(key, options = {}) {
  const inner = renderLawNoteInner(key, options);
  return inner ? `<span class="law-note" data-law-note="${escapeLawText(key)}" data-law-note-ready="true">${inner}</span>` : '';
}

/**
 * Fill the `data-law-note` placeholders emitted by the Jinja law_note macro.
 */
export function hydrateLawNotes(root = document) {
  if (!root || !root.querySelectorAll) {
    return;
  }
  root.querySelectorAll('[data-law-note]:not([data-law-note-ready])').forEach((element) => {
    const inner = renderLawNoteInner(element.dataset.lawNote, { short: element.dataset.lawNoteShort !== 'false' });
    if (!inner) {
      element.remove();
      return;
    }
    element.classList.add('law-note');
    element.innerHTML = inner;
    element.dataset.lawNoteReady = 'true';
  });
}

let activeLawButton = null;

function closeLawPopover({ restoreFocus = false } = {}) {
  const popover = document.getElementById('lawNotePopover');
  if (popover) {
    popover.remove();
  }
  if (activeLawButton) {
    activeLawButton.setAttribute('aria-expanded', 'false');
    if (restoreFocus) {
      activeLawButton.focus();
    }
  }
  activeLawButton = null;
}

function openLawPopover(button) {
  const note = LAW_NOTES[button.dataset.lawInfo];
  if (!note) {
    return;
  }
  closeLawPopover();
  const popover = document.createElement('div');
  popover.className = 'law-popover';
  popover.id = 'lawNotePopover';
  popover.setAttribute('role', 'dialog');
  popover.setAttribute('aria-label', `${note.cite}: plain-language summary`);
  popover.innerHTML = `
    <button type="button" class="law-popover-close" data-law-popover-close aria-label="Close">×</button>
    <h4>${escapeLawText(note.cite)}: ${escapeLawText(note.short)}</h4>
    <p class="law-popover-act">${escapeLawText(note.act)}</p>
    <p class="law-popover-body">${escapeLawText(note.detail)}</p>
    <div class="law-popover-footer">${escapeLawText(LAW_NOTE_DISCLAIMER)}</div>
  `;
  document.body.appendChild(popover);

  const rect = button.getBoundingClientRect();
  const width = popover.offsetWidth || 360;
  const left = Math.max(16, Math.min(rect.left + window.scrollX - 12, window.scrollX + document.documentElement.clientWidth - width - 16));
  popover.style.left = `${left}px`;
  popover.style.top = `${rect.bottom + window.scrollY + 8}px`;

  button.setAttribute('aria-expanded', 'true');
  activeLawButton = button;
  popover.querySelector('[data-law-popover-close]')?.focus();
}

/**
 * One delegated listener opens/closes the shared popover for every
 * `.law-info` button, including ones rendered later by JS.
 */
export function bindLawNotePopovers() {
  if (document.body.dataset.lawNotesBound === 'true') {
    return;
  }
  document.body.dataset.lawNotesBound = 'true';
  document.addEventListener('click', (event) => {
    const infoButton = event.target.closest('[data-law-info]');
    if (infoButton) {
      event.preventDefault();
      if (infoButton === activeLawButton) {
        closeLawPopover();
      } else {
        openLawPopover(infoButton);
      }
      return;
    }
    if (event.target.closest('[data-law-popover-close]')) {
      closeLawPopover({ restoreFocus: true });
      return;
    }
    if (activeLawButton && !event.target.closest('#lawNotePopover')) {
      closeLawPopover();
    }
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && activeLawButton) {
      closeLawPopover({ restoreFocus: true });
    }
  });
}
