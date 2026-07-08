import axios from 'axios';
// withCredentials so the signed session cookie (login) rides along.
const http = axios.create({ baseURL: '/api', timeout: 200_000, withCredentials: true });

// Auth
export const getAuth = () => http.get('/auth/me').then(r => r.data);
export const logout = () => http.post('/auth/logout').then(r => r.data);
export const loginUrl = (provider = 'google') => `/api/auth/login/${provider}`;

export const submitResearch = (query, paperText, paperFilename, maxIterations = 3) =>
  runJob('/research/start', { query, paper_text: paperText, paper_filename: paperFilename, max_iterations: maxIterations });

export const uploadPaper = (file) => {
  const fd = new FormData(); fd.append('file', file);
  // 180-second timeout: the first-ever upload triggers a cold-start model
  // load (~80 MB sentence-transformers) which can take up to 90 s.
  // Subsequent uploads are fast because the model stays in memory.
  return http.post('/upload-paper', fd, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 180_000 }).then(r => r.data);
};

export const getResult = (id) => http.get(`/research/${id}`).then(r => r.data);
export const getHealth = () => http.get('/health').then(r => r.data);
export const getTopology = () => http.get('/graph-topology').then(r => r.data);

// ── Background-job runner ─────────────────────────────────────────────────────
// The slow LLM endpoints (summarize / teach / visualize / teach-section) go
// through a start-then-poll flow: hosting proxies (e.g. Hugging Face Spaces)
// kill any request that holds the connection longer than ~60 s, so no single
// HTTP call here ever takes more than a moment.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const runJob = async (startPath, body, { interval = 2500, maxWait = 300_000 } = {}) => {
  const { job_id } = (await http.post(startPath, body)).data;
  const t0 = Date.now();
  for (;;) {
    await sleep(interval);
    const { status, result, error } = (await http.get(`/paper/job/${job_id}`)).data;
    if (status === 'done') return result;
    if (status === 'error') throw new Error(error || 'Processing failed');
    if (Date.now() - t0 > maxWait) throw new Error('Timed out waiting for the result');
  }
};

// Paper mode — all calls are scoped to a session_id returned by uploadPaper
export const summarizePaper = (sessionId, filename) =>
  runJob('/paper/summarize/start', { session_id: sessionId, filename });

export const askPaper = (question, sessionId) =>
  runJob('/paper/ask/start', { question, session_id: sessionId });

export const deleteSession = (sessionId) =>
  http.delete(`/paper/session/${sessionId}`).then(r => r.data);

export const visualizePaper = (sessionId) =>
  runJob('/paper/visualize/start', { session_id: sessionId });

export const teachPaper = (sessionId) =>
  runJob('/paper/teach/start', { session_id: sessionId });

export const teachSection = (sessionId, section, summary) =>
  runJob('/paper/teach-section/start', { session_id: sessionId, section, summary });

// Vision explanation of a single figure (+ follow-up Q&A).
// history: [{role:'user'|'assistant', content}] for follow-ups; omit for the first call.
export const explainFigure = (sessionId, figId, question = null, history = null) =>
  runJob('/paper/figure-explain/start', { session_id: sessionId, fig_id: figId, question, history });

export const fetchPaperFromUrl = (url, abstract, title) =>
  http.post('/paper/from-url', { url, abstract, title }, { timeout: 60_000 }).then(r => r.data);

export const explainSubQuestion = (question, context, api_results) =>
  http.post('/research/subquestion', { question, context, api_results }, { timeout: 90_000 }).then(r => r.data);

// Paper reader — figures + PDF
export const getPaperFigures = (sessionId) =>
  http.get(`/paper/figures/${sessionId}`).then(r => r.data);

export const paperFigureUrl = (sessionId, figId) => `/api/paper/figure/${sessionId}/${figId}`;
export const paperPdfUrl = (sessionId) => `/api/paper/pdf/${sessionId}`;

// Runtime flags (e.g. whether the shared Library is enabled on this deployment)
export const getConfig = () => http.get('/config').then(r => r.data);

// Library + persistence (P2)
export const getLibrary = () => http.get('/paper/library').then(r => r.data);
export const getPaperMeta = (sessionId) => http.get(`/paper/${sessionId}`).then(r => r.data);
export const getPaperChat = (sessionId) => http.get(`/paper/${sessionId}/chat`).then(r => r.data);

// Highlights
export const getHighlights = (sessionId) => http.get(`/paper/${sessionId}/highlights`).then(r => r.data);
export const createHighlight = (sessionId, body) =>
  http.post(`/paper/${sessionId}/highlights`, body).then(r => r.data);
export const updateHighlightNote = (id, note) =>
  http.patch(`/paper/highlights/${id}`, { note }).then(r => r.data);
export const deleteHighlight = (id) => http.delete(`/paper/highlights/${id}`).then(r => r.data);
