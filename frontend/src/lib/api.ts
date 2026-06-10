import axios from "axios";
import Cookies from "js-cookie";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const api = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = Cookies.get("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// ── Auth ──────────────────────────────────────────────────────────────────────
export async function login(email: string, password: string) {
  const form = new FormData();
  form.append("username", email);
  form.append("password", password);
  const { data } = await axios.post(`${BASE_URL}/api/v1/auth/token`, form, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  Cookies.set("access_token", data.access_token, { expires: 1 });
  return data;
}

export function logout() {
  Cookies.remove("access_token");
}

export async function getMe() {
  const { data } = await api.get("/auth/me");
  return data as { id: string; email: string; full_name: string | null; role: string; organization_id: string; is_active: boolean };
}

// ── Games ─────────────────────────────────────────────────────────────────────
export async function listGames(skip = 0, limit = 20) {
  const { data } = await api.get("/games", { params: { skip, limit } });
  return data;
}

export async function createGame(payload: Record<string, unknown>) {
  const { data } = await api.post("/games", payload);
  return data;
}

export async function getGame(id: string) {
  const { data } = await api.get(`/games/${id}`);
  return data;
}

/** Upload a video file. Returns the VideoAsset — does NOT start analysis. */
export async function uploadVideo(gameId: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post(`/games/${gameId}/video`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data as { id: string; game_id: string; filename: string; file_size_bytes: number | null };
}

export interface AnalysisOptions {
  pose_player_filter?: number[];
}

/** Start analysis of the already-uploaded video for a game. Returns a Job. */
export async function analyzeGame(gameId: string, opts: AnalysisOptions = {}) {
  const { data } = await api.post(`/games/${gameId}/analyze`, opts);
  return data;
}

/** Update game settings (show_poses, jerseys, court_level, etc.). */
export async function updateGameSettings(
  gameId: string,
  payload: {
    show_poses?: boolean;
    court_level?: string;
    is_half_court?: boolean;
    home_team1_jersey?: string;
    away_team2_jersey?: string;
    home_team_name?: string;
    away_team_name?: string;
    analysis_start_s?: number | null;
    analysis_end_s?: number | null;
    ball_tracking_quality?: string;
  }
) {
  const { data } = await api.patch(`/games/${gameId}`, payload);
  return data;
}

export async function deleteJob(jobId: string): Promise<void> {
  await api.delete(`/jobs/${jobId}`);
}

/** Check if a game has a video uploaded (non-throwing). */
export async function hasGameVideo(gameId: string): Promise<boolean> {
  try {
    await api.head(`/games/${gameId}/raw-video`);
    return true;
  } catch {
    // HEAD on the redirect doesn't work well; try GET instead
    try {
      await api.get(`/games/${gameId}/raw-video`, { maxRedirects: 0 });
      return true;
    } catch (err: unknown) {
      // 302 redirect = video exists, 404 = no video
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status && status >= 300 && status < 400) return true;
      return false;
    }
  }
}

export async function getGameMetrics(gameId: string) {
  const { data } = await api.get(`/games/${gameId}/metrics`);
  return data;
}

// ── Annotations / homography calibration ──────────────────────────────────────

export interface LandmarkPoint {
  landmark_id: string;
  pixel: [number, number];
  frame_t: number;
}

export interface GameAnnotation {
  id: string;
  game_id: string;
  landmarks: LandmarkPoint[] | null;
  camera_motion: "static" | "moderate" | "moving" | "unknown" | null;
}

export interface LandmarkCatalogItem {
  id: string;
  label: string;
  category: "corner" | "circle" | "line" | "key" | "hoop";
}

export async function getGameVideoUrl(gameId: string): Promise<string> {
  const { data } = await api.get<{ url: string }>(`/games/${gameId}/raw-video`);
  return data.url;
}

export async function getGameAnnotation(gameId: string): Promise<GameAnnotation | null> {
  try {
    const { data } = await api.get(`/games/${gameId}/annotation`);
    return data;
  } catch {
    return null;
  }
}

export async function putGameAnnotation(
  gameId: string,
  landmarks: LandmarkPoint[],
  camera_motion?: string,
): Promise<GameAnnotation> {
  const { data } = await api.put(`/games/${gameId}/annotation`, {
    landmarks,
    camera_motion: camera_motion ?? null,
  });
  return data;
}

export async function detectCameraMotion(gameId: string): Promise<{
  motion: string;
  ssim_avg: number | null;
  ssim_samples: number[];
}> {
  const { data } = await api.post(`/games/${gameId}/detect-motion`);
  return data;
}

// ── Ball annotation (SAM2 tracking + fine-tune labels) ──────────────────────

export interface BallPoint {
  frame_t: number;
  pixel: [number, number];   // intrinsic video resolution
  visible: boolean;          // false = ball NOT present in this frame
}

export interface BallAnnotation {
  id: string;
  game_id: string;
  points: BallPoint[] | null;
}

export async function getBallAnnotation(gameId: string): Promise<BallAnnotation | null> {
  try {
    const { data } = await api.get(`/games/${gameId}/ball-annotation`);
    return data;
  } catch {
    return null;
  }
}

export async function putBallAnnotation(
  gameId: string,
  points: BallPoint[],
): Promise<BallAnnotation> {
  const { data } = await api.put(`/games/${gameId}/ball-annotation`, { points });
  return data;
}

/** Trigger a background fine-tune of the ball detector on accumulated SAM2 auto-labels. */
export async function triggerBallFinetune(epochs = 60): Promise<{ task_id: string; status: string; epochs: number }> {
  const { data } = await api.post(`/admin/finetune-ball`, null, { params: { epochs } });
  return data;
}

// ── Hoop annotation (rim/backboard boxes for shot counting) ─────────────────

export interface HoopBox {
  frame_t: number;
  bbox: [number, number, number, number];  // intrinsic resolution
  kind: "rim" | "backboard";
  hoop_id?: number;  // which physical hoop this box belongs to (0, 1, …)
}

export interface HoopAnnotation {
  id: string;
  game_id: string;
  hoops: HoopBox[] | null;
}

export async function getHoopAnnotation(gameId: string): Promise<HoopAnnotation | null> {
  try {
    const { data } = await api.get(`/games/${gameId}/hoop-annotation`);
    return data;
  } catch {
    return null;
  }
}

export async function putHoopAnnotation(gameId: string, hoops: HoopBox[]): Promise<HoopAnnotation> {
  const { data } = await api.put(`/games/${gameId}/hoop-annotation`, { hoops });
  return data;
}

export async function getLandmarkCatalog(): Promise<LandmarkCatalogItem[]> {
  const { data } = await api.get("/landmarks/catalog");
  return data;
}

// ── Roster mapping (detected identities → real players) ─────────────────────────
export interface RosterPlayer { id: string; name: string; jersey_number?: string | null; }
export interface MappingIdentity {
  track_id: number;
  display_label?: string | null;
  jersey_number?: string | null;
  team_id?: number | null;       // 1 = home, 2 = away
  minutes_played: number;
  player_id?: string | null;
}
export interface PlayerMapping {
  game_id: string;
  job_id: string;
  home_team?: RosterPlayer | null;
  away_team?: RosterPlayer | null;
  home_roster: RosterPlayer[];
  away_roster: RosterPlayer[];
  identities: MappingIdentity[];
}
export interface PlayerMapItem {
  track_id: number;
  player_id?: string | null;
  new_player_name?: string | null;
  team_id?: number | null;
  jersey_number?: string | null;
}

export async function getPlayerMapping(gameId: string): Promise<PlayerMapping> {
  const { data } = await api.get(`/games/${gameId}/player-mapping`);
  return data;
}

export async function putPlayerMapping(gameId: string, mappings: PlayerMapItem[]): Promise<PlayerMapping> {
  const { data } = await api.put(`/games/${gameId}/player-mapping`, { mappings });
  return data;
}

// ── Player / Team profile stats (player_game_stats aggregation) ─────────────────
export async function getPlayerStats(playerId: string, seasonId?: string) {
  const { data } = await api.get(`/players/${playerId}/stats`, {
    params: seasonId ? { season_id: seasonId } : {},
  });
  return data;
}

export async function getTeamStats(teamId: string, seasonId?: string) {
  const { data } = await api.get(`/teams/${teamId}/stats`, {
    params: seasonId ? { season_id: seasonId } : {},
  });
  return data;
}

// ── Lab: SAM 3 pilot (experimental, isolated) ───────────────────────────────────
export async function sam3Track(gameId: string, prompt: string, startS?: number, endS?: number | null) {
  const { data } = await api.post(`/lab/sam3/track`, {
    game_id: gameId, prompt, start_s: startS ?? 0, end_s: endS ?? null,
  });
  return data as { task_id: string; queued: boolean };
}

export async function sam3Result(taskId: string) {
  const { data } = await api.get(`/lab/sam3/result/${taskId}`);
  return data as {
    state: string; error?: string; output_url?: string | null;
    result?: { coverage_pct?: number; frames?: number; frames_with_object?: number; prompt?: string };
  };
}

// ── Seasons ───────────────────────────────────────────────────────────────────
export async function listSeasons(skip = 0, limit = 50) {
  const { data } = await api.get("/seasons", { params: { skip, limit } });
  return data;
}

export async function createSeason(payload: Record<string, unknown>) {
  const { data } = await api.post("/seasons", payload);
  return data;
}

// ── Organizations ─────────────────────────────────────────────────────────────
export async function listOrganizations(skip = 0, limit = 50) {
  const { data } = await api.get("/organizations", { params: { skip, limit } });
  return data;
}

export async function createOrganization(payload: Record<string, unknown>) {
  const { data } = await api.post("/organizations", payload);
  return data;
}

// ── Teams ─────────────────────────────────────────────────────────────────────
export async function listTeams(skip = 0, limit = 50) {
  const { data } = await api.get("/teams", { params: { skip, limit } });
  return data;
}

export async function createTeam(payload: Record<string, unknown>) {
  const { data } = await api.post("/teams", payload);
  return data;
}

// ── Players ───────────────────────────────────────────────────────────────────
export async function listPlayers(teamId?: string, skip = 0, limit = 100) {
  const { data } = await api.get("/players", { params: { team_id: teamId, skip, limit } });
  return data;
}

export async function createPlayer(payload: Record<string, unknown>) {
  const { data } = await api.post("/players", payload);
  return data;
}

export async function updatePlayer(playerId: string, payload: Record<string, unknown>) {
  const { data } = await api.put(`/players/${playerId}`, payload);
  return data;
}

export async function deletePlayer(playerId: string) {
  await api.delete(`/players/${playerId}`);
}

// ── Jobs ──────────────────────────────────────────────────────────────────────
export async function listJobs(skip = 0, limit = 30) {
  const { data } = await api.get("/jobs", { params: { skip, limit } });
  return data;
}

export async function getJob(jobId: string) {
  const { data } = await api.get(`/jobs/${jobId}`);
  return data;
}

export async function getLatestDoneJobForGame(gameId: string) {
  const { data } = await api.get("/jobs", {
    params: { game_id: gameId, status: "done", limit: 1 },
  });
  return Array.isArray(data) ? data[0] : (data as { items?: unknown[] }).items?.[0];
}

export async function getLatestActiveJobForGame(gameId: string) {
  const [running, pending] = await Promise.all([
    api.get("/jobs", { params: { game_id: gameId, status: "running", limit: 1 } }).then(r => Array.isArray(r.data) ? r.data[0] : null).catch(() => null),
    api.get("/jobs", { params: { game_id: gameId, status: "pending", limit: 1 } }).then(r => Array.isArray(r.data) ? r.data[0] : null).catch(() => null),
  ]);
  return running ?? pending ?? null;
}

// ── Matchups ──────────────────────────────────────────────────────────────────
export async function listMatchups(skip = 0, limit = 50) {
  const { data } = await api.get("/matchups", { params: { skip, limit } });
  return data;
}

export async function getUpcomingMatchups(limit = 5) {
  const { data } = await api.get("/matchups/upcoming", { params: { limit } });
  return data;
}

export async function getMatchup(matchupId: string) {
  const { data } = await api.get(`/matchups/${matchupId}`);
  return data;
}

export async function createMatchup(payload: Record<string, unknown>) {
  const { data } = await api.post("/matchups", payload);
  return data;
}

export async function updateMatchup(matchupId: string, payload: Record<string, unknown>) {
  const { data } = await api.put(`/matchups/${matchupId}`, payload);
  return data;
}

export async function updateMatchupNotes(matchupId: string, notes: Record<string, unknown>) {
  const { data } = await api.patch(`/matchups/${matchupId}/notes`, notes);
  return data;
}

export async function deleteMatchup(matchupId: string) {
  await api.delete(`/matchups/${matchupId}`);
}

export async function updateMatchupClock(matchupId: string, payload: Record<string, unknown>) {
  const { data } = await api.patch(`/matchups/${matchupId}/clock`, payload);
  return data;
}

export async function getPrepStatus(matchupId: string) {
  const { data } = await api.get(`/matchups/${matchupId}/prep-status`);
  return data;
}

// ── Scouting Reports ──────────────────────────────────────────────────────────
// NOTE: Backend endpoints for scouting reports are planned; these call the
// matchup-scoped sub-resources. Pages degrade gracefully on 404.
export async function getScoutingReport(matchupId: string) {
  const { data } = await api.get(`/matchups/${matchupId}/scouting-report`);
  return data;
}

export async function generateScoutingReport(matchupId: string) {
  const { data } = await api.post(`/matchups/${matchupId}/scouting-report/generate`);
  return data;
}

export async function updateScoutingNotes(reportId: string, notes: string) {
  const { data } = await api.patch(`/matchups/scouting-reports/${reportId}/notes`, { coach_notes: notes });
  return data;
}

export async function getVideoInsights(matchupId: string) {
  const { data } = await api.get(`/matchups/${matchupId}/video-insights`);
  return data;
}

// ── Simulation ────────────────────────────────────────────────────────────────
export async function getSimulation(matchupId: string) {
  try {
    const { data } = await api.get(`/matchups/${matchupId}/simulation`);
    return data;
  } catch {
    return null;
  }
}

export async function runSimulation(matchupId: string, payload?: Record<string, unknown>) {
  const { data } = await api.post(`/matchups/${matchupId}/simulate`, payload ?? {});
  return data;
}

// ── Game Events (live tracker) ────────────────────────────────────────────────
export async function listGameEvents(matchupId: string, skip = 0, limit = 200) {
  const { data } = await api.get(`/matchups/${matchupId}/events`, { params: { skip, limit } });
  return data;
}

export async function createGameEvent(matchupId: string, payload: Record<string, unknown>) {
  const { data } = await api.post(`/matchups/${matchupId}/events`, payload);
  return data;
}

export async function deleteGameEvent(matchupId: string, eventId: string) {
  await api.delete(`/matchups/${matchupId}/events/${eventId}`);
}

export async function getLiveKeysStatus(matchupId: string) {
  const { data } = await api.get(`/matchups/${matchupId}/live-keys-status`);
  return data;
}

export async function getEventHeatmap(matchupId: string) {
  const { data } = await api.get(`/matchups/${matchupId}/event-heatmap`);
  return data;
}

export async function setPriorityKey(
  matchupId: string,
  keyId: string,
  isPriority: boolean,
  priorityRank?: number,
) {
  const { data } = await api.patch(`/matchups/${matchupId}/keys/${keyId}/priority`, {
    is_priority: isPriority,
    priority_rank: priorityRank,
  });
  return data;
}

export async function triggerHalftimeResim(matchupId: string) {
  const { data } = await api.post(`/matchups/${matchupId}/halftime-resim`);
  return data;
}

// ── Plays ─────────────────────────────────────────────────────────────────────
export async function listPlays(matchupId?: string, skip = 0, limit = 100, playbookId?: string) {
  const { data } = await api.get("/plays", {
    params: { matchup_id: matchupId, skip, limit, playbook_id: playbookId },
  });
  return data;
}

export async function getPlay(playId: string) {
  const { data } = await api.get(`/plays/${playId}`);
  return data;
}

export async function createPlay(payload: Record<string, unknown>) {
  const { data } = await api.post("/plays", payload);
  return data;
}

export async function updatePlay(playId: string, payload: Record<string, unknown>) {
  const { data } = await api.put(`/plays/${playId}`, payload);
  return data;
}

export async function deletePlay(playId: string) {
  await api.delete(`/plays/${playId}`);
}

// ── Playbooks ─────────────────────────────────────────────────────────────────
export async function listPlaybooks() {
  const { data } = await api.get("/playbooks");
  return data;
}

export async function getPlaybook(playbookId: string) {
  const { data } = await api.get(`/playbooks/${playbookId}`);
  return data;
}

export async function createPlaybook(payload: { name: string; description?: string }) {
  const { data } = await api.post("/playbooks", payload);
  return data;
}

export async function deletePlaybook(playbookId: string) {
  await api.delete(`/playbooks/${playbookId}`);
}

// ── Box Scores ────────────────────────────────────────────────────────────────
export async function listBoxScores(params?: {
  game_id?: string;
  team_id?: string;
  season_id?: string;
  skip?: number;
  limit?: number;
}) {
  const { data } = await api.get("/box-scores", { params });
  return data;
}

export async function createBoxScore(payload: Record<string, unknown>) {
  const { data } = await api.post("/box-scores", payload);
  return data;
}

export async function deleteBoxScore(boxScoreId: string) {
  await api.delete(`/box-scores/${boxScoreId}`);
}

export async function importBoxScores(gameId: string) {
  const { data } = await api.post("/box-scores/import", null, { params: { game_id: gameId } });
  return data;
}

export async function importBoxScoresCsv(gameId: string, teamId: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post("/box-scores/import-csv", form, {
    params: { game_id: gameId, team_id: teamId },
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function getTeamAverages(teamId: string, seasonId?: string) {
  const { data } = await api.get(`/box-scores/team-averages`, {
    params: { team_id: teamId, season_id: seasonId },
  });
  return data;
}

// ── Training Sessions ─────────────────────────────────────────────────────────
export async function listTrainingSessions(skip = 0, limit = 20) {
  const { data } = await api.get("/training", { params: { skip, limit } });
  return data;
}

export async function createTrainingSession(payload: { sport_drill?: string }) {
  const { data } = await api.post("/training", payload);
  return data;
}

export async function getTrainingSession(id: string) {
  const { data } = await api.get(`/training/${id}`);
  return data;
}

export async function uploadTrainingVideo(sessionId: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post(`/training/${sessionId}/upload-video`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function triggerTrainingAnalysis(sessionId: string, poseEnabled = true) {
  const { data } = await api.post(`/training/${sessionId}/analyze`, null, {
    params: { pose_enabled: poseEnabled },
  });
  return data;
}

export async function getTrainingHighlights(sessionId: string) {
  const { data } = await api.get(`/training/${sessionId}/highlights`);
  return data;
}

export async function getTrainingCvEvents(sessionId: string) {
  const { data } = await api.get(`/training/${sessionId}/cv-events`);
  return data;
}

// ── Polling ───────────────────────────────────────────────────────────────────
export async function pollJobUntilDone(
  jobId: string,
  onProgress?: (job: { status: string; progress_pct: number; current_stage: string; error_message?: string | null }) => void,
  intervalMs = 4000,
  timeoutMs = 3_600_000,
): Promise<unknown> {
  const start = Date.now();
  let consecutiveErrors = 0;
  const MAX_CONSECUTIVE_ERRORS = 10; // tolerate ~40s of network outage

  return new Promise((resolve, reject) => {
    const timer = setInterval(async () => {
      if (Date.now() - start > timeoutMs) {
        clearInterval(timer);
        reject(new Error("Job polling timeout"));
        return;
      }
      try {
        const job = await getJob(jobId);
        consecutiveErrors = 0; // reset on success
        onProgress?.(job);
        if (job.status === "done") {
          clearInterval(timer);
          resolve(job);
        } else if (job.status === "failed") {
          clearInterval(timer);
          reject(new Error(job.error_message ?? "Job failed"));
        }
      } catch {
        // Transient network error — keep polling unless too many in a row
        consecutiveErrors++;
        if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
          clearInterval(timer);
          reject(new Error("Lost connection to server. Refresh the page to check status."));
        }
        // Otherwise silently retry
      }
    }, intervalMs);
  });
}
