# Action Star: NYC Siege 3D — Game Design Document (GDD)

> سند طراحی بازی — خروجی واقعی ایجنت طراح استودیو (game_designer_agent) از روی مشخصات اعلام‌شده‌ی سایرس، شامل ارتقای سیستم امتیازدهی «بدلکاری هالیوودی». اعتبارسنجی ماشینی: ۱۳ از ۱۳ بخش کامل، صفر نقص. پلتفرم هدف فعلی: PC / Python Desktop (موبایل بعداً).

## 1. Title
Action Star: NYC Siege 3D

## 2. Pitch
Infiltrate a skyscraper in New York City, combining shooting, melee combat, and cinematic stunts to defeat enemies and escape in record time.

## 3. Genre
3D Action

## 4. Platform
PC (Python desktop) — current target: PC / Python desktop first; mobile later.

## 5. Core Loop
Navigate through levels, engage in combat using shooting and melee skills, utilize Bullet Time for strategic advantage, and complete objectives to progress.

## 6. Mechanics
- Third-person perspective with dynamic camera angles.
- Shooting mechanics with aim assist and recoil control.
- Melee combat with combos and finishers.
- Bullet Time ability to slow down time for dodging and executing stunts.
- Time-Attack metric for level completion.
- Health system with regeneration over time or through pickups.
- Stealth elements to avoid detection by enemies.

## 7. Scoring System
Final Take Rating = Base Time Bonus + Stunt Score. Base Time Bonus: Points awarded for time remaining under the stage time cap. Stunt Matrix: Bullet Dodge +50, Slide & Shoot +100, Air Takedown +150, Wall-Run Kill +200. Multi-Kill Combo: 3 kills within 2 seconds earns a multiplier from x2 up to x5. Combo/diversity rule: each unique stunt action raises the combo multiplier by +0.5, capped at 5.0; points added = base points x current multiplier; combo resets when the player takes a hit. Ranks: S (1000+), A (800-999), B (600-799), C (400-599), F (<400).

## 7b. Stunt Scoring & Combo Mechanics (dedicated treatment)
Scoring in this game is a Hollywood stunt-scene evaluation, not a plain speedrun score. Full machine text (designer's `scoring_system`, the source of this section):

> Final Take Rating = Base Time Bonus + Stunt Score. Base Time Bonus: Points awarded for time remaining under the stage time cap. Stunt Matrix: Bullet Dodge +50, Slide & Shoot +100, Air Takedown +150, Wall-Run Kill +200. Multi-Kill Combo: 3 kills within 2 seconds earns a multiplier from x2 up to x5. Combo/diversity rule: each unique stunt action raises the combo multiplier by +0.5, capped at 5.0; points added = base points x current multiplier; combo resets when the player takes a hit. Ranks: S (1000+), A (800-999), B (600-799), C (400-599), F (<400).

**Final Take Rating formula**
- Final Take Rating = Base Time Bonus + Stunt Score.
- Base Time Bonus: points from the time remaining under the stage time cap when the exit is reached.
- Rank thresholds (designer-proposed rating formula, to be tuned in playtesting): **S = 1000+**, **A = 800–999**, **B = 600–799**, **C = 400–599**, **F = below 400**.

**Stunt Matrix (base points — Cyrus's declared values)**

| Stunt action | Base points | Trigger |
|---|---|---|
| Bullet Dodge | +50 | Dodging a bullet while in Bullet Time |
| Slide & Shoot | +100 | A kill while sliding |
| Air Takedown | +150 | Melee throw of an enemy from a window / height |
| Wall-Run Kill | +200 | A kill while wall-running |
| Multi-Kill Combo | multiplier x2 to x5 | 3 kills within 2 seconds |

**Combo / diversity rule (StuntManager semantics — Cyrus's declared rule)**
- Each registered stunt action that differs from the last 3 actions raises the combo multiplier by **+0.5**, capped at **5.0**.
- Points added for an action = base points x current multiplier.
- The combo resets when the player takes a hit.

## 8. Physics Rules
Bullet Time slows time to 0.3x normal speed. Energy drains at 10% per second while active, recharges at 5% per second when inactive. Cooldown of 5 seconds after deactivation. Gravity affects all objects and characters, with realistic physics for falling and thrown objects.

Bullet Time summary: time-scale 0.3x while active; energy drains 10%/s while active and recharges 5%/s while inactive; 5-second cooldown after deactivation.

## 9. Controls
WASD for movement, mouse for aiming, left click to shoot, right click for melee, spacebar to jump, shift to sprint, Q to activate Bullet Time, E for interactions, R to reload, C to crouch.

Bullet Time activation key: **Q**.

## 10. Win Conditions
Reach the exit of the level within the time limit.

Time-Attack: the run timer is a count-up race timer; the best-time record is kept between runs, and beating the stage time cap is the acting-test pass criterion.

## 11. Lose Conditions
Player's health reaches zero or player is detected by security systems.

## 12. Levels — Level 1 Tower Structure
- Floor 1: Lobby - Initial enemy encounter, tutorial on basic controls.
- Floor 2: Offices - Stealth section with patrolling guards.
- Floor 3: Security Room - Disable security systems to proceed.
- Floor 4: Executive Suites - Intense combat with elite enemies.
- Floor 5: Rooftop - Final showdown and escape via helicopter.

## 13. Art & Sound Direction
Realistic 3D environments with high-detail textures. Dynamic lighting and shadow effects. Intense and cinematic soundtrack with action-oriented sound effects. Voice acting for main character and key enemies.

---

## Open items (honest notes — NOT in the machine GDD)
- Rank thresholds in section 7b (S/A/B/C/F point bands) are the designer's proposed formula values; they will be re-tuned once Level 1 is playable and real score ranges are known.
- Enemy counts per floor, health/damage numbers and weapon stats are not yet fixed — they belong to the Level 1 slice design pass.
- The stage time cap per floor (the number the Base Time Bonus is measured against) is not yet set numerically.
