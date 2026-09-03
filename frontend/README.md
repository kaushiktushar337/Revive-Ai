# ReviveAI — React + JavaScript + Tailwind

This frontend is intentionally **JavaScript/JSX only**. There are no TypeScript (`.ts`/`.tsx`) files.

## Stack
- React 18
- JavaScript + JSX
- Tailwind CSS 3
- Vite 5

## Windows setup
Use Node.js 20 or 22. From this `frontend` directory:

```powershell
npm install
npm run dev
```

Open `http://127.0.0.1:5500`.

The app expects the API at `http://127.0.0.1:8000/api`. To point at a hosted API, edit the `window.REVIVE_API` line in `index.html`.

## Production build

```powershell
npm run build
npm run preview
```

The build output is written to `dist/`.

## No activation required
The frontend does not use Python virtual-environment activation. It only needs Node/npm.
