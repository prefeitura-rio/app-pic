// export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'https://services.staging.app.dados.rio/eai-agent' || 'http://localhost:8089';
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8089';

// Controls the login session duration.
// In development (process.env.NODE_ENV !== 'production'), it's set to null for an unlimited session.
// In production, it's set to 30 minutes.
export const SESSION_DURATION_MINUTES: number | null =
  process.env.NODE_ENV !== 'production' ? null : 30;