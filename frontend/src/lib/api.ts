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

// ── Jobs ──────────────────────────────────────────────────────────────────────
export async function getJob(jobId: string) {
  const { data } = await api.get(`/jobs/${jobId}`);
  return data;
}

export async function pollJobUntilDone(
  jobId: string,
  onProgress?: (job: { status: string; progress_pct: number; current_stage: string }) => void,
  intervalMs = 3000,
  timeoutMs = 3600_000,
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
