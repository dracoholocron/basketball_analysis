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

export async function uploadVideo(gameId: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post(`/games/${gameId}/video`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function getGameMetrics(gameId: string) {
  const { data } = await api.get(`/games/${gameId}/metrics`);
  return data;
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
export async function listPlays(matchupId?: string, skip = 0, limit = 100) {
  const { data } = await api.get("/plays", { params: { matchup_id: matchupId, skip, limit } });
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
  onProgress?: (job: { status: string; progress_pct: number; current_stage: string }) => void,
  intervalMs = 3000,
  timeoutMs = 3_600_000,
): Promise<unknown> {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const timer = setInterval(async () => {
      if (Date.now() - start > timeoutMs) {
        clearInterval(timer);
        reject(new Error("Job polling timeout"));
        return;
      }
      try {
        const job = await getJob(jobId);
        onProgress?.(job);
        if (job.status === "done") {
          clearInterval(timer);
          resolve(job);
        } else if (job.status === "failed") {
          clearInterval(timer);
          reject(new Error(job.error_message ?? "Job failed"));
        }
      } catch (err) {
        clearInterval(timer);
        reject(err);
      }
    }, intervalMs);
  });
}
