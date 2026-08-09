# Read-only public launch

## Browser environment

The public Vite application may receive only this environment variable:

```text
VITE_CONVEX_URL=https://your-production-deployment.convex.cloud
```

Do not add market-data, LLM, authentication, or provider credentials with a
`VITE_` prefix. Provider secrets belong in the matching Convex deployment
environment, not Vercel.

## Vercel preview

1. Import the GitHub repository into Vercel.
2. Keep the detected Vite settings from `vercel.json` (`npm run build`, output
   directory `dist`).
3. Add `VITE_CONVEX_URL` only for the Preview environment, using a non-public
   Convex preview/development deployment that contains safe test data.
4. Create a preview deployment and confirm the site can read intended data but
   cannot call mutations, refreshes, or AI generation.

## Production promotion

1. Deploy the Convex production schema/functions and import the approved data
   snapshot.
2. Add all provider keys to Convex production settings, never to Vercel.
3. Set Vercel Production `VITE_CONVEX_URL` to the production Convex URL.
4. Re-run the read-only, secret-scan, and anonymous-browsing checks.
5. Promote the verified Vercel preview.
