# Action Star: NYC Siege 3D — HUD & Rating Spec (Cyrus, 2026-10-27)

Official UI layout and final-rating formula, as declared by Cyrus. This document
governs over any mock values (an earlier Gemini HUD preview used different stunt
points — 150/250/300 — those are NOT approved; the matrix below is).

## Final Take Rating

S_total = S_time + (S_stunt × M_combo)

- **S_time** = max(0, (T_target − T_actual) × 100). (Approved final formula, Cyrus
  2026-10-27 — supersedes the earlier 1000 + 20×remaining draft and the HUD mock's
  numbers. Check: 85s vs 120s target → 3,500.)
- **S_stunt** = sum of base points P_i: Bullet Dodge 50 · Slide & Shoot 100 ·
  Air Takedown 150 · Wall-Run Kill 200. Multi-Kill Combo (3 kills < 2s): ×2–×5.
- **M_combo** = diversity multiplier: +0.5 for each action differing from the last 3,
  cap 5.0; reset on taking a hit.

## Rank thresholds

| Rank | S_total | Cinematic title |
|---|---|---|
| S (Superstar) | ≥ 15,000 | Perfect Take |
| A (Action Hero) | 10,000 – 14,999 | Box Office Hit |
| B (Stunt Double) | 6,000 – 9,999 | Good Take |
| C (Extra) | 3,000 – 5,999 | Wrap Scene |
| F (Failed Test) | < 3,000 | Re-take Required |

## HUD layout

Top-left (health + bullet time):
```
[HP: |||||||||| 100%]
[BULLET TIME: ████████░░ 80%] ⚡ READY (L-SHIFT)
```
Bullet Time key: **L-SHIFT**.

Top-right (live time + score):
```
⏱️ TIME: 01:25.30 (Target: 02:00.00)
⭐ STUNT SCORE: 12,450
🔥 COMBO: 3.5x [WALL-RUN + AIR TAKEDOWN]
```

Bottom-center (live stunt feed):
```
+200 PTS  ⚡ WALL-RUN KILL
+150 PTS  💥 AIR TAKEDOWN
[ COMBO MULTIPLIER INCREASED TO 3.5x ]
```
