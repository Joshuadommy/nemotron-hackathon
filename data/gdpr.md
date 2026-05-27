---
id: GDPR
title: General Data Protection Regulation (EU) 2016/679 — Selected Provisions
jurisdiction: European Union / European Economic Area
effective: 2018-05-25
enforcement: National Data Protection Authorities; European Data Protection Board (EDPB)
scope_keywords: [GDPR, EU, personal data, automated decision, profiling, Article 22, DPIA, candidate, employee, EEA, data subject, lawful basis, consent]
applies_when: Processing of personal data of individuals located in the EU/EEA, OR processing by an entity established in the EU, OR offering goods/services to or monitoring behavior of individuals in the EU. Applies to hiring tools that process EU-resident applicants regardless of employer location.
penalties: Up to €20 million or 4% of total worldwide annual turnover (whichever is higher) for Article 5, 6, 7, 9, 12-22 violations.
---

## §Art.5 Principles
Personal data must be: (a) processed lawfully, fairly, transparently; (b) collected for specified, explicit, legitimate purposes; (c) adequate, relevant, limited to what is necessary (data minimization); (d) accurate; (e) kept no longer than necessary; (f) processed securely.

## §Art.6 Lawful Basis
Processing is lawful only if at least one applies: (a) consent; (b) contract; (c) legal obligation; (d) vital interests; (e) public interest; (f) legitimate interests (does not override fundamental rights of the data subject). For hiring tools the typical bases are (b) pre-contractual steps at the request of the data subject, or (f) legitimate interest with a balancing test.

## §Art.9 Special Categories
Processing of racial/ethnic origin, political opinions, religion, trade union membership, genetic/biometric data, health, sex life, or sexual orientation is prohibited unless a specific exception (e.g., explicit consent, employment law, substantial public interest) applies.

## §Art.13–14 Transparency
Data subjects must be informed at collection time of: identity of controller, purposes, legal basis, recipients, retention period, rights (access, rectification, erasure, restriction, portability, objection), and — critically — "the existence of automated decision-making, including profiling, referred to in Article 22(1) and (4) and, at least in those cases, meaningful information about the logic involved, as well as the significance and the envisaged consequences of such processing."

## §Art.22 Automated Individual Decision-Making
(1) The data subject shall have the right not to be subject to a decision based solely on automated processing, including profiling, which produces legal effects concerning him or her or similarly significantly affects him or her.
(2) Paragraph 1 shall not apply if the decision: (a) is necessary for entering into, or performance of, a contract; (b) is authorized by Union or Member State law; or (c) is based on the data subject's explicit consent.
(3) In cases (a) and (c), the controller shall implement suitable measures to safeguard the data subject's rights and freedoms and legitimate interests, at least the right to obtain human intervention, to express his or her point of view, and to contest the decision.
(4) Decisions referred to in paragraph 2 shall not be based on special categories of personal data under Article 9(1), unless point (a) or (g) of Article 9(2) applies.

Hiring application: An AI tool that auto-rejects candidates without human review is a "decision based solely on automated processing" with legal/significant effect. To be permissible it generally requires (a) explicit consent, (b) statutory authorization, or human-in-the-loop sufficient that the decision is not "solely" automated.

## §Art.35 Data Protection Impact Assessment (DPIA)
A DPIA is required where processing is "likely to result in a high risk to the rights and freedoms of natural persons", expressly including "a systematic and extensive evaluation of personal aspects relating to natural persons which is based on automated processing, including profiling, and on which decisions are based that produce legal effects or similarly significantly affect" the person. Hiring algorithms typically trigger this requirement.

## §Art.44–49 International Transfers
Transfers of personal data outside the EEA require an adequate level of protection — Commission adequacy decision, Standard Contractual Clauses (SCCs), Binding Corporate Rules, or another safeguard. EU candidate data sent to a US-based AI vendor falls under this regime.

## §Common Violations to Watch For
- Auto-rejecting EU candidates with no human review or appeal pathway.
- Failing to disclose use of automated decision-making in the privacy notice.
- Skipping a DPIA before deploying a hiring AI tool.
- Sending EU applicant data to a US vendor without SCCs or equivalent safeguards.
- Using video-analysis features that infer emotion or personality (special-category risk).
