# UMOA Banking Intelligence — Next.js Frontend

## Stack

- **Framework**: Next.js 15 (App Router)
- **Language**: TypeScript (strict mode)
- **Styling**: Tailwind CSS
- **i18n**: next-intl (fr/en)
- **API**: custom typed fetch client

## Development

```bash
npm install
npm run dev
```

Frontend runs at http://localhost:3000
Redirects automatically to /fr (default locale)

## i18n

- French: `/fr/` (default)
- English: `/en/`
- Messages: `src/messages/fr.json` and `src/messages/en.json`
- Add new messages to both files when adding UI strings

## API

The frontend connects to the FastAPI backend (default: http://localhost:8000).
Configure via `NEXT_PUBLIC_API_URL` environment variable.

## Structure

```
src/
├── app/
│   ├── [locale]/     # Locale-aware pages
│   │   ├── layout.tsx
│   │   └── page.tsx
│   └── globals.css
├── i18n/
│   ├── request.ts    # Server-side locale config
│   ├── routing.ts    # Locale routing config
│   └── navigation.ts # Locale-aware navigation
├── messages/
│   ├── fr.json
│   └── en.json
├── lib/
│   └── api.ts        # FastAPI client
└── types/
    └── index.ts      # Shared TypeScript types
```

## Adding a new page

1. Create `src/app/[locale]/my-page/page.tsx`
2. Add translations in `src/messages/fr.json` and `src/messages/en.json`
3. Use `useTranslations("namespace")` in the component

## Data integrity

All data displayed must come from the API.
Never hardcode financial data in the frontend.
Use explicit empty states when data is not available.
