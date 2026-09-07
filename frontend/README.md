# Face Trace frontend

React/Vite interface for searching public images, choosing a social-media
match, and registering or verifying its evidence fingerprint on the local
Hardhat blockchain.

## Development

```bash
npm install
npm run dev
```

The app calls `http://127.0.0.1:8011` by default. To use another API URL,
create `.env.local` with:

```bash
VITE_API_URL=http://127.0.0.1:8011
```

Run `npm run build` to create a production build.
