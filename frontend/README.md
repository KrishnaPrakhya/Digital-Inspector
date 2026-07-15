# Digital Inspector frontend

Next.js 15 App Router frontend for Digital Inspector. It provides microphone and file analysis, pasted text, browser-side OCR, a staged processing experience, local IndexedDB report history, charts, script education, and deterministic complaint export.

```powershell
Copy-Item .env.example .env.local
npm ci
npm run dev
```

Set `NEXT_PUBLIC_API_BASE_URL` to the FastAPI origin. Only public configuration belongs in frontend environment variables; the Groq key must remain in the backend deployment secret store.

Production checks:

```powershell
npm run lint
npm run build
```
