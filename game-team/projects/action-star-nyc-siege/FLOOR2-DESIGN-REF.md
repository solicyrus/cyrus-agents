# Floor 2 & Enemy Design — REFERENCE (from Cyrus's Gemini mock, 2026-10-27)

Status: DESIGN REFERENCE for Stage 3 — not built yet, and its point values are
NOT approved into the official Stunt Matrix (dodge 50 / slide 100 / air 150 /
wall 200). Environmental/enemy bonuses below need Cyrus's explicit approval
before entering the rating system.

## Floor 2 — Data Center (mock "Stage 3.2 Tower Assault")
Note: the GDD tower plan calls Floor 2 "Offices (stealth, patrolling guards)".
This mock renames it Data Center with environmental hazards — design evolution
to settle at the Stage-3 design pass.

Layout: 3 server racks. Environmental hazards (3 active):
- H1 High-Voltage Conduit — electrocutes nearby hostiles upon heavy slam (+250 PTS, unapproved)
- H2 Fragile Glass Racks — shrapnel area damage when thrown (+150 PTS, unapproved)
- H3 Pressure Vent Valves — blinds & stuns target on impact (+200 PTS, unapproved)

Also referenced: Penthouse & Helipad (upper floors).

## Enemy units
- HEAVY: **Riot Enforcer** — Shield & Baton. 850 HP. Ballistic Shield.
  Counter move: Vault-Slam. Threat: Moderate. Defeat stunt bonus +450 PTS (unapproved).
  AI: advances aggressively behind shield; blocks ALL frontal light attacks;
  vulnerability window 1.8s during heavy-swing recovery.
  Optimal counter sequence: (1) Jump-Kick off High-Voltage Conduit to stagger the
  shield, (2) Vault-Slam over depleted armor, (3) finish with a Glass Rack
  environmental slam.
- RANGED: **Elite Marksman** — Laser Precision.
- STAGE BOSS: **Commander Vane** — Dual Kinetic Pistols.
