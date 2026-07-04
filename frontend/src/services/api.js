import axios from 'axios';
// withCredentials so the signed session cookie (login) rides along.
const http = axios.create({ baseURL: '/api', timeout: 200_000, withCredentials: true });

// Auth
export const getAuth = () => http.get('/auth/me').then(r => r.data);
export const logout = () => http.post('/auth/logout').then(r => r.data);
export const loginUrl = (provider = 'google') => `/api/auth/login/${provider}`;

export const submitResearch = (query, paperText, paperFilename, maxIterations = 3) =>
  http.post('/research', { query, paper_text: paperText, paper_filename: paperFilename, max_iterations: maxIterations }).then(r => r.data);

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

// Paper mode — all calls are scoped to a session_id returned by uploadPaper
export const summarizePaper = (sessionId, filename) =>
  http.post('/paper/summarize', { session_id: sessionId, filename }, { timeout: 180_000 }).then(r => r.data);

export const askPaper = (question, sessionId) =>
  http.post('/paper/ask', { question, session_id: sessionId }, { timeout: 120_000 }).then(r => r.data);

export const deleteSession = (sessionId) =>
  http.delete(`/paper/session/${sessionId}`).then(r => r.data);

export const visualizePaper = (sessionId) =>
  http.post('/paper/visualize', { session_id: sessionId }, { timeout: 120_000 }).then(r => r.data);

export const teachPaper = (sessionId) =>
  http.post('/paper/teach', { session_id: sessionId }, { timeout: 180_000 }).then(r => r.data);

export const teachSection = (sessionId, section, summary) =>
  http.post('/paper/teach-section', { session_id: sessionId, section, summary }, { timeout: 120_000 }).then(r => r.data);

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
