import uuid
from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from ..core.database import Base


class PlayerGameStats(Base):
    """Unified per-player, per-game stats: merges manual box-score numbers with
    CV/tracking metrics into one row, aggregable to season. One row per
    (player_id, game_id). `source` records which families are populated.

    - Box-score family (authoritative for shooting %): pts, fg*, ft*, ast, reb, etc.
    - CV/tracking family (physical + activity): minutes, distance, speed, possession,
      shots made/missed/attempted (rim-based), rebounds_cv, steals_cv.
    """

    __tablename__ = "player_game_stats"
    __table_args__ = (UniqueConstraint("player_id", "game_id", name="uq_pgs_player_game"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    game_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    season_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("seasons.id", ondelete="SET NULL"), nullable=True, index=True
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(12), default="cv")  # cv | box_score | both

    # ── Box-score family (manual CSV / authoritative shooting) ──
    pts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fgm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fga: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fg3m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fg3a: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ftm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ast: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stl: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blk: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tov: Mapped[int | None] = mapped_column(Integer, nullable=True)
    oreb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dreb: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── CV / tracking family ──
    minutes_played: Mapped[float] = mapped_column(Float, default=0.0)
    distance_m: Mapped[float] = mapped_column(Float, default=0.0)
    avg_speed_kmh: Mapped[float] = mapped_column(Float, default=0.0)
    max_speed_kmh: Mapped[float] = mapped_column(Float, default=0.0)
    possession_frames: Mapped[int] = mapped_column(Integer, default=0)
    shots_attempted_cv: Mapped[int] = mapped_column(Integer, default=0)
    shots_made_cv: Mapped[int] = mapped_column(Integer, default=0)
    shots_missed_cv: Mapped[int] = mapped_column(Integer, default=0)
    rebounds_cv: Mapped[int] = mapped_column(Integer, default=0)
    steals_cv: Mapped[int] = mapped_column(Integer, default=0)
    passes_cv: Mapped[int] = mapped_column(Integer, default=0)
