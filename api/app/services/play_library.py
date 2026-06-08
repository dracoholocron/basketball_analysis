"""
Procedural play library — DSL that expands compact play definitions into
full svg_data v2 JSON understood by the frontend Play Builder.

Canvas: viewBox "0 0 500 280"
  Left basket:   x≈15,  y=140
  Right basket:  x≈485, y=140
  Left 3PT arc: approximately x=95, y=55–225
  Right 3PT arc: x=405
  Paint left:   x=2–97,  y=89–191
  Paint right:  x=403–498, y=89–191
  Mid-court:    x=250

Player IDs p1..p5 = PG,SG,SF,PF,C (team 1, blue)
Player IDs d1..d5 = defenders (team 2, red)
Positions stored as (x, y) tuples.
"""
from __future__ import annotations

import copy
from typing import Any

# ── Coordinate constants ────────────────────────────────────────────────────

# Basket positions
BASKET_L = (15, 140)
BASKET_R = (485, 140)

# Standard half-court offensive positions (team attacks RIGHT basket)
POS_PG  = (120, 140)   # Point guard top of key
POS_SG  = (190, 85)    # Shooting guard right wing
POS_SF  = (190, 195)   # Small forward left wing
POS_PF  = (310, 68)    # Power forward right corner
POS_C   = (310, 212)   # Center left corner

# Post/elbow positions
ELBOW_R = (270, 95)    # Right elbow
ELBOW_L = (270, 185)   # Left elbow
HIGH_POST = (250, 140) # High post
LOW_POST_R = (130, 108) # Low post right block
LOW_POST_L = (130, 172) # Low post left block

# Full-court press break positions (team attacks RIGHT)
FULL_INBOUND = (10, 140)
FULL_PG = (150, 140)
FULL_SG = (200, 85)
FULL_SF = (200, 195)
FULL_PF = (340, 90)
FULL_C  = (340, 190)

PLAYER_COLORS = ["#2563eb", "#7c3aed", "#16a34a", "#d97706", "#dc2626"]
OPP_COLOR = "#ef4444"
POSITIONS = ["PG", "SG", "SF", "PF", "C"]


# ── Helper types ────────────────────────────────────────────────────────────

def _player(pid: str, x: float, y: float, label: str, color: str, team: int) -> dict:
    return {"id": pid, "x": round(x, 1), "y": round(y, 1), "label": label,
            "color": color, "team": team}


def _arrow(aid: str, x1: float, y1: float, x2: float, y2: float,
           style: str = "pass") -> dict:
    return {"id": aid, "x1": round(x1, 1), "y1": round(y1, 1),
            "x2": round(x2, 1), "y2": round(y2, 1), "style": style}


def _interp(p1: tuple, p2: tuple, t: float) -> tuple:
    """Linear interpolation between two points at ratio t (0..1)."""
    return (p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ── DSL expansion ────────────────────────────────────────────────────────────

class PlayDefinition:
    """
    A compact play definition with initial positions and a list of frame specs.
    Each frame spec is a dict:
      players: {pid: (x,y)}   — optional, overrides only listed players
      arrows:  [(pid_src, pid_dst, style), ...]  OR [(x1,y1, x2,y2, style)]
      note: str
    """
    def __init__(self, name: str, category: str, description: str,
                 tags: list[str], pace: str,
                 initial: dict[str, tuple],
                 frames: list[dict]):
        self.name = name
        self.category = category
        self.description = description
        self.tags = tags
        self.pace = pace
        self.initial = initial  # {pid: (x,y)}
        self.frame_specs = frames


def expand_play(defn: PlayDefinition) -> dict[str, Any]:
    """Expand a PlayDefinition into svg_data v2."""
    # Start with initial positions
    positions: dict[str, tuple] = dict(defn.initial)

    # Build player color/label lookup from initial set
    team1_pids = [k for k in positions if k.startswith("p")]
    team2_pids = [k for k in positions if k.startswith("d")]

    def _make_player(pid: str, pos: tuple) -> dict:
        if pid.startswith("p"):
            idx = int(pid[1:]) - 1
            label = POSITIONS[idx] if idx < len(POSITIONS) else str(idx + 1)
            color = PLAYER_COLORS[idx % len(PLAYER_COLORS)]
            return _player(pid, pos[0], pos[1], label, color, 1)
        else:
            idx = int(pid[1:]) - 1
            return _player(pid, pos[0], pos[1], str(idx + 1), OPP_COLOR, 2)

    out_frames = []
    for i, spec in enumerate(defn.frame_specs):
        # Update positions
        for pid, pos in spec.get("players", {}).items():
            positions[pid] = pos

        players = [_make_player(pid, pos) for pid, pos in positions.items()]

        # Build arrows
        arrows = []
        for j, a in enumerate(spec.get("arrows", [])):
            aid = f"a{i}_{j}"
            if len(a) == 3:
                src, dst, style = a
                if isinstance(src, str):
                    # pid -> pid
                    p1 = positions.get(src, (0, 0))
                    p2 = positions.get(dst, (0, 0))
                    arrows.append(_arrow(aid, p1[0], p1[1], p2[0], p2[1], style))
                else:
                    x1, y1 = src
                    x2, y2 = dst
                    arrows.append(_arrow(aid, x1, y1, x2, y2, style))
            elif len(a) == 5:
                x1, y1, x2, y2, style = a
                arrows.append(_arrow(aid, x1, y1, x2, y2, style))

        out_frames.append({
            "index": i,
            "players": players,
            "arrows": arrows,
            "freeform_paths": [],
            "notes": spec.get("note", ""),
        })

    return {"version": 2, "frames": out_frames}


def validate_svg_data(svg_data: dict) -> list[str]:
    """Return list of validation errors (empty = valid)."""
    errors: list[str] = []
    if svg_data.get("version") != 2:
        errors.append("version must be 2")
    frames = svg_data.get("frames", [])
    if len(frames) < 10:
        errors.append(f"need >=10 frames, got {len(frames)}")
    for fi, frame in enumerate(frames):
        team1 = [p for p in frame.get("players", []) if p.get("team") == 1]
        if len(team1) < 5:
            errors.append(f"frame {fi}: only {len(team1)} team-1 players")
        for p in frame.get("players", []):
            x, y = p.get("x", 0), p.get("y", 0)
            if not (0 <= x <= 500 and 0 <= y <= 280):
                errors.append(f"frame {fi} player {p['id']} out of bounds ({x},{y})")
        for a in frame.get("arrows", []):
            for coord in [a.get("x1", 0), a.get("x2", 0)]:
                if not (0 <= coord <= 500):
                    errors.append(f"frame {fi} arrow {a['id']} x out of range")
            for coord in [a.get("y1", 0), a.get("y2", 0)]:
                if not (0 <= coord <= 280):
                    errors.append(f"frame {fi} arrow {a['id']} y out of range")
    return errors


# ── 12 Template play definitions ─────────────────────────────────────────────
# Each play attacks toward the RIGHT basket (x≈485)

TEMPLATE_PLAYS: list[PlayDefinition] = [

    # 1. Pick & Roll ──────────────────────────────────────────────────────────
    PlayDefinition(
        name="Pick & Roll",
        category="set_play",
        description="Classic ball-handler pick and roll action",
        tags=["Offensive Set", "P&R"],
        pace="medium-to-fast",
        initial={
            "p1": (120, 140), "p2": (200, 85),  "p3": (200, 195),
            "p4": (310, 68),  "p5": (310, 212),
        },
        frames=[
            {"note": "Initial alignment — PG top of key, C at elbow"},
            {"players": {"p5": (230, 140)},
             "arrows": [("p5", "p1", "screen")],
             "note": "C sets ball screen for PG at top"},
            {"players": {"p1": (280, 115)},
             "arrows": [("p1", "p5", "pass"), ("p5", (380, 140), "dribble")],
             "note": "PG drives off screen, C rolls to basket"},
            {"players": {"p5": (380, 140)},
             "arrows": [("p1", "p5", "pass")],
             "note": "PG hits rolling C if defense switches"},
            {"players": {"p5": (430, 140)},
             "arrows": [("p5", BASKET_R, "dribble")],
             "note": "C finishes at rim"},
            {"arrows": [("p2", "p4", "cut")],
             "note": "SG spaces to corner, PF kicks to corner option"},
            {"players": {"p1": (320, 140)},
             "arrows": [("p1", "p2", "pass")],
             "note": "Kick out to SG on the wing if paint is clogged"},
            {"players": {"p2": (270, 75)},
             "arrows": [("p2", "p4", "pass")],
             "note": "SG extra pass to PF in corner for 3"},
            {"players": {"p4": (380, 60)},
             "arrows": [("p4", BASKET_R, "dribble")],
             "note": "PF drives baseline if open"},
            {"arrows": [("p1", "p3", "pass")],
             "note": "Reset — kick to SF weak side for second action"},
        ],
    ),

    # 2. Horns ────────────────────────────────────────────────────────────────
    PlayDefinition(
        name="Horns",
        category="set_play",
        description="Two bigs at the elbows with guards at corners",
        tags=["Offensive Set", "Horns"],
        pace="medium",
        initial={
            "p1": (130, 140), "p2": (310, 68), "p3": (310, 212),
            "p4": (250, 95),  "p5": (250, 185),
        },
        frames=[
            {"note": "Horns set: PG ball, PF+C at elbows, wings in corners"},
            {"arrows": [("p1", "p4", "pass")],
             "note": "PG enters to PF at right elbow"},
            {"players": {"p1": (200, 140)},
             "arrows": [("p4", "p1", "screen"), ("p1", (320, 140), "cut")],
             "note": "PF hand-off or screen for PG driving baseline"},
            {"players": {"p1": (340, 140)},
             "arrows": [("p1", BASKET_R, "dribble")],
             "note": "PG attacks basket off elbow action"},
            {"arrows": [("p4", "p5", "pass")],
             "note": "Reverse: PF swings to C at left elbow"},
            {"players": {"p5": (250, 185)},
             "arrows": [("p5", "p3", "pass")],
             "note": "C feeds SF cutting from corner"},
            {"players": {"p3": (380, 175)},
             "arrows": [("p3", BASKET_R, "dribble")],
             "note": "SF finishes at rim on baseline cut"},
            {"arrows": [("p4", "p2", "pass"), ("p2", "p2", "screen")],
             "note": "PF hits SG — SG attacks off own momentum"},
            {"players": {"p2": (360, 68)},
             "arrows": [("p2", BASKET_R, "dribble")],
             "note": "SG drives baseline from corner"},
            {"arrows": [("p1", "p4", "pass"), ("p4", "p5", "screen")],
             "note": "Reset — PG resets, PF screens for C on second side"},
        ],
    ),

    # 3. Flex ─────────────────────────────────────────────────────────────────
    PlayDefinition(
        name="Flex",
        category="set_play",
        description="Continuous flex cuts and down screens",
        tags=["Offensive Set", "Flex"],
        pace="slow-to-medium",
        initial={
            "p1": (130, 140), "p2": (200, 90),  "p3": (200, 190),
            "p4": (320, 68),  "p5": (140, 200),
        },
        frames=[
            {"note": "Flex alignment — PG top, wings on each side"},
            {"arrows": [("p1", "p3", "pass")],
             "note": "PG passes to SF on left wing"},
            {"players": {"p5": (230, 190)},
             "arrows": [("p5", "p4", "screen")],
             "note": "C sets down screen (flex screen) for PF in corner"},
            {"players": {"p4": (260, 110)},
             "arrows": [("p4", BASKET_R, "cut")],
             "note": "PF flex cuts off screen to basket"},
            {"arrows": [("p3", "p4", "pass")],
             "note": "SF hits PF on flex cut if open"},
            {"players": {"p4": (380, 140)},
             "arrows": [("p4", BASKET_R, "dribble")],
             "note": "PF layup if open on flex cut"},
            {"arrows": [("p2", "p3", "screen")],
             "note": "SG sets down screen for SF after the pass"},
            {"players": {"p3": (230, 140)},
             "arrows": [("p3", (310, 90), "cut")],
             "note": "SF pops to wing off down screen"},
            {"arrows": [("p1", "p3", "pass")],
             "note": "PG swings to new wing — flex motion continues"},
            {"arrows": [("p3", "p5", "screen"), ("p5", BASKET_R, "cut")],
             "note": "Continuous flex: C cuts, motion resets with new action"},
        ],
    ),

    # 4. Princeton ────────────────────────────────────────────────────────────
    PlayDefinition(
        name="Princeton",
        category="set_play",
        description="Back-door cuts from the high post",
        tags=["Offensive Set", "Princeton"],
        pace="slow",
        initial={
            "p1": (120, 140), "p2": (200, 90), "p3": (200, 190),
            "p4": (320, 90),  "p5": (250, 140),
        },
        frames=[
            {"note": "Princeton: C at high post, wings and PG spaced"},
            {"arrows": [("p1", "p5", "pass")],
             "note": "PG enters to C at high post"},
            {"arrows": [("p2", (310, 140), "cut")],
             "note": "SG makes back-door cut off C's vision"},
            {"arrows": [("p5", "p2", "pass")],
             "note": "C hits SG on back-door if open"},
            {"players": {"p2": (420, 140)},
             "arrows": [("p2", BASKET_R, "dribble")],
             "note": "SG finishes back-door layup"},
            {"players": {"p5": (270, 140)},
             "arrows": [("p5", "p3", "pass")],
             "note": "If back-door denied: C reverses to SF"},
            {"arrows": [("p4", (360, 140), "cut")],
             "note": "PF cuts baseline as defense collapses"},
            {"arrows": [("p3", "p4", "pass")],
             "note": "SF hits PF on cut or drives baseline"},
            {"players": {"p4": (380, 140)},
             "arrows": [("p4", BASKET_R, "dribble")],
             "note": "PF finishes or kicks to corner shooter"},
            {"arrows": [("p1", "p5", "pass"), ("p5", "p2", "screen")],
             "note": "Reset: PG re-enters, C screens for SG — motion continues"},
        ],
    ),

    # 5. Motion Offense (5-out) ────────────────────────────────────────────────
    PlayDefinition(
        name="Motion Offense",
        category="system",
        description="5-out motion with spacing principles",
        tags=["System", "5-out"],
        pace="medium",
        initial={
            "p1": (130, 140), "p2": (220, 78),  "p3": (220, 202),
            "p4": (330, 70),  "p5": (330, 210),
        },
        frames=[
            {"note": "5-out spacing — all five beyond arc"},
            {"arrows": [("p1", "p2", "pass")],
             "note": "PG enters to SG on right wing"},
            {"players": {"p1": (195, 140)},
             "arrows": [("p1", (270, 90), "cut")],
             "note": "PG makes skip cut (gate cut) to weak side"},
            {"arrows": [("p2", "p4", "pass")],
             "note": "SG swings to PF in corner"},
            {"players": {"p4": (380, 65)},
             "arrows": [("p4", BASKET_R, "dribble")],
             "note": "PF drives baseline off live dribble"},
            {"arrows": [("p4", "p5", "pass")],
             "note": "PF kicks to C spacing weak corner"},
            {"players": {"p5": (390, 215)},
             "arrows": [("p5", (430, 140), "dribble")],
             "note": "C attack middle, defense must help"},
            {"arrows": [("p5", "p3", "pass")],
             "note": "C kick to SF on left wing for 3"},
            {"players": {"p3": (240, 200)},
             "arrows": [("p3", (310, 170), "dribble")],
             "note": "SF attacks off the catch — baseline drive"},
            {"arrows": [("p3", "p1", "pass")],
             "note": "Reset — kick back to top, 5-out motion continues"},
        ],
    ),

    # 6. Floppy ────────────────────────────────────────────────────────────────
    PlayDefinition(
        name="Floppy",
        category="set_play",
        description="Off-ball screens to free shooters",
        tags=["Offensive Set", "Shooter"],
        pace="medium",
        initial={
            "p1": (130, 140), "p2": (160, 140), "p3": (280, 68),
            "p4": (280, 212), "p5": (160, 68),
        },
        frames=[
            {"note": "Floppy: shooter baseline, screeners on each side"},
            {"players": {"p5": (190, 100)},
             "arrows": [("p5", "p2", "screen")],
             "note": "PF sets screen for shooter (SG) on right side"},
            {"players": {"p4": (190, 180)},
             "arrows": [("p4", "p2", "screen")],
             "note": "C sets screen on left side — shooter chooses"},
            {"players": {"p2": (300, 95)},
             "arrows": [("p2", (320, 78), "cut")],
             "note": "SG cuts off right screen to wing"},
            {"arrows": [("p1", "p2", "pass")],
             "note": "PG hits shooter coming off screen"},
            {"players": {"p2": (320, 78)},
             "arrows": [("p2", BASKET_R, "dribble")],
             "note": "Shooter catches and shoots — or drives baseline"},
            {"arrows": [("p3", "p5", "screen")],
             "note": "PF pops to elbow, SF screens down for C"},
            {"players": {"p5": (260, 110)},
             "arrows": [("p5", BASKET_R, "dribble")],
             "note": "PF mid-range off elbow pop"},
            {"arrows": [("p1", "p3", "pass")],
             "note": "PG swing to SF — second screen action coming"},
            {"arrows": [("p4", "p2", "screen"), ("p2", (300, 185), "cut")],
             "note": "Floppy reset — shooter goes other way off second screen"},
        ],
    ),

    # 7. Spain Pick & Roll ─────────────────────────────────────────────────────
    PlayDefinition(
        name="Spain Pick & Roll",
        category="set_play",
        description="Pick & roll with back screen on roller",
        tags=["Offensive Set", "P&R"],
        pace="fast",
        initial={
            "p1": (130, 140), "p2": (220, 85), "p3": (220, 195),
            "p4": (310, 68),  "p5": (240, 140),
        },
        frames=[
            {"note": "Spain PnR: PG ball, C at nail, SG wing"},
            {"players": {"p5": (215, 140)},
             "arrows": [("p5", "p1", "screen")],
             "note": "C sets ball screen for PG at top"},
            {"arrows": [("p3", "p5", "screen")],
             "note": "SF immediately sets back screen on rolling C"},
            {"players": {"p5": (330, 140)},
             "arrows": [("p5", BASKET_R, "cut")],
             "note": "C rolls hard to basket, screened defender has 2 threats"},
            {"arrows": [("p1", "p5", "pass")],
             "note": "PG lobs or bounce pass to rolling C"},
            {"players": {"p5": (430, 140)},
             "arrows": [("p5", BASKET_R, "dribble")],
             "note": "C finishes at rim"},
            {"arrows": [("p1", "p2", "pass")],
             "note": "If C covered: PG kicks to SG on wing"},
            {"players": {"p2": (300, 78)},
             "arrows": [("p2", BASKET_R, "dribble")],
             "note": "SG attacks baseline off catch"},
            {"arrows": [("p4", "p3", "cut")],
             "note": "PF cuts baseline if help defense sagged"},
            {"arrows": [("p1", "p3", "pass")],
             "note": "Reset — swing weak side, Spain action can repeat"},
        ],
    ),

    # 8. Hammer ────────────────────────────────────────────────────────────────
    PlayDefinition(
        name="Hammer",
        category="set_play",
        description="Corner shooter off baseline cut from DHO",
        tags=["Offensive Set", "Shooter"],
        pace="medium-to-fast",
        initial={
            "p1": (150, 140), "p2": (260, 90), "p3": (380, 210),
            "p4": (310, 68),  "p5": (260, 180),
        },
        frames=[
            {"note": "Hammer: PG drives, PF screens for corner shooter"},
            {"arrows": [("p1", "p2", "dribble")],
             "note": "PG dribbles toward SG on right wing (DHO set-up)"},
            {"players": {"p1": (230, 140)},
             "arrows": [("p1", "p2", "pass")],
             "note": "PG hands off to SG (DHO)"},
            {"players": {"p2": (290, 90)},
             "arrows": [("p2", BASKET_R, "dribble")],
             "note": "SG drives baseline — DHO triggers hammer action"},
            {"arrows": [("p4", "p3", "screen")],
             "note": "PF sets hammer screen for SF in corner"},
            {"players": {"p3": (400, 200)},
             "arrows": [("p3", (430, 195), "cut")],
             "note": "SF comes off hammer screen to corner 3 spot"},
            {"arrows": [("p2", "p3", "pass")],
             "note": "SG skip pass to SF coming off hammer screen — open 3!"},
            {"players": {"p3": (430, 205)},
             "arrows": [("p3", BASKET_R, "dribble")],
             "note": "SF shoots or drives if help is slow"},
            {"arrows": [("p5", "p1", "screen")],
             "note": "C sets second side screen for PG cutting through"},
            {"arrows": [("p2", "p5", "pass"), ("p5", BASKET_R, "dribble")],
             "note": "Back action: SG enters C rolling after clearing the screen"},
        ],
    ),

    # 9. Zipper ────────────────────────────────────────────────────────────────
    PlayDefinition(
        name="Zipper",
        category="set_play",
        description="Guard cuts to ball on wing for action",
        tags=["Offensive Set"],
        pace="medium",
        initial={
            "p1": (130, 140), "p2": (160, 140), "p3": (310, 195),
            "p4": (310, 68),  "p5": (260, 140),
        },
        frames=[
            {"note": "Zipper: SG starts at basket, zips to wing off C screen"},
            {"arrows": [("p5", "p2", "screen")],
             "note": "C sets up screen (zipper screen) for SG"},
            {"players": {"p2": (280, 95)},
             "arrows": [("p2", (310, 85), "cut")],
             "note": "SG zips to right wing off C screen"},
            {"arrows": [("p1", "p2", "pass")],
             "note": "PG hits SG on the zip — SG catches with pace"},
            {"players": {"p2": (320, 85)},
             "arrows": [("p2", BASKET_R, "dribble")],
             "note": "SG attacks baseline off the catch"},
            {"arrows": [("p5", "p1", "screen")],
             "note": "C screens for PG rolling down — 2-man game option"},
            {"arrows": [("p2", "p5", "pass")],
             "note": "SG hits C rolling down if defender helps on baseline"},
            {"players": {"p5": (390, 145)},
             "arrows": [("p5", BASKET_R, "dribble")],
             "note": "C finishes roll at rim"},
            {"arrows": [("p4", "p3", "cut"), ("p3", (390, 205), "cut")],
             "note": "PF/SF set back-cut if overplaying wing pass"},
            {"arrows": [("p1", "p4", "pass"), ("p4", BASKET_R, "dribble")],
             "note": "Reset: PG swings to PF popping — attack from PF's side"},
        ],
    ),

    # 10. Pin Down ─────────────────────────────────────────────────────────────
    PlayDefinition(
        name="Pin Down",
        category="set_play",
        description="Big screens for shooter cutting up from corner",
        tags=["Offensive Set", "Shooter"],
        pace="slow-to-medium",
        initial={
            "p1": (130, 140), "p2": (380, 68), "p3": (220, 85),
            "p4": (310, 68),  "p5": (280, 175),
        },
        frames=[
            {"note": "Pin Down: SG in corner, C sets pin-down screen"},
            {"arrows": [("p1", "p3", "pass")],
             "note": "PG enters to SF on left wing"},
            {"arrows": [("p5", "p2", "screen")],
             "note": "C moves to pin-down position — sets screen for SG in corner"},
            {"players": {"p2": (310, 80)},
             "arrows": [("p2", (310, 80), "cut")],
             "note": "SG curls off pin-down toward wing — catch and shoot threat"},
            {"arrows": [("p3", "p2", "pass")],
             "note": "SF hits SG coming off pin-down screen"},
            {"players": {"p2": (330, 78)},
             "arrows": [("p2", BASKET_R, "dribble")],
             "note": "SG catches and shoots 3 or drives baseline"},
            {"arrows": [("p5", "p4", "screen")],
             "note": "C sets second pin-down for PF on other side"},
            {"players": {"p4": (320, 85)},
             "arrows": [("p4", (360, 78), "cut")],
             "note": "PF curls to elbow, receives pass for mid-range"},
            {"arrows": [("p1", "p4", "pass")],
             "note": "PG enters to PF at elbow — PF can shoot or drive"},
            {"players": {"p4": (360, 78)},
             "arrows": [("p4", BASKET_R, "dribble")],
             "note": "PF drives baseline — pin-down cycle can restart"},
        ],
    ),

    # 11. Zone Attack (vs 2-3) ─────────────────────────────────────────────────
    PlayDefinition(
        name="Zone Attack",
        category="set_play",
        description="vs 2-3 zone — skip passes and hi-lo",
        tags=["Offensive Set", "vs Zone"],
        pace="slow",
        initial={
            "p1": (120, 140), "p2": (210, 85),  "p3": (210, 195),
            "p4": (360, 68),  "p5": (230, 140),
        },
        frames=[
            {"note": "Zone Attack 2-3: overload one side, high-low action"},
            {"arrows": [("p1", "p2", "pass")],
             "note": "PG enters to SG on right wing — probe zone"},
            {"players": {"p5": (240, 120)},
             "arrows": [("p5", (260, 130), "dribble")],
             "note": "C moves to high post — seams in zone"},
            {"arrows": [("p2", "p5", "pass")],
             "note": "SG feeds C at high post — zone must react"},
            {"arrows": [("p5", "p3", "pass")],
             "note": "C hi-lo to SF sneaking behind zone on weak side"},
            {"players": {"p3": (350, 200)},
             "arrows": [("p3", BASKET_R, "dribble")],
             "note": "SF catches behind zone — baseline drive or short corner shot"},
            {"arrows": [("p1", "p4", "pass")],
             "note": "Skip pass to PF in corner — zone scrambles"},
            {"players": {"p4": (390, 65)},
             "arrows": [("p4", BASKET_R, "dribble")],
             "note": "PF corner 3 or drives baseline on scrambling zone"},
            {"arrows": [("p2", "p3", "pass")],
             "note": "Overload right side: wing-to-short-corner for 2-3 gap"},
            {"arrows": [("p5", "p4", "screen"), ("p4", BASKET_R, "cut")],
             "note": "C screen-away: PF dives through gap in 2-3 zone"},
        ],
    ),

    # 12. Press Break ──────────────────────────────────────────────────────────
    PlayDefinition(
        name="Press Break",
        category="system",
        description="Full-court press breaker with outlets",
        tags=["System", "Press Break"],
        pace="fast",
        initial={
            "p1": (30, 140), "p2": (80, 90),   "p3": (80, 190),
            "p4": (200, 90), "p5": (200, 190),
        },
        frames=[
            {"note": "Press Break: inbound from baseline, two outlets each side"},
            {"arrows": [("p1", "p2", "pass")],
             "note": "PG inbounds to SG near free-throw line extended"},
            {"players": {"p2": (120, 90)},
             "arrows": [("p2", "p4", "pass")],
             "note": "SG quickly advances to PF at half-court"},
            {"players": {"p4": (250, 90)},
             "arrows": [("p4", "p1", "pass")],
             "note": "PF looks for PG filling middle — or hits C if open"},
            {"players": {"p1": (220, 140)},
             "arrows": [("p1", BASKET_R, "dribble")],
             "note": "PG catches in middle and attacks full speed"},
            {"arrows": [("p2", "p4", "cut"), ("p3", "p5", "cut")],
             "note": "Wings fill lanes — 3-on-2 fast break forming"},
            {"players": {"p1": (320, 140)},
             "arrows": [("p1", "p2", "pass")],
             "note": "PG passes to trailing wing for lay-up opportunity"},
            {"players": {"p2": (410, 90)},
             "arrows": [("p2", BASKET_R, "dribble")],
             "note": "Wing finishes — or kicks to trailer for 3"},
            {"arrows": [("p4", (390, 90), "cut")],
             "note": "PF trails for secondary break or 3-point shot"},
            {"arrows": [("p1", "p3", "pass")],
             "note": "If primary break denied: secondary action from PG to SF"},
            {"players": {"p3": (300, 190)},
             "arrows": [("p3", BASKET_R, "dribble")],
             "note": "SF attacks from left side — press break complete"},
        ],
    ),
]

# ── Master Playbook 2026 — 30 high-school effective plays ─────────────────────

MASTER_2026_PLAYS: list[PlayDefinition] = [

    # ─── Section A: Half-court vs Man-to-Man (10 plays) ──────────────────────

    PlayDefinition(
        name="Horns High (ATO)",
        category="set_play",
        description="After-timeout Horns: PG drives or hits shooter off stagger",
        tags=["ATO", "Horns", "vs Man"],
        pace="medium",
        initial={
            "p1": (130, 140), "p2": (310, 68), "p3": (310, 212),
            "p4": (250, 95),  "p5": (250, 185),
        },
        frames=[
            {"note": "Horns ATO — quick hitter off timeout"},
            {"arrows": [("p1", "p4", "pass")], "note": "PG enters to PF at right elbow"},
            {"arrows": [("p5", "p2", "screen"), ("p4", "p5", "screen")],
             "note": "Stagger screens: C-then-PF for SG cutting to wing"},
            {"players": {"p2": (370, 80)},
             "arrows": [("p2", (390, 75), "cut")], "note": "SG curls off stagger to corner 3"},
            {"arrows": [("p4", "p2", "pass")], "note": "PF skips to SG — open 3"},
            {"players": {"p2": (390, 68)},
             "arrows": [("p2", BASKET_R, "dribble")], "note": "SG shoots or drives baseline"},
            {"arrows": [("p1", "p5", "screen")], "note": "PG screens for C rolling — 2nd action"},
            {"players": {"p5": (330, 145)},
             "arrows": [("p5", BASKET_R, "cut")], "note": "C rolls hard to rim"},
            {"arrows": [("p4", "p5", "pass")], "note": "PF lobs to rolling C"},
            {"arrows": [("p1", "p3", "pass")], "note": "Kick weak side reset"},
        ],
    ),

    PlayDefinition(
        name="Box Baseline (BLOB)",
        category="inbound",
        description="Baseline out-of-bounds from box formation — stagger for shooter",
        tags=["Inbound", "Baseline", "BLOB"],
        pace="medium",
        initial={
            "p1": (60, 140),  "p2": (130, 108), "p3": (130, 172),
            "p4": (170, 108), "p5": (170, 172),
        },
        frames=[
            {"note": "Box BLOB: shooter and cutter in box, stagger screens"},
            {"arrows": [("p4", "p2", "screen"), ("p5", "p3", "screen")],
             "note": "PF and C set simultaneous box screens"},
            {"players": {"p2": (220, 90)},
             "arrows": [("p2", (250, 80), "cut")], "note": "SG cuts off top screen to wing"},
            {"arrows": [("p1", "p2", "pass")], "note": "Inbounder hits SG on wing"},
            {"players": {"p2": (260, 80)},
             "arrows": [("p2", BASKET_R, "dribble")], "note": "SG attacks wing catch"},
            {"arrows": [("p3", (200, 175), "cut")], "note": "SF cuts baseline off second box screen"},
            {"arrows": [("p1", "p3", "pass")], "note": "Alternate: inbounder hits SF cutting baseline"},
            {"players": {"p3": (360, 185)},
             "arrows": [("p3", BASKET_R, "dribble")], "note": "SF finishes baseline cut"},
            {"arrows": [("p4", "p5", "screen")], "note": "PF back-screens for C diving to rim"},
            {"arrows": [("p1", "p5", "pass")], "note": "Lob to C on back-screen dive — lob play"},
        ],
    ),

    PlayDefinition(
        name="Stack Sideline (SLOB)",
        category="inbound",
        description="Sideline out-of-bounds from stacked formation",
        tags=["Inbound", "Sideline", "SLOB"],
        pace="medium",
        initial={
            "p1": (250, 5),   "p2": (200, 140), "p3": (230, 140),
            "p4": (260, 140), "p5": (290, 140),
        },
        frames=[
            {"note": "Stack SLOB: 4 players in stack, inbound from sideline"},
            {"arrows": [("p5", "p4", "screen")], "note": "C screens for PF — first action"},
            {"players": {"p4": (310, 80)},
             "arrows": [("p4", (330, 75), "cut")], "note": "PF pops to wing off C screen"},
            {"arrows": [("p1", "p4", "pass")], "note": "Inbounder hits PF on wing"},
            {"arrows": [("p3", "p2", "screen")], "note": "SF screens for SG in stack — 2nd action"},
            {"players": {"p2": (200, 185)},
             "arrows": [("p2", (210, 195), "cut")], "note": "SG cuts baseline off screen"},
            {"arrows": [("p4", "p2", "pass")], "note": "PF hits SG on baseline cut"},
            {"players": {"p2": (350, 200)},
             "arrows": [("p2", BASKET_R, "dribble")], "note": "SG finishes baseline"},
            {"arrows": [("p5", "p1", "pass")], "note": "C seals for inbounder entering court"},
            {"players": {"p1": (260, 30)},
             "arrows": [("p1", (300, 140), "dribble")], "note": "Inbounder enters court after pass — reset"},
        ],
    ),

    PlayDefinition(
        name="Chin Series",
        category="set_play",
        description="PG screens for wing, big screens for PG — quick hitter",
        tags=["Quick Hitter", "vs Man", "Chin"],
        pace="medium-to-fast",
        initial={
            "p1": (130, 140), "p2": (200, 90), "p3": (200, 190),
            "p4": (310, 68),  "p5": (250, 140),
        },
        frames=[
            {"note": "Chin: PG dribbles at wing, triggers action"},
            {"arrows": [("p1", "p2", "dribble")], "note": "PG dribbles toward SG on wing"},
            {"arrows": [("p1", "p2", "screen")], "note": "PG sets screen for SG (dribble handoff)"},
            {"players": {"p2": (260, 90)},
             "arrows": [("p2", (290, 85), "cut")], "note": "SG uses screen, attacks elbow area"},
            {"arrows": [("p5", "p1", "screen")], "note": "C immediately back-screens for PG"},
            {"players": {"p1": (230, 140)},
             "arrows": [("p1", (300, 140), "cut")], "note": "PG cuts off C's back screen toward basket"},
            {"arrows": [("p2", "p1", "pass")], "note": "SG hits PG on basket cut if open"},
            {"players": {"p1": (400, 145)},
             "arrows": [("p1", BASKET_R, "dribble")], "note": "PG finishes at rim"},
            {"arrows": [("p5", "p4", "screen"), ("p4", (360, 78), "cut")],
             "note": "If PG cut denied: C screens for PF — 2nd option"},
            {"arrows": [("p2", "p4", "pass")], "note": "SG hits PF popping off screen"},
            {"players": {"p4": (370, 78)},
             "arrows": [("p4", BASKET_R, "dribble")], "note": "PF attacks off the catch"},
        ],
    ),

    PlayDefinition(
        name="Hawk Cut",
        category="set_play",
        description="Guard cuts baseline off high post entry",
        tags=["Quick Hitter", "vs Man", "Back-cut"],
        pace="medium",
        initial={
            "p1": (130, 140), "p2": (200, 90), "p3": (200, 190),
            "p4": (310, 68),  "p5": (260, 140),
        },
        frames=[
            {"note": "Hawk: PG enters to C at high post — guard cuts"},
            {"arrows": [("p1", "p5", "pass")], "note": "PG enters ball to C at high post"},
            {"arrows": [("p2", (320, 140), "cut")], "note": "SG makes Hawk (baseline) cut off C's vision"},
            {"arrows": [("p5", "p2", "pass")], "note": "C hits SG on Hawk cut — immediate basket opportunity"},
            {"players": {"p2": (420, 145)},
             "arrows": [("p2", BASKET_R, "dribble")], "note": "SG finishes Hawk cut at rim"},
            {"arrows": [("p5", "p4", "pass")], "note": "If SG defended: C swings to PF on wing"},
            {"players": {"p4": (330, 68)},
             "arrows": [("p4", BASKET_R, "dribble")], "note": "PF attacks from wing — second option"},
            {"arrows": [("p3", (280, 180), "cut")], "note": "SF drifts for weak-side 3 corner"},
            {"arrows": [("p5", "p3", "pass")], "note": "C hits SF — corner 3"},
            {"players": {"p3": (390, 205)},
             "arrows": [("p3", BASKET_R, "dribble")], "note": "SF shoots or attacks baseline"},
            {"arrows": [("p1", "p5", "pass"), ("p5", "p2", "screen")],
             "note": "Reset: Hawk action can repeat on opposite wing"},
        ],
    ),

    PlayDefinition(
        name="America Play",
        category="set_play",
        description="Stagger screen for shooter coming off pin-down series",
        tags=["Offensive Set", "Shooter", "Stagger"],
        pace="medium",
        initial={
            "p1": (130, 140), "p2": (160, 140), "p3": (310, 195),
            "p4": (240, 108), "p5": (240, 172),
        },
        frames=[
            {"note": "America: SG starts under basket, stagger screens up the lane"},
            {"players": {"p4": (230, 115)},
             "arrows": [("p4", "p2", "screen")], "note": "PF sets first screen for SG"},
            {"players": {"p5": (230, 165)},
             "arrows": [("p5", "p2", "screen")], "note": "C sets second screen (stagger)"},
            {"players": {"p2": (290, 90)},
             "arrows": [("p2", (310, 82), "cut")], "note": "SG pops off stagger to wing — catch and shoot"},
            {"arrows": [("p1", "p2", "pass")], "note": "PG hits SG off stagger — 3-point opportunity"},
            {"players": {"p2": (320, 80)},
             "arrows": [("p2", BASKET_R, "dribble")], "note": "SG shoots 3 or drives"},
            {"arrows": [("p4", "p5", "screen")], "note": "PF pins down for C — 2nd screen action"},
            {"players": {"p5": (280, 165)},
             "arrows": [("p5", (300, 155), "cut")], "note": "C pops to elbow on second action"},
            {"arrows": [("p1", "p5", "pass")], "note": "PG hits C at elbow — mid-range or drive"},
            {"players": {"p5": (310, 150)},
             "arrows": [("p5", BASKET_R, "dribble")], "note": "C drives elbow — America resets"},
        ],
    ),

    PlayDefinition(
        name="Iverson Cut",
        category="set_play",
        description="Guard cuts through key off stagger for catch-and-shoot",
        tags=["Quick Hitter", "vs Man", "Cut"],
        pace="medium-to-fast",
        initial={
            "p1": (130, 140), "p2": (130, 100), "p3": (260, 68),
            "p4": (260, 212), "p5": (160, 140),
        },
        frames=[
            {"note": "Iverson: SG cuts through paint off two screeners"},
            {"arrows": [("p3", "p2", "screen"), ("p4", "p2", "screen")],
             "note": "PF and C set stagger screens at elbows for SG"},
            {"players": {"p2": (290, 140)},
             "arrows": [("p2", (330, 100), "cut")], "note": "SG cuts Iverson through the key"},
            {"arrows": [("p1", "p2", "pass")], "note": "PG hits SG coming off Iverson cut"},
            {"players": {"p2": (340, 95)},
             "arrows": [("p2", BASKET_R, "dribble")], "note": "SG attacks from wing after cut"},
            {"arrows": [("p5", "p1", "screen")], "note": "C screens for PG following SG's cut"},
            {"players": {"p1": (230, 140)},
             "arrows": [("p1", (300, 140), "cut")], "note": "PG follows cut through — 2nd read"},
            {"arrows": [("p2", "p1", "pass")], "note": "SG hits PG on follow cut"},
            {"players": {"p1": (380, 145)},
             "arrows": [("p1", BASKET_R, "dribble")], "note": "PG finishes at rim"},
            {"arrows": [("p3", "p4", "screen"), ("p4", BASKET_R, "cut")],
             "note": "PF screens for C — second big action reset"},
        ],
    ),

    PlayDefinition(
        name="Wheel Motion",
        category="system",
        description="Read-and-react wheel offense — continuous cutting and spacing",
        tags=["System", "5-out", "Motion"],
        pace="medium",
        initial={
            "p1": (130, 140), "p2": (220, 80), "p3": (220, 200),
            "p4": (340, 70),  "p5": (340, 210),
        },
        frames=[
            {"note": "Wheel: 5-out read-and-react — anyone can initiate"},
            {"arrows": [("p1", "p2", "pass")], "note": "PG passes to SG right wing"},
            {"arrows": [("p1", (200, 195), "cut")], "note": "PG makes basket cut (pass-and-cut rule)"},
            {"players": {"p3": (310, 210)},
             "arrows": [("p3", (360, 210), "cut")], "note": "SF shifts to fill empty corner after PG cut"},
            {"arrows": [("p2", "p4", "pass")], "note": "SG swings to PF in corner"},
            {"players": {"p1": (150, 200)},
             "arrows": [("p1", (200, 200), "cut")], "note": "PG fills weak wing after cutting through"},
            {"arrows": [("p4", BASKET_R, "dribble")], "note": "PF attacks baseline — defense must collapse"},
            {"arrows": [("p4", "p5", "pass")], "note": "PF kicks to C trailing on weak side"},
            {"players": {"p5": (380, 215)},
             "arrows": [("p5", (410, 215), "dribble")], "note": "C attacks corner — mid-range or 3"},
            {"arrows": [("p2", "p3", "screen")], "note": "SG screens for SF — wheel motion reversal"},
            {"arrows": [("p1", "p2", "pass")], "note": "Ball reversal — wheel motion starts again"},
        ],
    ),

    PlayDefinition(
        name="DHO Elbow",
        category="set_play",
        description="Dribble handoff at elbow, shooter pops to corner",
        tags=["Quick Hitter", "vs Man", "DHO"],
        pace="medium-to-fast",
        initial={
            "p1": (130, 140), "p2": (310, 68), "p3": (310, 212),
            "p4": (260, 108), "p5": (260, 172),
        },
        frames=[
            {"note": "DHO Elbow: PG dribbles at PF for hand-off at elbow"},
            {"arrows": [("p1", "p4", "dribble")], "note": "PG dribbles toward PF at right elbow"},
            {"arrows": [("p1", "p4", "pass")], "note": "PG hands off to PF at elbow (DHO)"},
            {"players": {"p4": (280, 108)},
             "arrows": [("p4", BASKET_R, "dribble")], "note": "PF attacks basket off DHO"},
            {"arrows": [("p5", "p1", "screen")], "note": "C sets back-screen for PG after DHO"},
            {"players": {"p1": (220, 140)},
             "arrows": [("p1", (310, 145), "cut")], "note": "PG cuts hard off back-screen"},
            {"arrows": [("p4", "p1", "pass")], "note": "PF hits PG on back-cut"},
            {"players": {"p1": (390, 145)},
             "arrows": [("p1", BASKET_R, "dribble")], "note": "PG finishes at rim"},
            {"arrows": [("p2", "p3", "cut"), ("p3", (350, 205), "cut")],
             "note": "SG/SF space — weak-side 3 corner option"},
            {"arrows": [("p4", "p2", "pass")], "note": "PF kicks to SG if basket denied"},
            {"players": {"p2": (380, 68)},
             "arrows": [("p2", BASKET_R, "dribble")], "note": "SG attacks from corner — second read"},
        ],
    ),

    PlayDefinition(
        name="1-4 High Quick",
        category="set_play",
        description="1-4 high set — guard splits with two bigs, quick hitter",
        tags=["Quick Hitter", "vs Man", "1-4 High"],
        pace="fast",
        initial={
            "p1": (130, 140), "p2": (310, 68), "p3": (310, 212),
            "p4": (260, 100), "p5": (260, 180),
        },
        frames=[
            {"note": "1-4 High: PG ball, 4 players aligned at foul-line extended"},
            {"arrows": [("p4", "p5", "screen"), ("p5", "p4", "screen")],
             "note": "PF and C set double screen — PG attacks middle"},
            {"players": {"p1": (220, 140)},
             "arrows": [("p1", (300, 140), "dribble")], "note": "PG attacks between PF and C (split cut)"},
            {"arrows": [("p1", BASKET_R, "dribble")], "note": "PG drives to rim off split"},
            {"arrows": [("p4", "p2", "screen")], "note": "PF pops to screen for SG — secondary action"},
            {"players": {"p2": (350, 80)},
             "arrows": [("p2", (370, 72), "cut")], "note": "SG comes off PF screen to wing"},
            {"arrows": [("p1", "p2", "pass")], "note": "PG hits SG if rim is clogged"},
            {"players": {"p2": (380, 78)},
             "arrows": [("p2", BASKET_R, "dribble")], "note": "SG attacks from wing"},
            {"arrows": [("p5", "p3", "screen")], "note": "C screens for SF — weak side action mirrors"},
            {"arrows": [("p1", "p3", "pass")], "note": "PG swings weak side — 1-4 reset"},
        ],
    ),

    # ─── Section B: Half-court vs Zone (6 plays) ─────────────────────────────

    PlayDefinition(
        name="Swing Swing (vs Zone)",
        category="set_play",
        description="Rapid ball movement to collapse zone and find gap",
        tags=["vs Zone", "Ball Movement"],
        pace="medium",
        initial={
            "p1": (120, 140), "p2": (210, 85),  "p3": (210, 195),
            "p4": (360, 65),  "p5": (235, 140),
        },
        frames=[
            {"note": "Swing Swing: rapid reversal to find zone gaps"},
            {"arrows": [("p1", "p2", "pass")], "note": "PG enters right wing — zone shifts"},
            {"arrows": [("p2", "p1", "pass")], "note": "SG swings back — zone over-shifts"},
            {"arrows": [("p1", "p3", "pass")], "note": "PG swings to SF left wing — zone scrambles"},
            {"players": {"p5": (250, 140)},
             "arrows": [("p5", (270, 130), "cut")], "note": "C slides to hi-lo gap as zone scrambles"},
            {"arrows": [("p3", "p5", "pass")], "note": "SF hits C at gap in zone"},
            {"arrows": [("p5", "p4", "pass")], "note": "C hi-lo to PF sneaking corner — skip"},
            {"players": {"p4": (390, 62)},
             "arrows": [("p4", BASKET_R, "dribble")], "note": "PF corner 3 or drive — zone can't recover"},
            {"arrows": [("p3", "p4", "pass")], "note": "Direct skip left-to-right — zone scramble"},
            {"arrows": [("p4", "p2", "pass")], "note": "Continue swing — extra pass for open shot"},
            {"players": {"p2": (350, 82)},
             "arrows": [("p2", BASKET_R, "dribble")], "note": "SG attacks into zone gap from wing"},
        ],
    ),

    PlayDefinition(
        name="Hi-Lo Zone Series",
        category="set_play",
        description="High post to low post hi-lo action vs zone",
        tags=["vs Zone", "Hi-Lo", "Post"],
        pace="slow",
        initial={
            "p1": (120, 140), "p2": (210, 85),  "p3": (210, 195),
            "p4": (350, 68),  "p5": (240, 140),
        },
        frames=[
            {"note": "Hi-Lo vs Zone: C at high post is the hub"},
            {"arrows": [("p1", "p5", "pass")], "note": "PG enters to C at high post — zone must defend"},
            {"players": {"p4": (200, 155)},
             "arrows": [("p4", (210, 165), "cut")], "note": "PF flashes to low block as zone collapses on C"},
            {"arrows": [("p5", "p4", "pass")], "note": "C hi-lo to PF on low block — bucket opportunity"},
            {"players": {"p4": (170, 155)},
             "arrows": [("p4", BASKET_R, "dribble")], "note": "PF low post move — zone defense compromised"},
            {"arrows": [("p5", "p2", "pass")], "note": "If low post covered: C kicks to wing for 3"},
            {"players": {"p2": (270, 82)},
             "arrows": [("p2", BASKET_R, "dribble")], "note": "SG drives off kick — zone still recovering"},
            {"arrows": [("p3", (250, 190), "cut")], "note": "SF dives to weak-side short corner — zone gap"},
            {"arrows": [("p5", "p3", "pass")], "note": "C hits SF in short corner"},
            {"players": {"p3": (290, 200)},
             "arrows": [("p3", BASKET_R, "dribble")], "note": "SF attacks short corner — Hi-Lo complete"},
            {"arrows": [("p1", "p5", "pass"), ("p5", "p4", "screen")],
             "note": "Reset — Hi-Lo runs again from opposite side"},
        ],
    ),

    PlayDefinition(
        name="Overload Weak Side",
        category="set_play",
        description="Three players on one side to overload and skip to open corner",
        tags=["vs Zone", "Overload", "Skip"],
        pace="medium",
        initial={
            "p1": (130, 140), "p2": (210, 90),  "p3": (280, 90),
            "p4": (280, 165), "p5": (240, 145),
        },
        frames=[
            {"note": "Overload: 3-on-2 on right side, skip for corner shooter"},
            {"arrows": [("p1", "p2", "pass")], "note": "PG enters to SG — zone loads right"},
            {"arrows": [("p2", "p3", "pass")], "note": "Extra pass: SG to SF — zone continues loading"},
            {"arrows": [("p5", (260, 155), "cut")], "note": "C dives to short corner overload — 4th player"},
            {"arrows": [("p3", "p5", "pass")], "note": "SF hits C in short corner — zone collapses"},
            {"arrows": [("p5", "p4", "pass")], "note": "C kicks to PF weakside who has slipped behind"},
            {"players": {"p4": (390, 210)},
             "arrows": [("p4", BASKET_R, "dribble")], "note": "PF wide open in weakside corner — shoot or drive"},
            {"arrows": [("p1", "p4", "pass")], "note": "Skip from top to weakside corner — direct option"},
            {"players": {"p4": (410, 215)},
             "arrows": [("p4", BASKET_R, "dribble")], "note": "PF corner catch — zone scrambled"},
            {"arrows": [("p2", "p1", "pass"), ("p1", "p4", "pass")],
             "note": "Reversal chain: SG-PG-PF — skip to get open shooter"},
            {"arrows": [("p3", "p5", "screen"), ("p5", BASKET_R, "cut")],
             "note": "Zone closing out: SF screens for C diving — lob option"},
        ],
    ),

    PlayDefinition(
        name="Zone Baseline Cut",
        category="set_play",
        description="SG sneaks baseline behind zone for easy layup",
        tags=["vs Zone", "Back-cut", "Backdoor"],
        pace="medium-to-fast",
        initial={
            "p1": (130, 140), "p2": (210, 90), "p3": (210, 190),
            "p4": (340, 68),  "p5": (240, 155),
        },
        frames=[
            {"note": "Zone Baseline: SG hides behind zone then cuts"},
            {"arrows": [("p1", "p2", "pass")], "note": "PG enters right wing — zone activates"},
            {"players": {"p2": (280, 90)},
             "arrows": [("p2", "p4", "pass")], "note": "SG swings to PF corner — zone shifts"},
            {"players": {"p3": (180, 195)},
             "arrows": [("p3", (350, 200), "cut")], "note": "SF sneaks baseline behind zone"},
            {"arrows": [("p4", "p3", "pass")], "note": "PF hits SF on baseline cut — zone ball-watches"},
            {"players": {"p3": (400, 205)},
             "arrows": [("p3", BASKET_R, "dribble")], "note": "SF layup — zone can't recover"},
            {"players": {"p5": (260, 155)},
             "arrows": [("p5", (260, 165), "cut")], "note": "C seals zone center — second option hub"},
            {"arrows": [("p1", "p5", "pass")], "note": "PG hits C in zone gap"},
            {"arrows": [("p5", "p3", "pass")], "note": "C hi-lo to corner — continues action"},
            {"players": {"p3": (420, 210)},
             "arrows": [("p3", BASKET_R, "dribble")], "note": "SF drives or shoots corner"},
            {"arrows": [("p2", "p1", "pass"), ("p1", "p3", "pass")],
             "note": "Reset chain — repeat baseline cut on other side"},
        ],
    ),

    PlayDefinition(
        name="Zone 1-3-1 Attack",
        category="set_play",
        description="Attack 1-3-1 zone with corner and high-low",
        tags=["vs Zone", "1-3-1", "Corner"],
        pace="medium",
        initial={
            "p1": (130, 140), "p2": (240, 78), "p3": (350, 215),
            "p4": (350, 65),  "p5": (240, 165),
        },
        frames=[
            {"note": "1-3-1 Zone Attack: corner man and high post are keys"},
            {"arrows": [("p1", "p2", "pass")], "note": "PG enters to SG at wing — 1-3-1 wing defender activates"},
            {"arrows": [("p5", (245, 155), "cut")], "note": "C floats to short corner gap in 1-3-1"},
            {"arrows": [("p2", "p5", "pass")], "note": "SG hits C in the gap — baseline defender must choose"},
            {"arrows": [("p5", "p3", "pass")], "note": "C hits SF in corner — baseline defender over-commits"},
            {"players": {"p3": (390, 220)},
             "arrows": [("p3", BASKET_R, "dribble")], "note": "SF corner 3 or drive — open!"},
            {"arrows": [("p4", (310, 90), "cut")], "note": "PF slips from high post to mid gap"},
            {"arrows": [("p2", "p4", "pass")], "note": "SG hits PF in mid gap — 2 defenders must choose"},
            {"players": {"p4": (330, 90)},
             "arrows": [("p4", BASKET_R, "dribble")], "note": "PF drives — 1-3-1 gap exploited"},
            {"arrows": [("p1", "p4", "pass"), ("p4", "p5", "pass")],
             "note": "Top-to-gap-to-corner chain — reset for 1-3-1 attack"},
            {"arrows": [("p5", "p3", "screen"), ("p3", BASKET_R, "cut")],
             "note": "SF cuts corner to basket — final action"},
        ],
    ),

    PlayDefinition(
        name="Zone Skip and Shoot",
        category="set_play",
        description="Rapid skip pass to create corner 3 vs any zone",
        tags=["vs Zone", "Skip", "3-point"],
        pace="fast",
        initial={
            "p1": (130, 140), "p2": (220, 82),  "p3": (380, 215),
            "p4": (380, 65),  "p5": (250, 140),
        },
        frames=[
            {"note": "Skip and Shoot: rapid ball movement for corner 3 vs zone"},
            {"arrows": [("p1", "p2", "pass")], "note": "PG enters right wing — zone loads"},
            {"arrows": [("p2", "p4", "pass")], "note": "SG to PF corner — zone shifts right"},
            {"players": {"p3": (140, 215)},
             "arrows": [("p3", (160, 215), "cut")], "note": "SF sneaks to weak-side corner behind zone"},
            {"arrows": [("p4", "p3", "pass")], "note": "PF skip pass to SF in weak corner — zone can't recover"},
            {"players": {"p3": (380, 215)},
             "arrows": [("p3", BASKET_R, "dribble")], "note": "SF open corner 3 — zone disrupted"},
            {"arrows": [("p5", (260, 140), "cut")], "note": "C floats to gap — second skip target"},
            {"arrows": [("p1", "p5", "pass")], "note": "PG hits C in gap if zone shifts to corner"},
            {"arrows": [("p5", "p3", "pass")], "note": "C skips to corner — continues attack"},
            {"players": {"p3": (410, 218)},
             "arrows": [("p3", BASKET_R, "dribble")], "note": "SF shoots — zone skip attack complete"},
            {"arrows": [("p1", "p4", "pass"), ("p4", "p3", "pass")],
             "note": "Alternate chain: PG direct to corner — skip to SF"},
        ],
    ),

    # ─── Section C: Transition & Fast Break (5 plays) ────────────────────────

    PlayDefinition(
        name="Secondary Break Horns",
        category="set_play",
        description="Push to Horns set off live turnover or rebound",
        tags=["Transition", "Horns", "Secondary"],
        pace="fast",
        initial={
            "p1": (70, 140), "p2": (140, 85), "p3": (140, 195),
            "p4": (230, 85), "p5": (230, 195),
        },
        frames=[
            {"note": "Secondary Break: Horns set up on the run"},
            {"arrows": [("p1", "p2", "pass")], "note": "PG pushes — outlet to SG on right"},
            {"players": {"p1": (200, 140)},
             "arrows": [("p1", (260, 140), "dribble")], "note": "PG fills middle, wings fill lanes"},
            {"arrows": [("p2", "p4", "cut"), ("p3", "p5", "cut")],
             "note": "SG and SF sprint ahead to fill wings"},
            {"players": {"p4": (290, 85), "p5": (290, 195)},
             "arrows": [("p1", "p4", "pass")], "note": "PG hits right wing — 3-on-2 if present"},
            {"arrows": [("p4", BASKET_R, "dribble")], "note": "Wing attacks — or kick to trailer"},
            {"players": {"p1": (320, 145)},
             "arrows": [("p1", (350, 95), "cut")], "note": "PG trails to elbow — Horns position"},
            {"players": {"p5": (320, 185)},
             "arrows": [("p5", (350, 185), "cut")], "note": "C trails to other elbow — Horns complete"},
            {"arrows": [("p4", "p1", "pass")], "note": "Wing feeds Horns: PG at right elbow gets ball"},
            {"arrows": [("p1", "p5", "screen"), ("p5", BASKET_R, "cut")],
             "note": "Horns PnR: PG hands off to C rolling"},
            {"arrows": [("p1", BASKET_R, "dribble")], "note": "PG drives if C covered — Horns attack complete"},
        ],
    ),

    PlayDefinition(
        name="Early Offense 4-Out",
        category="set_play",
        description="Early offense into 4-out-1-in quick hitter",
        tags=["Transition", "Early Offense", "4-Out"],
        pace="fast",
        initial={
            "p1": (80, 140), "p2": (160, 85), "p3": (160, 195),
            "p4": (260, 85), "p5": (180, 155),
        },
        frames=[
            {"note": "Early Offense: push fast, look for early advantage"},
            {"arrows": [("p1", "p2", "dribble")], "note": "PG pushes — SG and SF fly ahead"},
            {"arrows": [("p2", "p4", "cut"), ("p3", (260, 195), "cut")],
             "note": "Wings sprint to 3-point line on each side"},
            {"players": {"p4": (280, 85), "p3": (280, 195)},
             "arrows": [("p1", "p4", "pass")], "note": "PG hits right wing early — look for 3"},
            {"players": {"p4": (300, 82)},
             "arrows": [("p4", BASKET_R, "dribble")], "note": "Wing attacks if early 3 not there"},
            {"players": {"p5": (240, 150)},
             "arrows": [("p5", (280, 150), "cut")], "note": "C fills nail — 4-out-1-in set"},
            {"arrows": [("p4", "p5", "pass")], "note": "Wing passes to C at nail — 4-out-1-in"},
            {"arrows": [("p5", "p3", "pass")], "note": "C swings weak side — defense scrambles"},
            {"players": {"p3": (290, 195)},
             "arrows": [("p3", BASKET_R, "dribble")], "note": "Left wing attacks off the swing"},
            {"arrows": [("p2", "p1", "screen")], "note": "SG sets back-screen for PG — 2nd early action"},
            {"arrows": [("p4", "p1", "pass")], "note": "Wing hits PG off back-screen — early offense reset"},
        ],
    ),

    PlayDefinition(
        name="Transition PnR",
        category="set_play",
        description="PG pushes and calls ball screen in transition — quick PnR",
        tags=["Transition", "P&R", "Quick Hitter"],
        pace="fast",
        initial={
            "p1": (80, 140), "p2": (160, 90), "p3": (160, 190),
            "p4": (230, 90), "p5": (220, 155),
        },
        frames=[
            {"note": "Transition PnR: call screen before defense sets"},
            {"players": {"p1": (180, 140)},
             "arrows": [("p1", (220, 140), "dribble")], "note": "PG pushes hard — C sprints to set screen"},
            {"players": {"p5": (230, 140)},
             "arrows": [("p5", "p1", "screen")], "note": "C sets ball screen at half-court level"},
            {"players": {"p1": (280, 120)},
             "arrows": [("p1", BASKET_R, "dribble")], "note": "PG turns corner on PnR — attack basket"},
            {"arrows": [("p5", (350, 145), "cut")], "note": "C rolls hard — 2 defenders must choose"},
            {"arrows": [("p1", "p5", "pass")], "note": "PG hits rolling C if defense switches or hedges"},
            {"players": {"p5": (420, 148)},
             "arrows": [("p5", BASKET_R, "dribble")], "note": "C finishes roll — transition PnR complete"},
            {"arrows": [("p2", "p4", "cut")], "note": "SG and PF fill wings — kickout option"},
            {"arrows": [("p1", "p2", "pass")], "note": "PG kicks to SG if paint clogged"},
            {"players": {"p2": (310, 88)},
             "arrows": [("p2", BASKET_R, "dribble")], "note": "SG attacks from right wing — secondary"},
            {"arrows": [("p4", "p3", "cut")], "note": "PF spaces left wing — further spacing"},
        ],
    ),

    PlayDefinition(
        name="3-Man Weave",
        category="system",
        description="Three-man weave full-court drill and transition play",
        tags=["Transition", "Weave", "Fast Break"],
        pace="fast",
        initial={
            "p1": (30, 140), "p2": (30, 90), "p3": (30, 190),
            "p4": (220, 90), "p5": (220, 190),
        },
        frames=[
            {"note": "3-Man Weave: continuous passing and cutting in transition"},
            {"arrows": [("p1", "p2", "pass")], "note": "PG passes right to SG — then cuts behind"},
            {"players": {"p2": (110, 90)},
             "arrows": [("p2", "p3", "pass")], "note": "SG passes to SF on other side — weave"},
            {"players": {"p1": (110, 140)},
             "arrows": [("p1", (190, 140), "cut")], "note": "PG cuts behind SG — weave continues"},
            {"players": {"p3": (160, 195)},
             "arrows": [("p3", "p1", "pass")], "note": "SF passes to PG cutting middle"},
            {"players": {"p1": (220, 140)},
             "arrows": [("p1", (290, 140), "dribble")], "note": "PG advances — weave reaches half-court"},
            {"arrows": [("p2", "p4", "cut"), ("p3", "p5", "cut")],
             "note": "SG and SF fly to wings — 3-on-2 forming"},
            {"players": {"p4": (300, 88), "p5": (300, 192)},
             "arrows": [("p1", "p4", "pass")], "note": "PG hits right wing — 3-on-2 attack"},
            {"arrows": [("p4", BASKET_R, "dribble")], "note": "Wing attacks — draw defense, dish"},
            {"arrows": [("p4", "p5", "pass")], "note": "Wing hits opposite wing for lay-up"},
            {"players": {"p5": (430, 190)},
             "arrows": [("p5", BASKET_R, "dribble")], "note": "Left wing finishes — 3-man weave complete"},
        ],
    ),

    PlayDefinition(
        name="Pitch Ahead Break",
        category="set_play",
        description="PG pitches ahead to flying wing for fast break",
        tags=["Transition", "Fast Break", "Pitch"],
        pace="fast",
        initial={
            "p1": (80, 140), "p2": (130, 85), "p3": (130, 195),
            "p4": (280, 85), "p5": (170, 155),
        },
        frames=[
            {"note": "Pitch Ahead: PG finds running wing immediately"},
            {"arrows": [("p2", "p4", "cut")], "note": "SG sprints ahead — fills right lane"},
            {"arrows": [("p1", "p4", "pass")], "note": "PG pitches ahead to SG — before defense sets"},
            {"players": {"p4": (340, 82)},
             "arrows": [("p4", BASKET_R, "dribble")], "note": "SG attacks rim off pitch — 1-on-1"},
            {"arrows": [("p3", (280, 192), "cut")], "note": "SF fills left lane trailing"},
            {"players": {"p1": (230, 143)},
             "arrows": [("p1", (310, 145), "dribble")], "note": "PG follows — fills middle"},
            {"arrows": [("p4", "p3", "pass")], "note": "SG kicks to trailing SF if help comes"},
            {"players": {"p3": (340, 192)},
             "arrows": [("p3", BASKET_R, "dribble")], "note": "SF finishes on left side"},
            {"arrows": [("p5", (290, 152), "cut")], "note": "C trailers for secondary 3 or mid-range"},
            {"arrows": [("p4", "p5", "pass")], "note": "SG hits trailing C for mid-range"},
            {"players": {"p5": (320, 152)},
             "arrows": [("p5", BASKET_R, "dribble")], "note": "C finishes — pitch break complete"},
        ],
    ),

    # ─── Section D: Quick Hitters & ATO (9 plays) ────────────────────────────

    PlayDefinition(
        name="Quick Hitter Elevator",
        category="set_play",
        description="Two bigs close on shooter passing through gap (elevator)",
        tags=["ATO", "Quick Hitter", "Elevator"],
        pace="medium",
        initial={
            "p1": (130, 140), "p2": (155, 140), "p3": (300, 68),
            "p4": (240, 110), "p5": (240, 170),
        },
        frames=[
            {"note": "Elevator: SG runs through closing doors of two bigs"},
            {"arrows": [("p1", "p3", "pass")], "note": "PG enters to SF on wing — SG starts at basket"},
            {"arrows": [("p4", (240, 120), "cut"), ("p5", (240, 160), "cut")],
             "note": "PF and C align at elbows — elevator doors open"},
            {"players": {"p2": (245, 140)},
             "arrows": [("p2", (330, 88), "cut")], "note": "SG runs through elevator gap — shooters path"},
            {"arrows": [("p4", "p5", "screen")], "note": "PF and C close doors — screens set as SG exits"},
            {"arrows": [("p3", "p2", "pass")], "note": "SF hits SG coming out of elevator — catch and shoot"},
            {"players": {"p2": (345, 82)},
             "arrows": [("p2", BASKET_R, "dribble")], "note": "SG open 3 from wing — elevator complete"},
            {"arrows": [("p4", "p1", "screen")], "note": "PF back-screens for PG — 2nd action"},
            {"players": {"p1": (240, 142)},
             "arrows": [("p1", (310, 145), "cut")], "note": "PG cuts off back-screen"},
            {"arrows": [("p3", "p1", "pass")], "note": "SF hits PG on cut — finish at rim"},
        ],
    ),

    PlayDefinition(
        name="Quick Hitter Throwback",
        category="set_play",
        description="PG drives and dials back to shooter for catch-and-shoot 3",
        tags=["ATO", "Quick Hitter", "Throwback"],
        pace="fast",
        initial={
            "p1": (130, 140), "p2": (230, 85), "p3": (230, 195),
            "p4": (350, 68),  "p5": (350, 212),
        },
        frames=[
            {"note": "Throwback: PG attacks, pulls back for trailing shooter"},
            {"arrows": [("p1", "p2", "dribble")], "note": "PG attacks right wing — drawing defender"},
            {"players": {"p1": (250, 130)},
             "arrows": [("p1", (290, 125), "dribble")], "note": "PG drives hard toward basket"},
            {"arrows": [("p2", (160, 90), "cut")], "note": "SG steps out of corner as PG drives"},
            {"arrows": [("p1", "p2", "pass")], "note": "PG throwback to SG stepping back — catch and shoot"},
            {"players": {"p2": (165, 88)},
             "arrows": [("p2", BASKET_R, "dribble")], "note": "SG open 3 off the throwback!"},
            {"arrows": [("p5", "p1", "screen")], "note": "C sets back-screen as PG drives — 2nd option"},
            {"players": {"p1": (330, 130)},
             "arrows": [("p1", BASKET_R, "dribble")], "note": "If throwback not open: PG keeps driving"},
            {"arrows": [("p3", (280, 195), "cut")], "note": "SF cuts baseline — draw-and-kick option"},
            {"arrows": [("p1", "p3", "pass")], "note": "PG hits SF on baseline cut"},
            {"players": {"p3": (400, 210)},
             "arrows": [("p3", BASKET_R, "dribble")], "note": "SF finishes or kicks to corner"},
        ],
    ),

    PlayDefinition(
        name="Flare Screen ATO",
        category="set_play",
        description="Flare screen for shooter moving away from ball",
        tags=["ATO", "Quick Hitter", "Flare"],
        pace="medium",
        initial={
            "p1": (130, 140), "p2": (310, 68), "p3": (220, 195),
            "p4": (260, 90),  "p5": (260, 175),
        },
        frames=[
            {"note": "Flare Screen ATO: SG flares off PF screen — corner 3"},
            {"arrows": [("p1", "p4", "pass")], "note": "PG enters to PF at right elbow"},
            {"arrows": [("p5", "p2", "screen")], "note": "C sets flare screen for SG"},
            {"players": {"p2": (400, 68)},
             "arrows": [("p2", (420, 65), "cut")], "note": "SG flares off C screen to deep corner"},
            {"arrows": [("p4", "p2", "pass")], "note": "PF skips to SG in corner — open 3"},
            {"players": {"p2": (430, 65)},
             "arrows": [("p2", BASKET_R, "dribble")], "note": "SG open corner 3 — flare complete"},
            {"arrows": [("p4", "p1", "screen")], "note": "If SG not open: PF back-screens for PG"},
            {"players": {"p1": (210, 140)},
             "arrows": [("p1", (310, 142), "cut")], "note": "PG cuts off back-screen to basket"},
            {"arrows": [("p4", "p1", "pass")], "note": "PF hits PG on cut"},
            {"players": {"p1": (390, 145)},
             "arrows": [("p1", BASKET_R, "dribble")], "note": "PG finishes — flare ATO complete"},
        ],
    ),

    PlayDefinition(
        name="High Ball Screen Ice",
        category="set_play",
        description="PG uses high ball screen, defense iced — side PnR attack",
        tags=["Quick Hitter", "P&R", "Ice"],
        pace="fast",
        initial={
            "p1": (130, 140), "p2": (230, 88), "p3": (230, 192),
            "p4": (310, 68),  "p5": (220, 140),
        },
        frames=[
            {"note": "High Ball Screen: C meets PG above 3-point line — Ice defense"},
            {"players": {"p5": (200, 142)},
             "arrows": [("p5", "p1", "screen")], "note": "C sets high ball screen for PG"},
            {"players": {"p1": (250, 128)},
             "arrows": [("p1", (310, 120), "dribble")], "note": "PG turns corner — C rolls to rim"},
            {"players": {"p5": (330, 145)},
             "arrows": [("p5", BASKET_R, "cut")], "note": "C rolls hard — help defender must commit"},
            {"arrows": [("p1", BASKET_R, "dribble")], "note": "PG keeps if defender over-commits to roll"},
            {"arrows": [("p1", "p5", "pass")], "note": "PG hits C if defense switches — mismatch!"},
            {"players": {"p5": (400, 148)},
             "arrows": [("p5", BASKET_R, "dribble")], "note": "C finishes at rim on mismatch"},
            {"arrows": [("p2", "p4", "cut")], "note": "SG and PF space — kick-out options"},
            {"arrows": [("p1", "p2", "pass")], "note": "PG kicks to SG on wing if defense helps on roll"},
            {"players": {"p2": (305, 88)},
             "arrows": [("p2", BASKET_R, "dribble")], "note": "SG attacks from wing — High Screen Ice complete"},
            {"arrows": [("p4", "p3", "cut")], "note": "PF screens for SF — second action if stalled"},
        ],
    ),

    PlayDefinition(
        name="Ghost Screen",
        category="set_play",
        description="PG rejects the screen and ghost dribbles into lane",
        tags=["Quick Hitter", "Ghost Screen", "PnR"],
        pace="fast",
        initial={
            "p1": (130, 140), "p2": (240, 90), "p3": (240, 190),
            "p4": (330, 68),  "p5": (210, 140),
        },
        frames=[
            {"note": "Ghost Screen: C sets screen but PG rejects it inside"},
            {"players": {"p5": (205, 142)},
             "arrows": [("p5", "p1", "screen")], "note": "C sets ball screen — defender expects PG to go right"},
            {"players": {"p1": (195, 133)},
             "arrows": [("p1", (260, 135), "dribble")], "note": "PG rejects (ghosts) the screen — cuts inside of C"},
            {"arrows": [("p5", (350, 145), "cut")], "note": "C still rolls — creates confusion for defense"},
            {"players": {"p1": (300, 130)},
             "arrows": [("p1", BASKET_R, "dribble")], "note": "PG drives off ghost — defender on wrong side"},
            {"arrows": [("p1", "p5", "pass")], "note": "If help rotates: PG finds C on ghost roll"},
            {"players": {"p5": (420, 148)},
             "arrows": [("p5", BASKET_R, "dribble")], "note": "C finishes — ghost screen complete"},
            {"arrows": [("p2", "p4", "cut")], "note": "SG and PF space as kick-out options"},
            {"arrows": [("p1", "p2", "pass")], "note": "PG kicks to SG on wing if clogged"},
            {"players": {"p2": (310, 88)},
             "arrows": [("p2", BASKET_R, "dribble")], "note": "SG attacks wing — second action"},
            {"arrows": [("p3", "p5", "screen")], "note": "SF screens for C — motion continues weak side"},
        ],
    ),

    PlayDefinition(
        name="Blob Lob (BLOB)",
        category="inbound",
        description="Baseline out-of-bounds lob play for athletic big",
        tags=["Inbound", "Baseline", "BLOB", "Lob"],
        pace="fast",
        initial={
            "p1": (60, 140), "p2": (130, 105), "p3": (130, 175),
            "p4": (175, 108), "p5": (175, 172),
        },
        frames=[
            {"note": "BLOB Lob: set-up decoy action, C cuts to rim for lob"},
            {"arrows": [("p4", "p2", "screen"), ("p5", "p3", "screen")],
             "note": "PF and C set double box screens — decoy action"},
            {"players": {"p2": (230, 108)},
             "arrows": [("p2", (250, 95), "cut")], "note": "SG cuts off first screen — decoy route"},
            {"arrows": [("p5", (160, 172), "cut")], "note": "C releases from screen, cuts to rim for lob"},
            {"players": {"p5": (380, 140)},
             "arrows": [("p5", (430, 140), "cut")], "note": "C explodes to rim — lob target"},
            {"arrows": [("p1", "p5", "pass")], "note": "Inbounder lobs to C at rim — easy 2!"},
            {"players": {"p5": (450, 142)},
             "arrows": [("p5", BASKET_R, "dribble")], "note": "C catches lob — finish"},
            {"arrows": [("p4", "p3", "screen")], "note": "PF screens for SF — secondary action if lob denied"},
            {"arrows": [("p1", "p3", "pass")], "note": "Inbounder hits SF coming off secondary screen"},
            {"players": {"p3": (280, 175)},
             "arrows": [("p3", BASKET_R, "dribble")], "note": "SF attacks — BLOB secondary complete"},
        ],
    ),

    PlayDefinition(
        name="Ram Action",
        category="set_play",
        description="C screens for PG cutting off wing — direct action off ram",
        tags=["Quick Hitter", "Ram", "vs Man"],
        pace="medium-to-fast",
        initial={
            "p1": (130, 140), "p2": (230, 90), "p3": (230, 190),
            "p4": (350, 68),  "p5": (300, 140),
        },
        frames=[
            {"note": "Ram: PG enters wing, C rams (screens) for PG"},
            {"arrows": [("p1", "p2", "pass")], "note": "PG passes to SG on wing"},
            {"players": {"p5": (250, 140)},
             "arrows": [("p5", "p1", "screen")], "note": "C sets Ram screen for PG cutting to wing"},
            {"players": {"p1": (235, 142)},
             "arrows": [("p1", (290, 140), "cut")], "note": "PG cuts off C's Ram screen — gets ball on wing"},
            {"arrows": [("p2", "p1", "pass")], "note": "SG hits PG coming off Ram screen"},
            {"players": {"p1": (300, 140)},
             "arrows": [("p1", BASKET_R, "dribble")], "note": "PG attacks off Ram screen — drive to basket"},
            {"arrows": [("p5", (350, 140), "cut")], "note": "C slips to rim after Ram screen — 2nd threat"},
            {"arrows": [("p1", "p5", "pass")], "note": "PG hits C slipping to basket"},
            {"players": {"p5": (430, 143)},
             "arrows": [("p5", BASKET_R, "dribble")], "note": "C finishes — Ram action complete"},
            {"arrows": [("p4", "p3", "cut")], "note": "PF/SF space — kick-out options on 3"},
            {"arrows": [("p1", "p4", "pass")], "note": "PG kicks to PF corner if defense collapses"},
        ],
    ),

    PlayDefinition(
        name="Pop-and-Drive",
        category="set_play",
        description="Big pops to three, PG drives off the space created",
        tags=["Quick Hitter", "Pop", "Stretch 4"],
        pace="medium-to-fast",
        initial={
            "p1": (130, 140), "p2": (250, 85), "p3": (250, 195),
            "p4": (310, 68),  "p5": (270, 140),
        },
        frames=[
            {"note": "Pop-and-Drive: PF pops to 3, PG attacks vacated paint"},
            {"arrows": [("p5", "p1", "screen")], "note": "C sets ball screen for PG — pop action begins"},
            {"players": {"p4": (370, 68)},
             "arrows": [("p4", (390, 65), "cut")], "note": "PF pops to corner 3 — stretches defense"},
            {"players": {"p1": (250, 130)},
             "arrows": [("p1", (310, 130), "dribble")], "note": "PG attacks vacated paint — PF's defender must choose"},
            {"arrows": [("p1", "p4", "pass")], "note": "PG hits popped PF in corner — open 3"},
            {"players": {"p4": (400, 65)},
             "arrows": [("p4", BASKET_R, "dribble")], "note": "PF corner 3 or drive baseline"},
            {"arrows": [("p5", BASKET_R, "cut")], "note": "C rolls after screen — rim threat"},
            {"arrows": [("p1", "p5", "pass")], "note": "PG hits rolling C if PF covered"},
            {"players": {"p5": (400, 148)},
             "arrows": [("p5", BASKET_R, "dribble")], "note": "C finishes roll — Pop-and-Drive 2nd read"},
            {"arrows": [("p2", "p3", "cut")], "note": "SG/SF fill weak side — spacing maintained"},
            {"arrows": [("p1", "p2", "pass")], "note": "PG kicks to SG if paint clogged — reset"},
        ],
    ),

    PlayDefinition(
        name="Spread PnR",
        category="set_play",
        description="5-out spacing with ball screen — no help defenders",
        tags=["Quick Hitter", "P&R", "5-out", "Spread"],
        pace="fast",
        initial={
            "p1": (130, 140), "p2": (230, 80), "p3": (230, 200),
            "p4": (360, 68),  "p5": (360, 212),
        },
        frames=[
            {"note": "Spread PnR: 4 shooters spaced, C sets screen — no help possible"},
            {"arrows": [("p1", "p2", "dribble")], "note": "PG dribbles toward SG — spacing maintained"},
            {"players": {"p4": (270, 95)},
             "arrows": [("p4", "p1", "screen")], "note": "PF sets ball screen — leaves corner for screen"},
            {"players": {"p1": (290, 125)},
             "arrows": [("p1", BASKET_R, "dribble")], "note": "PG attacks — all 4 shooters spaced, no help"},
            {"arrows": [("p4", (350, 95), "cut")], "note": "PF pops or rolls after screen — choose based on D"},
            {"arrows": [("p1", "p4", "pass")], "note": "PG hits PF if help came — mismatch on pop"},
            {"players": {"p4": (360, 88)},
             "arrows": [("p4", BASKET_R, "dribble")], "note": "PF attacks from wing — Spread PnR 2nd read"},
            {"arrows": [("p5", "p3", "cut")], "note": "C and SF maintain spacing on weak side"},
            {"arrows": [("p1", "p2", "pass")], "note": "PG kicks to SG if both reads covered"},
            {"players": {"p2": (300, 78)},
             "arrows": [("p2", BASKET_R, "dribble")], "note": "SG attacks from wing — spread maintained"},
            {"arrows": [("p4", "p5", "screen")], "note": "PF screens for C — 2nd action from weak side"},
        ],
    ),
]


def build_template_seed_data() -> list[dict]:
    """Return list of dicts ready to upsert as template plays."""
    out = []
    for defn in TEMPLATE_PLAYS:
        svg_data = expand_play(defn)
        out.append({
            "name": defn.name,
            "category": defn.category,
            "description": defn.description,
            "tags": defn.tags,
            "pace": defn.pace,
            "is_template": True,
            "shared": True,
            "svg_data": svg_data,
            "svg_data_version": 2,
        })
    return out


def build_master_playbook_data() -> tuple[dict, list[dict]]:
    """Return (playbook_meta, [play_dicts]) for Master Playbook 2026."""
    playbook_meta = {
        "name": "Master Playbook 2026",
        "description": (
            "30 most effective high-school basketball plays of the last 10 years. "
            "Curated from FastModel Sports, FIBA coaching resources, and top HS programs. "
            "Sections: Half-court vs Man (A), vs Zone (B), Transition (C), Quick Hitters & ATO (D)."
        ),
        "is_system": True,
    }
    plays = []
    for defn in MASTER_2026_PLAYS:
        svg_data = expand_play(defn)
        plays.append({
            "name": defn.name,
            "category": defn.category,
            "description": defn.description,
            "tags": defn.tags,
            "pace": defn.pace,
            "is_template": False,
            "shared": True,
            "svg_data": svg_data,
            "svg_data_version": 2,
        })
    return playbook_meta, plays
