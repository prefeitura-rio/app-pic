import NextAuth from "next-auth";

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [
    {
      id: "authentik",
      name: "Authentik",
      type: "oidc",
      issuer: process.env.NEXT_PUBLIC_AUTHENTIK_ISSUER,
      clientId: process.env.NEXT_PUBLIC_AUTHENTIK_ID,
      clientSecret: process.env.AUTHENTIK_SECRET,
      wellKnown: `${process.env.NEXT_PUBLIC_AUTHENTIK_ISSUER}.well-known/openid-configuration`,
      authorization: {
        params: {
          scope: "openid profile email",
        },
      },
    },
  ],
  callbacks: {
    async jwt({ token, account, profile }) {
      // Initial sign in
      if (account) {
        token.accessToken = account.access_token;
        token.idToken = account.id_token;
        token.refreshToken = account.refresh_token;
        token.expiresAt = account.expires_at;
      }

      if (profile) {
        token.profile = profile;
      }

      return token;
    },
    async session({ session, token }) {
      // Send properties to the client
      session.accessToken = token.accessToken as string;
      session.idToken = token.idToken as string;
      session.user = {
        ...session.user,
        ...(token.profile || {}),
      };

      return session;
    },
    authorized({ auth, request: { nextUrl } }) {
      const isLoggedIn = !!auth?.user;
      const isOnLogin = nextUrl.pathname === "/login";

      if (isOnLogin) {
        if (isLoggedIn) return Response.redirect(new URL("/", nextUrl));
        return true;
      }

      return isLoggedIn;
    },
  },
  pages: {
    signIn: "/login",
  },
});
