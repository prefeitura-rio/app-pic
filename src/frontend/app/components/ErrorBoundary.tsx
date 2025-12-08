"use client";

import React, { Component, ReactNode } from "react";
import { AlertTriangle, RefreshCw, Home } from "lucide-react";
import { Button } from "@/app/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/app/components/ui/card";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: React.ErrorInfo | null;
}

/**
 * Global Error Boundary Component
 *
 * Captura erros não tratados em qualquer componente filho e exibe uma UI amigável.
 * Em desenvolvimento, mostra detalhes completos do erro para debug.
 * Em produção, mostra mensagem genérica e opções de recuperação.
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      error,
      errorInfo: null,
    };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // Log error to console in development
    if (process.env.NODE_ENV === "development") {
      console.error("Error Boundary caught an error:", error);
      console.error("Error Info:", errorInfo);
    }

    this.setState({
      error,
      errorInfo,
    });
  }

  handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
  };

  handleGoHome = () => {
    window.location.href = "/";
  };

  render() {
    if (this.state.hasError) {
      // Custom fallback if provided
      if (this.props.fallback) {
        return this.props.fallback;
      }

      const isDev = process.env.NODE_ENV === "development";

      return (
        <div className="min-h-screen flex items-center justify-center p-4 bg-background">
          <Card className="w-full max-w-2xl border-destructive/50">
            <CardHeader className="text-center">
              <div className="mx-auto w-16 h-16 bg-destructive/10 rounded-full flex items-center justify-center mb-4">
                <AlertTriangle className="h-8 w-8 text-destructive" />
              </div>
              <CardTitle className="text-2xl">Oops! Algo deu errado</CardTitle>
              <CardDescription>
                {isDev
                  ? "Um erro ocorreu durante a renderização. Veja os detalhes abaixo."
                  : "Pedimos desculpas pelo inconveniente. Nossa equipe foi notificada."}
              </CardDescription>
            </CardHeader>

            <CardContent className="space-y-4">
              {/* Error Details (Development Only) */}
              {isDev && this.state.error && (
                <div className="space-y-3">
                  <div className="bg-destructive/5 border border-destructive/20 rounded-lg p-4">
                    <h3 className="font-semibold text-sm text-destructive mb-2">
                      Error Message:
                    </h3>
                    <p className="text-sm font-mono text-foreground/80">
                      {this.state.error.message}
                    </p>
                  </div>

                  {this.state.error.stack && (
                    <div className="bg-muted rounded-lg p-4 max-h-64 overflow-auto">
                      <h3 className="font-semibold text-sm mb-2">Stack Trace:</h3>
                      <pre className="text-xs font-mono text-muted-foreground whitespace-pre-wrap">
                        {this.state.error.stack}
                      </pre>
                    </div>
                  )}

                  {this.state.errorInfo && (
                    <div className="bg-muted rounded-lg p-4 max-h-64 overflow-auto">
                      <h3 className="font-semibold text-sm mb-2">Component Stack:</h3>
                      <pre className="text-xs font-mono text-muted-foreground whitespace-pre-wrap">
                        {this.state.errorInfo.componentStack}
                      </pre>
                    </div>
                  )}
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex flex-col sm:flex-row gap-3 pt-4">
                <Button
                  onClick={this.handleReset}
                  className="flex-1 gap-2"
                  variant="default"
                >
                  <RefreshCw className="h-4 w-4" />
                  Tentar Novamente
                </Button>
                <Button
                  onClick={this.handleGoHome}
                  className="flex-1 gap-2"
                  variant="outline"
                >
                  <Home className="h-4 w-4" />
                  Voltar ao Início
                </Button>
              </div>

              {/* Support Message */}
              <p className="text-sm text-muted-foreground text-center pt-4 border-t">
                Se o problema persistir, entre em contato com o suporte técnico.
              </p>
            </CardContent>
          </Card>
        </div>
      );
    }

    return this.props.children;
  }
}
