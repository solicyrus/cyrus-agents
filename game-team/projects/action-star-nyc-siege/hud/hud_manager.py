"""HUDManager — live HUD for Action Star: NYC Siege 3D (Ursina).

Implements the approved HUD layout from HUD-SPEC.md (this project folder):

  Top-left ...... HP bar + Bullet Time charge bar (% + READY state, L-SHIFT)
  Top-right ..... live TIME mm:ss.ms (Target mm:ss), STUNT SCORE, COMBO
  Bottom-center . floating stunt notification feed (rises, fades, expires)

Usage (the game owns the app and the frame loop):

    app = Ursina(...)
    hud = HUDManager(target_s=120.0)
    # every frame:
    hud.update_state(hp=hp, bullet_charge=charge, elapsed_s=elapsed,
                     target_s=120.0, stunt_score=score, combo=mult,
                     last_actions=["WALL-RUN KILL"])
    # on a stunt event:
    hud.notify(200, "WALL-RUN KILL")
    # when the combo multiplier changes:
    hud.set_combo(3.5)          # announces increases in the feed

Rendering cost is kept flat: every entity is created once in __init__ —
the notification feed is a fixed pool of Text entities that are recycled,
never created or destroyed per frame. update_state() only rewrites a text
when its rendered content actually changed.
"""

from ursina import Entity, Text, camera, color, time, window

# --------------------------------------------------------------------------
# Layout / behaviour constants (UI space: y in [-0.5, 0.5], x in
# [-aspect/2, aspect/2]; positions are computed from the live aspect ratio)
# --------------------------------------------------------------------------
BAR_WIDTH = 0.34            # UI units, HP / Bullet Time bars
BAR_HEIGHT = 0.022
FEED_SLOTS = 6              # fixed pool size for the notification feed
FEED_LIFETIME = 2.6         # seconds a feed entry stays on screen
FEED_RISE = 0.15            # UI units an entry rises over its lifetime
FEED_LINE_HEIGHT = 0.052    # vertical spacing between stacked feed entries
FEED_BASE_Y = -0.30         # bottom-center feed anchor

HP_COLOR_HIGH = color.rgb32(64, 200, 90)
HP_COLOR_MID = color.rgb32(240, 190, 40)
HP_COLOR_LOW = color.rgb32(230, 60, 50)
BAR_BACK_COLOR = color.rgba32(10, 10, 14, 170)
BULLET_COLOR = color.rgb32(50, 170, 255)
BULLET_READY_COLOR = color.rgb32(255, 205, 40)

# Spec icons for the stunt feed (HUD-SPEC.md shows exactly these two).
ACTION_ICONS = {
    "WALL-RUN KILL": "⚡",
    "AIR TAKEDOWN": "💥",
}
DEFAULT_ICON = "⚡"


def format_time(seconds: float) -> str:
    """Format seconds as mm:ss.ms (e.g. 85.3 -> '01:25.30')."""
    if seconds < 0:
        seconds = 0.0
    minutes = int(seconds // 60)
    rest = seconds - minutes * 60
    return f"{minutes:02d}:{rest:05.2f}"


def _bar(parent, x, y, width, height, fill_color):
    """Create a (background, fill) pair of UI quads anchored at the left."""
    back = Entity(model="quad", parent=parent, position=(x, y, 0),
                  origin=(-0.5, 0.5), scale=(width, height),
                  color=BAR_BACK_COLOR)
    fill = Entity(model="quad", parent=parent, position=(x, y, -0.01),
                  origin=(-0.5, 0.5), scale=(width, height),
                  color=fill_color)
    return back, fill


class _FeedEntry:
    """One pooled feed slot: a Text entity plus its animation state."""

    __slots__ = ("text", "age", "active", "kind")

    def __init__(self, text_entity):
        self.text = text_entity
        self.age = 0.0
        self.active = False
        self.kind = "stunt"     # "stunt" or "combo"


class HUDManager:
    """Live HUD renderer. Construct after the Ursina app exists."""

    def __init__(self, target_s: float = 120.0):
        self._ui = camera.ui
        aspect = window.aspect_ratio
        left = -aspect / 2 + 0.035
        right = aspect / 2 - 0.035
        self._target_s = float(target_s)

        # ------------------------- state cache -------------------------
        self._hp = 100.0
        self._bullet_charge = 100.0
        self._elapsed_s = 0.0
        self._stunt_score = 0
        self._combo = 1.0
        self._last_actions = []
        self._shown = {}        # name -> last rendered string (change guard)

        # ------------------------- top-left ----------------------------
        self.hp_label = Text(text="", position=(left, 0.485),
                             origin=(-0.5, 0.5), scale=1.25,
                             color=color.white, parent=self._ui)
        self._hp_back, self.hp_fill = _bar(self._ui, left, 0.452,
                                           BAR_WIDTH, BAR_HEIGHT,
                                           HP_COLOR_HIGH)
        self.bullet_label = Text(text="", position=(left, 0.418),
                                 origin=(-0.5, 0.5), scale=1.25,
                                 color=color.white, parent=self._ui)
        self._bullet_back, self.bullet_fill = _bar(
            self._ui, left, 0.385, BAR_WIDTH, BAR_HEIGHT, BULLET_COLOR)
        self.bullet_status = Text(text="", position=(left, 0.352),
                                  origin=(-0.5, 0.5), scale=1.15,
                                  color=BULLET_READY_COLOR, parent=self._ui)

        # ------------------------- top-right ---------------------------
        self.time_text = Text(text="", position=(right, 0.485),
                              origin=(0.5, 0.5), scale=1.35,
                              color=color.white, parent=self._ui)
        self.score_text = Text(text="", position=(right, 0.432),
                               origin=(0.5, 0.5), scale=1.35,
                               color=color.yellow, parent=self._ui)
        self.combo_text = Text(text="", position=(right, 0.379),
                               origin=(0.5, 0.5), scale=1.25,
                               color=color.orange, parent=self._ui)

        # ------------------- bottom-center feed pool -------------------
        self._feed = []
        for i in range(FEED_SLOTS):
            t = Text(text="", position=(0, FEED_BASE_Y - i * FEED_LINE_HEIGHT),
                     origin=(0, 0.5), scale=1.45, color=color.white,
                     parent=self._ui)
            t.enabled = False
            self._feed.append(_FeedEntry(t))
        self.total_notifications = 0   # every notify()/announcement spawned
        self.total_expired = 0         # entries that lived out their lifetime

        # First paint so nothing is blank on frame one.
        self._render_static()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def update_state(self, hp, bullet_charge, elapsed_s, target_s,
                     stunt_score, combo, last_actions):
        """Feed the current game state in; call once per frame."""
        self._hp = max(0.0, min(100.0, float(hp)))
        self._bullet_charge = max(0.0, min(100.0, float(bullet_charge)))
        self._elapsed_s = float(elapsed_s)
        self._target_s = float(target_s)
        self._stunt_score = int(stunt_score)
        self._last_actions = list(last_actions or [])
        if float(combo) != self._combo:
            self.set_combo(combo)
        self._advance_feed(time.dt)
        self._render_static()

    def set_combo(self, value):
        """Set the combo multiplier; an increase is announced in the feed."""
        new_value = float(value)
        increased = new_value > self._combo
        self._combo = new_value
        self._render_static()
        if increased:
            self._spawn(f"[ COMBO MULTIPLIER INCREASED TO {new_value:.1f}x ]",
                        kind="combo")

    def notify(self, points, label):
        """Spawn a floating stunt entry, e.g. notify(200, 'WALL-RUN KILL')."""
        label = str(label).strip().upper()
        icon = ACTION_ICONS.get(label, DEFAULT_ICON)
        self._spawn(f"+{int(points)} PTS  {icon} {label}", kind="stunt")

    def active_feed_count(self) -> int:
        return sum(1 for e in self._feed if e.active)

    def feed_texts(self):
        """Current visible feed strings (oldest pool order) — for QA/tools."""
        return [e.text.text for e in self._feed if e.active]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _spawn(self, text_value, kind):
        entry = next((e for e in self._feed if not e.active), None)
        if entry is None:                       # pool full: reuse the oldest
            entry = max(self._feed, key=lambda e: e.age)
        entry.text.text = text_value
        entry.text.color = color.orange if kind == "combo" else color.white
        entry.age = 0.0
        entry.kind = kind
        entry.active = True
        entry.text.enabled = True
        entry.text.alpha = 1.0
        self.total_notifications += 1
        self._layout_feed()

    def _advance_feed(self, dt):
        if dt <= 0:
            return
        for entry in self._feed:
            if not entry.active:
                continue
            entry.age += dt
            if entry.age >= FEED_LIFETIME:
                entry.active = False
                entry.text.enabled = False
                self.total_expired += 1
        self._layout_feed()

    def _layout_feed(self):
        """Stack active entries at bottom-center with rise + fade applied."""
        slot = 0
        for entry in self._feed:
            if not entry.active:
                continue
            progress = entry.age / FEED_LIFETIME
            y = FEED_BASE_Y - slot * FEED_LINE_HEIGHT + progress * FEED_RISE
            entry.text.position = (0, y)
            # Hold full opacity for the first 55% of life, then fade out.
            entry.text.alpha = 1.0 if progress < 0.55 else \
                max(0.0, 1.0 - (progress - 0.55) / 0.45)
            slot += 1

    def _set_text(self, name, entity, value):
        if self._shown.get(name) != value:
            entity.text = value
            self._shown[name] = value

    def _render_static(self):
        """Refresh bars + readouts; text is rewritten only when changed."""
        hp_pct = self._hp
        self._set_text("hp", self.hp_label, f"HP: {hp_pct:.0f}%")
        self.hp_fill.scale = (BAR_WIDTH * hp_pct / 100.0, BAR_HEIGHT)
        self.hp_fill.color = (HP_COLOR_HIGH if hp_pct > 50 else
                              HP_COLOR_MID if hp_pct > 25 else HP_COLOR_LOW)

        charge = self._bullet_charge
        self._set_text("bt", self.bullet_label, f"BULLET TIME: {charge:.0f}%")
        self.bullet_fill.scale = (BAR_WIDTH * charge / 100.0, BAR_HEIGHT)
        ready = charge >= 100.0
        self.bullet_fill.color = BULLET_READY_COLOR if ready else BULLET_COLOR
        self._set_text("bt_status", self.bullet_status,
                       "⚡ READY (L-SHIFT)" if ready else "(L-SHIFT)")

        self._set_text("time", self.time_text,
                       f"⏱️ TIME: {format_time(self._elapsed_s)} "
                       f"(Target: {format_time(self._target_s)})")
        self._set_text("score", self.score_text,
                       f"⭐ STUNT SCORE: {self._stunt_score:,}")
        actions = " + ".join(
            a.replace("_", "-").upper() for a in self._last_actions[-2:])
        combo_str = f"🔥 COMBO: {self._combo:.1f}x"
        if actions:
            combo_str += f" [{actions}]"
        self._set_text("combo", self.combo_text, combo_str)
