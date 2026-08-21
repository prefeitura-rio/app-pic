import { jwtDecode } from "jwt-decode";

/**
 * Check if a JWT token is expired
 */
export function isJwtExpired(token: string): boolean {
  try {
    const decoded: { exp?: number } = jwtDecode(token);
    if (!decoded.exp) return true;

    const now = Math.floor(Date.now() / 1000);
    return decoded.exp < now;
  } catch {
    return true; // If we can't decode, consider it expired
  }
}

/**
 * Get user info from JWT token
 */
export function getUserInfoFromToken(token: string): {
  sub?: string;
  name?: string;
  email?: string;
  preferred_username?: string;
  given_name?: string;
  family_name?: string;
  iat?: number;
  exp?: number;
} | null {
  try {
    const decoded: {
      sub?: string;
      name?: string;
      email?: string;
      preferred_username?: string;
      given_name?: string;
      family_name?: string;
      iat?: number;
      exp?: number;
    } = jwtDecode(token);
    return {
      sub: decoded.sub,
      name: decoded.name,
      email: decoded.email,
      preferred_username: decoded.preferred_username,
      given_name: decoded.given_name,
      family_name: decoded.family_name,
      iat: decoded.iat,
      exp: decoded.exp,
    };
  } catch {
    return null;
  }
}
