# IPID Portal - Quick Start

## 1. Open the project

Open the `case_docket_system` folder in VS Code.

## 2. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Windows Command Prompt:

```bat
python -m venv .venv
.venv\Scripts\activate
```

## 3. Install Python dependencies

Run this from the `case_docket_system` folder:

```bash
pip install -r requirements.txt
```

A copy of `requirements.txt` is also included at the ZIP root so the dependency file is easy to find.

## 4. Start Flask

From the `case_docket_system` folder, run:

```bash
flask --app app run --debug
```

If your project uses a different Flask entrypoint configured by your environment, use that existing command instead.

## 5. Open the IPID Portal

Open the local address printed by Flask in your browser and sign in with one of the seeded IPID identities shown by the application.

The IPID dashboard has been restyled to match the supplied reference screenshot: compact navy sidebar, mono-style portal typography, security restriction banner, live review queue, dark decision-rationale panel, and the lower custody/disciplinary sections.
