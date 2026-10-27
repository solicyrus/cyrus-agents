"""Level 1 (Tower Lobby) package for Action Star: NYC Siege 3D.

Modules:
    lobby_level ......... 3D lobby geometry, shared collision world,
                          cinematic lighting, third-person camera rig.
    player_controller_3d  WASD + mouse third-person controller wired to
                          StuntManager / HUDManager (shooting, melee,
                          slide, Bullet Time on L-SHIFT).
    enemy_ai_3d ......... armed guards (patrol / alert / engage) and the
                          projectile manager their bullets fly through.
    main ................ game assembly (GameSession) + human entry point.
"""
