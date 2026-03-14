import axios from 'axios';
const http = axios.create({ baseURL: '/api', timeout: 200_000 });

export const submitResearch = (query, paperText, paperFilename, maxIterations = 3) =>
  http.post('/research', { query, paper_text: paperText, paper_filename: paperFilename, max_iterations: maxIterations }).then(r => r.data);

export const uploadPaper = (file) => {
  const fd = new FormData(); fd.append('file', file);
  return http.post('/upload-paper', fd, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60_000 }).then(r => r.data);
};

export const getResult = (id) => http.get(`/research/${id}`).then(r => r.data);
export const getHealth = () => http.get('/health').then(r => r.data);
export const getTopology = () => http.get('/graph-topology').then(r => r.data);
