# Fixtures for task 6 — document understanding

`amazon-rejection-crewsheet.txt` is the real rejection Amazon sent on 11.09.2026 for CrewSheet
1.0.0. It is his own e-mail about his own app: allowed by the hackathon data rules (no client data,
no third party's personal information, nothing from social media). Screenshot links from the
original are dropped — they are private Amazon Photos URLs and do not belong in a public repo.

**Why this one is the hook.** Primary and Functionality validation both passed; the app died on
Content Policy with "IAP displays error", and Amazon's own next step points at the Purchasing
Service documentation. That is precisely the rule family the checker covers and nobody else does.
The cost is on the record: submitted 10.09 14:38 UTC, rejected 11.09 18:42 UTC, live 13.09 15:50
UTC with 1.0.2 — two days and two extra builds for something a static check would have caught
before the upload.

A second, different rejection exists if a contrast is wanted: **Scanly 1.0.2 and 1.0.3**, also
content policy, a different cause. Useful for showing the mapping is not hard-coded to one e-mail.
