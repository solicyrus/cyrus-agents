"""Stage 3 of Action Star: NYC Siege 3D — the tower final.

Floor 2: Data Center (data_center_level.DataCenterLevel, target 75 s)
Floor 3: Penthouse & Helipad (penthouse_level.PenthouseLevel, target 105 s,
         includes the Syndicate Boss fight)

New enemy archetypes live in enemy_archetypes.py (Enforcer / Marksman /
Boss); destructible cover in destructibles.py. Everything here builds on
the Stage-1/2 foundation: the shared CollisionWorld + Solid model from
level1.lobby_level, the StuntManager in logic/, and the HUD contract in
hud/ — nothing is duplicated or forked.
"""
