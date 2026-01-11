# CodeExplorer Client

Next.js dashboard for visualizing repository analysis results from the CodeExplorer backend.

## Features

- **Repository Input**: Submit GitHub repository URLs for analysis
- **Overview Dashboard**: View key statistics including total files, languages, entry points, and key files
- **File Structure**: Interactive file tree visualization with folders and files
- **Language Breakdown**: Visual charts showing code distribution across programming languages
- **Dependencies**: Display of project dependencies from various package managers
- **Key Files & Entry Points**: Identification of important files and application entry points

## Tech Stack

- **Next.js 15** - React framework with App Router
- **TypeScript** - Type-safe development
- **Tailwind CSS** - Utility-first styling
- **Axios** - HTTP client for API communication

## Getting Started

### Prerequisites

- Node.js 18+ installed
- Backend API running (see `../server/README.md`)

### Installation

1. Install dependencies:
```bash
npm install
```

2. Create environment file:
```bash
cp .env.example .env.local
```

3. Update `.env.local` with your API URL:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Development

Run the development server:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### Build

Create a production build:

```bash
npm run build
npm start
```

## Project Structure

```
client/
├── app/
│   ├── globals.css          # Global styles
│   ├── layout.tsx            # Root layout
│   └── page.tsx              # Home page
├── components/
│   ├── AnalysisResults.tsx   # Main results container
│   ├── RepositoryInput.tsx   # URL input form
│   ├── OverviewSection.tsx   # Overview statistics
│   ├── FileTreeSection.tsx   # File tree viewer
│   ├── LanguagesSection.tsx  # Language breakdown
│   ├── DependenciesSection.tsx # Dependencies display
│   └── KeyFilesSection.tsx   # Key files & entry points
├── public/                   # Static assets
├── .env.local                # Environment variables (not in git)
└── package.json              # Dependencies
```

## Usage

1. **Start the Backend**: Ensure the FastAPI backend is running on `http://localhost:8000`

2. **Enter Repository URL**: Input a public GitHub repository URL (e.g., `https://github.com/facebook/react`)

3. **Analyze**: Click "Analyze Repository" to start the analysis

4. **View Results**: Browse through the different tabs:
   - **Overview**: Key statistics and README preview
   - **File Structure**: Interactive file tree
   - **Languages**: Code distribution by language
   - **Dependencies**: Project dependencies
   - **Key Files**: Important files and entry points

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API URL | `http://localhost:8000` |

## Development Notes

- All components use TypeScript for type safety
- Tailwind CSS is configured with dark mode support
- API calls are made using Axios with proper error handling
- Components are client-side rendered (`'use client'`) for interactivity

## Troubleshooting

**API Connection Error**
- Ensure the backend is running on the correct port
- Check that `NEXT_PUBLIC_API_URL` is set correctly
- Verify CORS is enabled on the backend

**Build Errors**
- Clear `.next` folder: `rm -rf .next`
- Reinstall dependencies: `rm -rf node_modules && npm install`

## License

Part of the CodeExplorer project - see main repository for license details.
