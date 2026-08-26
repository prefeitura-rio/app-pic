'use client';

import { useEffect, ReactNode } from 'react';

interface LoginFormWithFallbackProps {
  children: ReactNode;
  authUrl: string;
}

/**
 * Wraps the login form with CSP error handling
 * If form submission fails due to CSP violation, silently redirects to authUrl
 * 
 * This is a failsafe for intermittent CSP issues on first access after long periods
 */
export function LoginFormWithFallback({ children, authUrl }: LoginFormWithFallbackProps) {
  useEffect(() => {
    // Handle CSP violations for form-action directive
    const handleSecurityPolicyViolation = (event: SecurityPolicyViolationEvent) => {
      // Only handle form-action CSP violations
      if (event.violatedDirective === 'form-action') {
        // Silently redirect to auth URL
        window.location.href = authUrl;
      }
    };

    // Listen for CSP violations on page
    document.addEventListener('securitypolicyviolation', handleSecurityPolicyViolation, true);

    // Cleanup listener on unmount
    return () => {
      document.removeEventListener('securitypolicyviolation', handleSecurityPolicyViolation, true);
    };
  }, [authUrl]);

  return <>{children}</>;
}
