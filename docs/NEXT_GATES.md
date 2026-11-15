# The next engineering gates

## 1. Authority and jurisdiction

- Reproduce and verify the official Kansas City, Missouri City Charter and municipal code, section by section, with authoritative links and legal effective dates.
- Introduce `legal_document_versions` with provenance and hash verification; detect amended/repealed provisions.
- Require review by legal experts where hierarchy, statutory preemption, or legal ambiguity arises.

## 2. Data quality and signals

- Source-specific authorized connectors; stable feed identifiers and timestamp validation; data retention and redaction rules.
- Verify whether allegedly independent source labels represent independent evidence.
- Calibrated infrastructure/service forecasting models with historical validation, sensitivity/specificity, drift monitoring and disparate-impact checks.
- Reject any use for predicting person-level offenses, innocence or guilt, or bypassing due process.

## 3. Secure deployment

- IAM/SSO RBAC with per-request staff identity, least privilege and reviewer separation.
- Witness audit heads outside the host (remote write-once service), offline backups and recovery drills.
- Full threat modeling, penetration testing, encrypted rest and transit, compliance/legal review.
- Granular secrets/keys rotation and secure provisioning. Do not use development keys on government systems.

## 4. Model and human review

- Quantitative evaluation of Ollama research model grounding, factuality, citation quality and sensitivity to prompt injection.
- Human fact-check protocol and time-bounded status; findings can be disputed or superseded.
- No automatic public-action execution; authorized humans should approve workflows.

## 5. Broader product system

- Optional, permission-controlled read-only adapters to Clerk's Access and the *proposed* Chambers Desk.
- A modular agency-level workflow interface, audit-ready reporting, and WCAG 2.1 AA review.
- A reproducible deployment artifact with signed builds and documented dependency SBOM.
