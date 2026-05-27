---
id: INDEX
title: Compliance Copilot — Regulation Corpus Index
note: Lightweight index used by the agent's identify_applicable_regs tool to route scenarios to relevant regulations. Every entry maps a regulation id (matching the filename) to its scope, trigger keywords, and high-level applicability test.
---

- id: NYC_LL144
  file: nyc_ll144.md
  jurisdiction: New York City, USA
  domain: hiring / automated employment decision tools
  triggers: AEDT used to screen NYC candidates or for NYC-located positions (hire or promote)
  signals: ["NYC", "New York City", "AEDT", "hiring tool", "resume screen", "candidate", "applicant tracking", "automated employment"]

- id: EEOC_AI_TITLE_VII
  file: eeoc_ai_hiring.md
  jurisdiction: United States (federal)
  domain: federal employment discrimination law as applied to algorithmic selection
  triggers: Title VII-covered US employer using AI/algorithmic selection procedure
  signals: ["US employer", "Title VII", "disparate impact", "four-fifths", "algorithmic", "AI hiring", "resume screening", "federal"]

- id: GDPR
  file: gdpr.md
  jurisdiction: European Union / EEA
  domain: personal data processing, automated decision-making, profiling
  triggers: Processing personal data of EU/EEA individuals or by EU-established controller, especially solely-automated decisions with legal/significant effect
  signals: ["EU", "European", "GDPR", "EEA", "EU candidates", "profiling", "automated decision", "personal data", "data subject"]

- id: EU_AI_ACT
  file: eu_ai_act.md
  jurisdiction: European Union / EEA
  domain: AI system providers and deployers; prohibited & high-risk AI
  triggers: AI system placed on EU market, deployed in EU, or whose output is used in EU; hiring AI is high-risk by default; emotion recognition in workplace prohibited
  signals: ["EU AI Act", "high-risk AI", "emotion recognition", "biometric", "EU", "CE marking", "conformity assessment", "deployer", "provider"]

- id: CCPA_CPRA
  file: ccpa_cpra.md
  jurisdiction: California, USA
  domain: consumer (incl. applicant/employee) privacy; automated decision-making technology (ADMT)
  triggers: Qualifying business processing personal information of California consumers including applicants and employees
  signals: ["California", "CA", "CCPA", "CPRA", "consumer", "applicant", "employee privacy", "ADMT", "sensitive personal information"]

- id: COLORADO_AI_ACT
  file: colorado_ai_act.md
  jurisdiction: Colorado, USA
  domain: high-risk AI systems making or substantially contributing to consequential decisions
  triggers: Developer or deployer doing business in Colorado where AI is a substantial factor in a consequential decision (incl. employment)
  signals: ["Colorado", "high-risk AI", "consequential decision", "algorithmic discrimination", "impact assessment", "SB 24-205"]

- id: IL_AIVI
  file: illinois_aivi.md
  jurisdiction: Illinois, USA
  domain: AI analysis of applicant-submitted video interviews
  triggers: Illinois-based position where applicants are asked to submit videos analyzed by AI
  signals: ["Illinois", "video interview", "AI video", "applicant video", "demographic reporting"]
