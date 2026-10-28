#!/usr/bin/env python3
"""
Cat's Space Invaders — Python port 0.1
1:1 arcade-faithful Midway Space Invaders (1978) style fork.

  * import math + pygame-ce only (import pygame)
  * files = off — no PNG/WAV/JSON; sprites & audio generated in RAM
  * 5×11 grid, shields, UFO, lives, march tempo, scoring

Run:  python3 space4k1.x.py
"""

from __future__ import annotations

import array
import math
import random
import sys

import pygame

# ---------------------------------------------------------------------------
# Identity / arcade constants (Midway 1978 logical raster)
# ---------------------------------------------------------------------------
TITLE = "Cat's Space Invaders — Python port 0.1"
LOGICAL_W, LOGICAL_H = 224, 256
SCALE = 3
FPS = 60

# Playfield (classic cabinet was rotated; we keep upright Midway coords)
INV_COLS, INV_ROWS = 11, 5
INV_X0, INV_Y0 = 26, 48
INV_DX, INV_DY = 16, 16
STEP_X, STEP_Y = 2, 8

PLAYER_Y = 216
SHIELD_Y = 176
UFO_Y = 28

SCORE_SQUID, SCORE_CRAB, SCORE_OCTO = 30, 20, 10
UFO_SCORES = (50, 100, 150, 300)

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREEN = (32, 255, 32)
RED = (255, 48, 48)
CYAN = (0, 255, 255)
YELLOW = (255, 255, 64)
PURPLE = (200, 80, 255)


# ---------------------------------------------------------------------------
# Procedural audio engine (no files)
# ---------------------------------------------------------------------------
class AudioEngine:
    """Synthesizes arcade-ish beeps / noise bursts with pygame Sound buffers."""

    def __init__(self):
        self.enabled = True
        self._sr = 22050
        try:
            pygame.mixer.pre_init(self._sr, -16, 1, 512)
        except pygame.error:
            pass
        if not pygame.mixer.get_init():
            try:
                pygame.mixer.init(self._sr, -16, 1, 512)
            except pygame.error:
                self.enabled = False
                self._sr = 22050
        else:
            self._sr = pygame.mixer.get_init()[0] or 22050

        self.sfx = {}
        if self.enabled:
            self.sfx["shoot"] = self._square(880, 0.06, 0.35)
            self.sfx["inv_hit"] = self._noise(0.08, 0.4)
            self.sfx["player_hit"] = self._sweep(200, 60, 0.45, 0.5)
            self.sfx["ufo"] = self._square(160, 0.12, 0.25)
            self.sfx["ufo_hit"] = self._sweep(400, 100, 0.35, 0.45)
            self.sfx["bonus"] = self._square(1200, 0.05, 0.3)
            # Four-note march (speeds up with remaining invaders)
            self.march = [
                self._square(f, 0.09, 0.28) for f in (110, 98, 87, 78)
            ]
        self._march_i = 0
        self._march_t = 0.0

    def _buf(self, samples: array.array) -> pygame.mixer.Sound:
        return pygame.mixer.Sound(buffer=samples.tobytes())

    def _square(self, freq: float, dur: float, vol: float) -> pygame.mixer.Sound:
        n = max(1, int(self._sr * dur))
        amp = int(32000 * vol)
        period = max(1, int(self._sr / max(1.0, freq)))
        half = period // 2
        data = array.array("h")
        for i in range(n):
            data.append(amp if (i % period) < half else -amp)
        return self._buf(data)

    def _sweep(self, f0: float, f1: float, dur: float, vol: float) -> pygame.mixer.Sound:
        n = max(1, int(self._sr * dur))
        amp = int(28000 * vol)
        data = array.array("h")
        phase = 0.0
        for i in range(n):
            t = i / n
            freq = f0 + (f1 - f0) * t
            phase += 2 * math.pi * freq / self._sr
            # soft square
            v = amp if math.sin(phase) >= 0 else -amp
            # fade out
            v = int(v * (1.0 - t))
            data.append(v)
        return self._buf(data)

    def _noise(self, dur: float, vol: float) -> pygame.mixer.Sound:
        n = max(1, int(self._sr * dur))
        amp = int(24000 * vol)
        data = array.array("h")
        for i in range(n):
            fade = 1.0 - (i / n)
            data.append(int(random.randint(-amp, amp) * fade))
        return self._buf(data)

    def play(self, name: str):
        if not self.enabled:
            return
        snd = self.sfx.get(name)
        if snd:
            snd.play()

    def tick_march(self, dt: float, alive: int, total: int = 55):
        """Arcade march: interval shrinks as invaders die."""
        if not self.enabled or alive <= 0:
            return
        # Classic feel: ~0.9s full grid → ~0.15s near last alien
        ratio = alive / max(1, total)
        interval = 0.14 + 0.75 * ratio
        self._march_t += dt
        if self._march_t >= interval:
            self._march_t = 0.0
            self.march[self._march_i % 4].play()
            self._march_i += 1


# ---------------------------------------------------------------------------
# Sprite factory from bit grids (files = off)
# ---------------------------------------------------------------------------
def grid_surface(rows: list[str], color, scale: int = 1) -> pygame.Surface:
    h, w = len(rows), len(rows[0])
    surf = pygame.Surface((w * scale, h * scale), pygame.SRCALPHA)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch not in ". ":
                pygame.draw.rect(surf, color, (x * scale, y * scale, scale, scale))
    return surf


# Classic Midway-ish silhouettes (approximate 1:1 shapes)
SPIDER = [  # 30 pts — top row
    "....X....X....",
    "...XXXXXX.....",
    "..XXXXXXXX....",
    ".XX.XXXX.XX...",
    ".XXXXXXXXXX...",
    ".X.XXXXXX.X...",
    ".X.X....X.X...",
    "....XX.XX.....",
]
CRAB = [  # 20 pts
    "..X.....X.....",
    "...X...X......",
    "..XXXXXXX.....",
    ".XX.XXX.XX....",
    "XXXXXXXXXXX...",
    "X.XXXXXXX.X...",
    "X.X.....X.X...",
    "...XX.XX......",
]
OCTO = [  # 10 pts
    "....XXXX......",
    ".XXXXXXXXXX...",
    "XXXXXXXXXXXX..",
    "XXX..XX..XXX..",
    "XXXXXXXXXXXX..",
    "..XX....XX....",
    ".XX.XXXX.XX...",
    "XX........XX..",
]
SPIDER2 = [
    "....X....X....",
    "...XXXXXX.....",
    "..XXXXXXXX....",
    ".XX.XXXX.XX...",
    ".XXXXXXXXXX...",
    "..X.XXXX.X....",
    ".X........X...",
    "..X......X....",
]
CRAB2 = [
    "..X.....X.....",
    "X..X...X..X...",
    "X.XXXXXXX.X...",
    "XXX.XXX.XXX...",
    "XXXXXXXXXXX...",
    ".XXXXXXXXX....",
    "..X.....X.....",
    ".X.......X....",
]
OCTO2 = [
    "....XXXX......",
    ".XXXXXXXXXX...",
    "XXXXXXXXXXXX..",
    "XXX..XX..XXX..",
    "XXXXXXXXXXXX..",
    ".XXX....XXX...",
    "XX..XXXX..XX..",
    ".XX......XX...",
]
PLAYER = [
    ".......X.......",
    "......XXX......",
    "......XXX......",
    "..XXXXXXXXXXX..",
    ".XXXXXXXXXXXXX.",
    "XXXXXXXXXXXXXXX",
    "XXXXXXXXXXXXXXX",
    "XXXXXXXXXXXXXXX",
]
PLAYER_SHOT = ["X", "X", "X", "X"]
INV_SHOT_A = ["X", "X", ".", "X", "X", ".", "X"]
INV_SHOT_B = [".", "X", "X", ".", "X", "X", "."]
UFO = [
    ".....XXXXXX.....",
    "...XXXXXXXXXX...",
    "..XXXXXXXXXXXX..",
    ".XX.XX.XX.XX.XX.",
    "XXXXXXXXXXXXXXXX",
    "..XXX..XX..XXX..",
    "...X........X...",
]
EXPLODE = [
    "..X...X..X...",
    "X..X.X.X..X..",
    ".X..XXX..X...",
    "X.XXXXXXX.X..",
    ".X..XXX..X...",
    "X..X.X.X..X..",
    "..X...X..X...",
]
# Soft shield brick (erodes on hit)
BRICK = ["XXXX", "XXXX", "XXXX", "XXXX"]


def make_sprites():
    return {
        "squid": [grid_surface(SPIDER, WHITE), grid_surface(SPIDER2, WHITE)],
        "crab": [grid_surface(CRAB, WHITE), grid_surface(CRAB2, WHITE)],
        "octopus": [grid_surface(OCTO, WHITE), grid_surface(OCTO2, WHITE)],
        "player": grid_surface(PLAYER, GREEN),
        "player_shot": grid_surface(PLAYER_SHOT, WHITE),
        "inv_shot_a": grid_surface(INV_SHOT_A, WHITE),
        "inv_shot_b": grid_surface(INV_SHOT_B, WHITE),
        "ufo": grid_surface(UFO, RED),
        "explode": grid_surface(EXPLODE, YELLOW),
        "brick": grid_surface(BRICK, GREEN),
    }


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------
class Invader:
    __slots__ = ("col", "row", "kind", "alive", "rect")

    def __init__(self, col: int, row: int):
        self.col, self.row = col, row
        if row == 0:
            self.kind = "squid"
        elif row < 3:
            self.kind = "crab"
        else:
            self.kind = "octopus"
        self.alive = True
        self.rect = pygame.Rect(0, 0, 12, 8)

    def score(self) -> int:
        return {"squid": SCORE_SQUID, "crab": SCORE_CRAB, "octopus": SCORE_OCTO}[self.kind]


class Shield:
    """Pixel-eroding bunker (4 classic shields)."""

    def __init__(self, x: int, y: int):
        # 22×16 logical shield mask
        self.x, self.y = x, y
        self.w, self.h = 22, 16
        self.mask = [[1] * self.w for _ in range(self.h)]
        # Carve classic arch
        for yy in range(10, self.h):
            for xx in range(6, 16):
                if yy > 11:
                    self.mask[yy][xx] = 0
        self._dirty = True
        self.surf = pygame.Surface((self.w, self.h), pygame.SRCALPHA)

    def rebuild(self):
        self.surf.fill((0, 0, 0, 0))
        for yy in range(self.h):
            for xx in range(self.w):
                if self.mask[yy][xx]:
                    self.surf.set_at((xx, yy), GREEN)
        self._dirty = False

    def draw(self, dest: pygame.Surface):
        if self._dirty:
            self.rebuild()
        dest.blit(self.surf, (self.x, self.y))

    def hit(self, px: int, py: int, radius: int = 2) -> bool:
        lx, ly = px - self.x, py - self.y
        if not (0 <= lx < self.w and 0 <= ly < self.h):
            return False
        if not self.mask[ly][lx]:
            return False
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy > radius * radius + 1:
                    continue
                nx, ny = lx + dx, ly + dy
                if 0 <= nx < self.w and 0 <= ny < self.h:
                    self.mask[ny][nx] = 0
        self._dirty = True
        return True

    def collides_rect(self, r: pygame.Rect) -> bool:
        if r.right < self.x or r.left > self.x + self.w:
            return False
        if r.bottom < self.y or r.top > self.y + self.h:
            return False
        for yy in range(max(0, r.top - self.y), min(self.h, r.bottom - self.y)):
            for xx in range(max(0, r.left - self.x), min(self.w, r.right - self.x)):
                if self.mask[yy][xx]:
                    return True
        return False


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------
class CatsSpaceInvaders:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption(TITLE)
        self.screen = pygame.display.set_mode((LOGICAL_W * SCALE, LOGICAL_H * SCALE))
        self.clock = pygame.time.Clock()
        self.canvas = pygame.Surface((LOGICAL_W, LOGICAL_H))
        self.audio = AudioEngine()
        self.sprites = make_sprites()
        self.font = pygame.font.SysFont("Courier", 10, bold=True)
        self.font_lg = pygame.font.SysFont("Courier", 14, bold=True)
        self.reset_game(attract=True)

    def reset_game(self, attract: bool = False):
        self.state = "ATTRACT" if attract else "PLAYING"
        self.score = 0
        self.hi = getattr(self, "hi", 0)
        self.lives = 3
        self.wave = 1
        self.frame = 0
        self.anim = 0
        self.player_x = LOGICAL_W // 2 - 8
        self.player_alive = True
        self.player_shot = None  # Rect or None
        self.inv_shots: list[dict] = []
        self.explosions: list[dict] = []
        self.ufo = None
        self.ufo_cooldown = 18.0
        self.flash = 0
        self.message = ""
        self.message_t = 0.0
        self._build_wave()
        self._build_shields()

    def _build_wave(self):
        self.invaders: list[Invader] = []
        drop = min(24, (self.wave - 1) * 8)
        for row in range(INV_ROWS):
            for col in range(INV_COLS):
                inv = Invader(col, row)
                inv.rect.topleft = (INV_X0 + col * INV_DX, INV_Y0 + drop + row * INV_DY)
                self.invaders.append(inv)
        self.dir = 1
        self.move_accum = 0.0
        self.fire_accum = 0.0
        self.base_move = 0.55  # seconds between steps at full grid
        self.shot_cooldown = 0.0

    def _build_shields(self):
        xs = [32, 72, 112, 152]
        self.shields = [Shield(x, SHIELD_Y) for x in xs]

    def alive_invaders(self) -> list[Invader]:
        return [i for i in self.invaders if i.alive]

    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            self.frame += 1
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit(0)
                if ev.type == pygame.KEYDOWN:
                    self._keydown(ev.key)
            self._update(dt)
            self._draw()
            scaled = pygame.transform.scale(self.canvas, self.screen.get_size())
            self.screen.blit(scaled, (0, 0))
            pygame.display.flip()

    def _keydown(self, key: int):
        if key in (pygame.K_ESCAPE, pygame.K_q):
            pygame.quit()
            sys.exit(0)
        if self.state == "ATTRACT" and key in (pygame.K_RETURN, pygame.K_SPACE):
            self.reset_game(attract=False)
        elif self.state == "GAME_OVER" and key in (pygame.K_RETURN, pygame.K_SPACE):
            self.reset_game(attract=True)
        elif self.state == "WAVE_CLEAR" and key in (pygame.K_RETURN, pygame.K_SPACE):
            self.wave += 1
            self.state = "PLAYING"
            self._build_wave()
            self._build_shields()
            self.player_shot = None
            self.inv_shots.clear()

    def _update(self, dt: float):
        if self.message_t > 0:
            self.message_t -= dt
        if self.flash > 0:
            self.flash -= dt

        if self.state == "ATTRACT":
            self.anim = (self.frame // 30) % 2
            return

        if self.state in ("GAME_OVER", "WAVE_CLEAR", "PLAYER_HIT"):
            if self.state == "PLAYER_HIT":
                self.message_t -= 0  # handled below
            self.anim = (self.frame // 20) % 2
            # wait timer for player hit
            if self.state == "PLAYER_HIT":
                if not hasattr(self, "_hit_timer"):
                    self._hit_timer = 1.4
                self._hit_timer -= dt
                if self._hit_timer <= 0:
                    del self._hit_timer
                    if self.lives <= 0:
                        self.state = "GAME_OVER"
                        self.hi = max(self.hi, self.score)
                        self.message = "GAME OVER"
                        self.message_t = 999
                    else:
                        self.state = "PLAYING"
                        self.player_alive = True
                        self.player_x = LOGICAL_W // 2 - 8
                        self.player_shot = None
                        self.inv_shots.clear()
            return

        keys = pygame.key.get_pressed()
        speed = 80
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.player_x -= speed * dt
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.player_x += speed * dt
        self.player_x = max(8, min(LOGICAL_W - 24, self.player_x))

        # Fire (one shot on screen — arcade rule)
        self.shot_cooldown = max(0.0, self.shot_cooldown - dt)
        fire = keys[pygame.K_SPACE] or keys[pygame.K_UP] or keys[pygame.K_w]
        if fire and self.player_shot is None and self.player_alive and self.shot_cooldown <= 0:
            self.player_shot = pygame.Rect(int(self.player_x) + 7, PLAYER_Y - 6, 1, 4)
            self.audio.play("shoot")
            self.shot_cooldown = 0.05

        # Move player shot
        if self.player_shot:
            self.player_shot.y -= int(180 * dt)
            if self.player_shot.bottom < 16:
                self.player_shot = None
            else:
                self._player_shot_collisions()

        alive = self.alive_invaders()
        self.audio.tick_march(dt, len(alive))

        # Invader formation step
        if alive:
            ratio = len(alive) / 55.0
            interval = 0.12 + self.base_move * ratio
            # Later waves slightly faster
            interval *= max(0.55, 1.0 - (self.wave - 1) * 0.06)
            self.move_accum += dt
            if self.move_accum >= interval:
                self.move_accum = 0.0
                self.anim ^= 1
                self._step_invaders(alive)

            # Invader fire
            self.fire_accum += dt
            fire_every = 0.35 + 0.9 * ratio
            if self.fire_accum >= fire_every and len(self.inv_shots) < 3:
                self.fire_accum = 0.0
                self._invader_fire(alive)

        # Invader shots
        for shot in self.inv_shots[:]:
            shot["rect"].y += shot["vy"] * dt
            shot["phase"] = (shot["phase"] + dt * 12) % 2
            if shot["rect"].top > LOGICAL_H:
                self.inv_shots.remove(shot)
                continue
            if self._inv_shot_hit(shot):
                if shot in self.inv_shots:
                    self.inv_shots.remove(shot)

        # UFO
        self.ufo_cooldown -= dt
        if self.ufo is None and self.ufo_cooldown <= 0 and alive:
            direction = random.choice((-1, 1))
            x = -20 if direction > 0 else LOGICAL_W + 4
            self.ufo = {"x": float(x), "dir": direction, "wiggle": 0.0}
            self.ufo_cooldown = random.uniform(12.0, 22.0)
            self.audio.play("ufo")
        if self.ufo:
            self.ufo["x"] += self.ufo["dir"] * 40 * dt
            self.ufo["wiggle"] += dt
            if self.ufo["x"] < -24 or self.ufo["x"] > LOGICAL_W + 24:
                self.ufo = None

        # Wave clear
        if not alive:
            self.state = "WAVE_CLEAR"
            self.message = f"WAVE {self.wave} CLEARED"
            self.message_t = 999
            self.audio.play("bonus")

        # Invaders reached player line
        for inv in alive:
            if inv.rect.bottom >= PLAYER_Y:
                self._player_die()
                break

        # Expire explosions
        for ex in self.explosions[:]:
            ex["t"] -= dt
            if ex["t"] <= 0:
                self.explosions.remove(ex)

    def _step_invaders(self, alive: list[Invader]):
        # Edge detect
        min_x = min(i.rect.left for i in alive)
        max_x = max(i.rect.right for i in alive)
        drop = False
        if self.dir > 0 and max_x + STEP_X >= LOGICAL_W - 8:
            drop = True
        elif self.dir < 0 and min_x - STEP_X <= 8:
            drop = True
        if drop:
            self.dir *= -1
            for inv in alive:
                inv.rect.y += STEP_Y
        else:
            for inv in alive:
                inv.rect.x += STEP_X * self.dir

    def _invader_fire(self, alive: list[Invader]):
        # Prefer bottom-most invader per column (arcade)
        cols: dict[int, Invader] = {}
        for inv in alive:
            cur = cols.get(inv.col)
            if cur is None or inv.rect.y > cur.rect.y:
                cols[inv.col] = inv
        if not cols:
            return
        shooter = random.choice(list(cols.values()))
        rect = pygame.Rect(shooter.rect.centerx, shooter.rect.bottom, 1, 6)
        self.inv_shots.append({"rect": rect, "vy": 70 + random.random() * 20, "phase": 0})

    def _player_shot_collisions(self):
        assert self.player_shot is not None
        r = self.player_shot

        # UFO
        if self.ufo:
            urect = pygame.Rect(int(self.ufo["x"]), UFO_Y, 16, 7)
            if r.colliderect(urect):
                # Arcade mystery ship: weighted 50/100/150/300
                pts = random.choices(UFO_SCORES, weights=[4, 3, 2, 1], k=1)[0]
                self.score += pts
                self.explosions.append({"pos": urect.center, "t": 0.4})
                self.audio.play("ufo_hit")
                self.ufo = None
                self.player_shot = None
                return

        # Invaders
        for inv in self.invaders:
            if inv.alive and r.colliderect(inv.rect):
                inv.alive = False
                self.score += inv.score()
                self.explosions.append({"pos": inv.rect.center, "t": 0.25})
                self.audio.play("inv_hit")
                self.player_shot = None
                return

        # Shields
        for sh in self.shields:
            if sh.collides_rect(r):
                sh.hit(r.centerx, r.top, radius=2)
                self.player_shot = None
                return

    def _inv_shot_hit(self, shot: dict) -> bool:
        r = shot["rect"]
        # Shields
        for sh in self.shields:
            if sh.collides_rect(r):
                sh.hit(r.centerx, r.bottom, radius=2)
                return True
        # Player
        if self.player_alive:
            prect = pygame.Rect(int(self.player_x), PLAYER_Y, 15, 8)
            if r.colliderect(prect):
                self._player_die()
                return True
        return False

    def _player_die(self):
        if not self.player_alive:
            return
        self.player_alive = False
        self.lives -= 1
        self.player_shot = None
        self.inv_shots.clear()
        self.explosions.append({"pos": (int(self.player_x) + 7, PLAYER_Y + 4), "t": 0.6})
        self.audio.play("player_hit")
        self.flash = 0.3
        self.state = "PLAYER_HIT"
        self._hit_timer = 1.5

    # ------------------------------------------------------------------ draw
    def _draw(self):
        self.canvas.fill(BLACK)
        # Scanline vibe
        if self.flash > 0:
            self.canvas.fill((40, 0, 0))

        # HUD
        self._blit_text(f"SCORE {self.score:04d}", 8, 4, GREEN)
        self._blit_text(f"HI {self.hi:04d}", 90, 4, CYAN)
        self._blit_text(f"WAVE {self.wave}", 160, 4, YELLOW)

        # Lives as mini tanks
        for i in range(max(0, self.lives)):
            mini = pygame.transform.scale(self.sprites["player"], (12, 6))
            self.canvas.blit(mini, (8 + i * 16, LOGICAL_H - 12))

        # Shields
        for sh in self.shields:
            sh.draw(self.canvas)

        # Invaders
        for inv in self.invaders:
            if not inv.alive:
                continue
            frames = self.sprites[inv.kind]
            self.canvas.blit(frames[self.anim % 2], inv.rect.topleft)

        # UFO
        if self.ufo:
            self.canvas.blit(self.sprites["ufo"], (int(self.ufo["x"]), UFO_Y))

        # Player
        if self.player_alive and self.state not in ("GAME_OVER",):
            self.canvas.blit(self.sprites["player"], (int(self.player_x), PLAYER_Y))

        # Shots
        if self.player_shot:
            self.canvas.blit(self.sprites["player_shot"], self.player_shot.topleft)
        for shot in self.inv_shots:
            spr = self.sprites["inv_shot_a" if int(shot["phase"]) == 0 else "inv_shot_b"]
            self.canvas.blit(spr, shot["rect"].topleft)

        # Explosions
        for ex in self.explosions:
            self.canvas.blit(self.sprites["explode"], (ex["pos"][0] - 6, ex["pos"][1] - 4))

        # Green line above lives (arcade)
        pygame.draw.line(self.canvas, GREEN, (0, LOGICAL_H - 16), (LOGICAL_W, LOGICAL_H - 16))

        if self.state == "ATTRACT":
            self._center("CAT'S SPACE INVADERS", 88, GREEN)
            self._center("PYTHON PORT 0.1", 104, CYAN)
            self._center("* SCORE ADVANCE TABLE *", 128, WHITE)
            self._center("= 30 POINTS", 148, WHITE)
            self.canvas.blit(self.sprites["squid"][self.anim % 2], (70, 146))
            self._center("= 20 POINTS", 168, WHITE)
            self.canvas.blit(self.sprites["crab"][self.anim % 2], (70, 166))
            self._center("= 10 POINTS", 188, WHITE)
            self.canvas.blit(self.sprites["octopus"][self.anim % 2], (70, 186))
            if (self.frame // 40) % 2 == 0:
                self._center("PRESS ENTER", 220, YELLOW)
            self._center("ARROWS/A D MOVE  SPACE FIRE", 240, PURPLE)

        elif self.state == "WAVE_CLEAR":
            self._center(self.message or "WAVE CLEAR", 110, GREEN)
            self._center("PRESS ENTER", 130, YELLOW)

        elif self.state == "GAME_OVER":
            self._center("GAME OVER", 110, RED)
            self._center(f"SCORE {self.score:04d}", 130, WHITE)
            self._center("PRESS ENTER", 150, YELLOW)

        # Title watermark
        if self.state == "PLAYING":
            pass

    def _blit_text(self, text: str, x: int, y: int, color):
        surf = self.font.render(text, True, color)
        self.canvas.blit(surf, (x, y))

    def _center(self, text: str, y: int, color):
        surf = self.font_lg.render(text, True, color)
        self.canvas.blit(surf, ((LOGICAL_W - surf.get_width()) // 2, y))


def main():
    print(TITLE)
    print("files=off | math + pygame-ce | arcade Midway 1978 style")
    game = CatsSpaceInvaders()
    game.run()


if __name__ == "__main__":
    main()
