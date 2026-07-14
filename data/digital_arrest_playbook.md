# digital_arrest playbook structure (advisory-sourced)

Compiled from public reporting on official Indian government advisories
(MHA, I4C) and legal/financial-institution explainers, for grounding
`04_augment.py`'s synthetic `digital_arrest` generation. Not a direct quote
of any single advisory — cross-referenced across multiple sources listed at
the bottom. This file is the seed material `04_augment.py` reads; keep it
in sync with that script's prompts.

## Stage-by-stage structure

**1. Initial contact (maps to `s1_authority_claim`)**
Spoofed or automated call, caller ID mimics an official helpline. Caller
claims to be from CBI, ED, Customs, local Police, or (less often) TRAI/RBI.
Common opening hooks: Aadhaar number linked to a money-laundering case, a
parcel booked in the victim's name containing drugs/fake passports/illegal
goods, tax evasion, or a SIM card used for a crime.

**2. Escalation to video call + evidence theater (`s1_authority_claim` →
`s2_threat_urgency`)**
Call moves to WhatsApp or Skype video. Scammer appears in a uniform, in
front of a fake police-station or courtroom backdrop (sometimes a real
studio set), or uses a deepfaked face of a real officer. Shows a forged FIR,
arrest warrant, or "court order" on screen. States the matter is
sub-judice/non-bailable and confidential.

**3. Isolation (`s3_isolation`)**
Explicit scripted commands, e.g.:
- "Don't tell your family — this is sub-judice."
- "Stay on this video call 24x7 until verification is complete."
- "Do not disconnect or mute the call."
- "Do not contact a lawyer or anyone else — that will be treated as
  obstruction."
Victims have been kept on camera anywhere from a few hours to several days.

**4. Information harvest (`s4_info_harvest`)**
Requests Aadhaar/PAN "for verification," sometimes escalates to asking for
OTPs under the pretext of "confirming your identity with the bank."

**5. Payment demand (`s5_payment_demand`)**
Framed as proving innocence, not paying a bribe: "Transfer all funds to the
RBI/CBI safe account for verification, it will be refunded within 24 hours
once you're cleared." Account is typically UPI or a mule bank account.
Some cases pivot fully to direct account-draining via harvested OTPs
instead of a discrete "transfer."

## Agencies/authorities impersonated
CBI, ED (Enforcement Directorate), Customs, local/Mumbai/Delhi Police,
occasionally RBI or TRAI framed as coordinating with the "investigation."

## Scale and government response (context, not for generation)
I4C reported ~₹120.30 crore lost to digital arrest scams Jan–Apr 2024 and
said it had blocked 1,700+ Skype IDs and 59,000+ WhatsApp accounts tied to
this scam type. MHA issued a public advisory (March 2024) specifically
naming Police/CBI/RBI impersonation in digital arrest scams. A high-level
panel was later formed to address systemic gaps.

## Sources
- [PIB press release on digital arrest scams](https://www.pib.gov.in/Pressreleaseshare.aspx?PRID=2082761)
- [The420.in — Centre cracks down on digital arrest scams, I4C panel](https://the420.in/digital-arrest-scam-panel-mha-supreme-court-i4c/)
- [Business Standard — why educated users fall for digital arrest scams](https://www.business-standard.com/technology/tech-news/digital-arrest-scam-fear-educated-elderly-victim-users-fall-cyber-fraud-126062500485_1.html)
- [Cybernews — Indian train driver loses $29,000 in digital arrest scam](https://cybernews.com/cybercrime/indian-digital-arrest-aadhaar/)
- [WION Decodes — 5 red flags of digital arrest scams](https://www.wionews.com/trending/how-to-spot-a-digital-arrest-scam-before-you-lose-money-red-flags-you-cannot-miss-wion-decodes-1782465781683)

Note: `pib.gov.in` blocks automated fetches (403), so it's cited as the
official primary source per secondary reporting rather than fetched
directly — worth a manual read-through before using this in anything
judge-facing (README, demo narration).
