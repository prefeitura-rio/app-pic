'use client';

import { ReactNode, useEffect } from 'react';

interface LoginFormWithFallbackProps {
  children: ReactNode;
  authUrl: string;
}

/**
 * Wraps the login form with CSP error handling and direct fallback
 * If form submission is blocked by CSP, directly redirects to authUrl
 * 
 * This prevents users from getting stuck on CSP violations
 */
export function LoginFormWithFallback({ children, authUrl }: LoginFormWithFallbackProps) {
  useEffect(() => {
    // Setup CSP violation listener
    const handleSecurityPolicyViolation = (event: SecurityPolicyViolationEvent) => {
      // Check if this is a form-action violation
      if (event.violatedDirective && event.violatedDirective.includes('form-action')) {
        console.warn('CSP form-action blocked, redirecting to:', authUrl);
        // Silently redirect to auth URL
        window.location.href = authUrl;
      }
    };

    // Listen for any CSP violations
    document.addEventListener('securitypolicyviolation', handleSecurityPolicyViolation, true);

    return () => {
      document.removeEventListener('securitypolicyviolation', handleSecurityPolicyViolation, true);
    };
  }, [authUrl]);

  return <>{children}</>;
}
