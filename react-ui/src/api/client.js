import axios from 'axios';

const api = axios.create({
  baseURL: process.env.REACT_APP_API_URL || 'http://127.0.0.1:8080',
  timeout: 120000,
});

export async function forecastTraffic(file, rolloutSteps = 5, signal) {
  const form = new FormData();
  form.append('file', file);
  form.append('rolloutSteps', String(rolloutSteps));
  const response = await api.post('/forecast/upload', form, { signal });
  const payload = response.data;
  const raw = payload.prediction || {};
  const rawRollout = raw.rollout || {};
  return {
    ...payload,
    prediction: {
      artifactVersion: raw.artifact_version,
      probability: raw.probability,
      predictedStage: raw.predicted_stage,
      quality: raw.quality || 'ok',
      qualityDetail: raw.quality_detail || null,
      topFeatures: (raw.top_5_features || []).map((feature) => ({
        feature: feature.feature,
        value: feature.value,
        shapValue: feature.shap_value,
      })),
      attentionSummary: {
        contextWindows: raw.attention_summary?.context_windows || 0,
        topContext: raw.attention_summary?.top_context_for_final_query || [],
        causalFutureAttentionMass:
          raw.attention_summary?.causal_future_attention_mass || 0,
      },
      rollout: {
        steps: rawRollout.steps || 0,
        probabilities: rawRollout.probabilities || [],
        predictedStages: rawRollout.predicted_stages || [],
        maxProbability: rawRollout.max_probability || 0,
      },
      latencyMs: raw.latency_ms || 0,
    },
  };
}

export async function listLiveInterfaces() {
  const response = await api.get('/live/interfaces');
  return response.data?.interfaces || [];
}

export async function startLiveSession({ interfaceName, durationSeconds, packetLimit, bpfFilter }) {
  const body = { interfaceName, mode: 'passive' };
  if (durationSeconds) body.durationSeconds = durationSeconds;
  if (packetLimit) body.packetLimit = packetLimit;
  if (bpfFilter) body.bpfFilter = bpfFilter;
  const response = await api.post('/live/sessions', body);
  return response.data;
}

export async function stopLiveSession(sessionId) {
  const response = await api.post(`/live/sessions/${encodeURIComponent(sessionId)}/stop`);
  return response.data;
}

export async function liveSessionStatus(sessionId) {
  const response = await api.get(`/live/sessions/${encodeURIComponent(sessionId)}`);
  return response.data;
}

export function openLiveEvents(sessionId, handlers) {
  const base = (process.env.REACT_APP_API_URL || 'http://127.0.0.1:8080').replace(/\/$/, '');
  const source = new EventSource(`${base}/live/sessions/${encodeURIComponent(sessionId)}/events`);
  const onState = (event) => handlers.onState?.(JSON.parse(event.data));
  const onCounter = (event) => handlers.onCounter?.(JSON.parse(event.data));
  const onPrediction = (event) => handlers.onPrediction?.(JSON.parse(event.data));
  source.addEventListener('state', onState);
  source.addEventListener('counter', onCounter);
  source.addEventListener('prediction', onPrediction);
  source.onerror = (error) => handlers.onError?.(error);
  return () => source.close();
}

export function explainApiError(error) {
  if (axios.isCancel(error)) return 'Analysis cancelled.';
  const detail = error.response?.data?.detail || error.response?.data?.message;
  if (detail) return detail;
  if (error.code === 'ECONNABORTED') {
    return 'Analysis timed out. Keep the services running and try again.';
  }
  if (!error.response) {
    return 'The local KAIROS engine is unreachable. Start Java and Python, then retry.';
  }
  return `Analysis failed (HTTP ${error.response.status}). Try the file again.`;
}
