# Frozen PDSA Plan

## SMART Objective

Create a minimal viable web application skeleton that serves an Arabic RTL interface, loads synthetic institution data from data/institutions.json, and displays it in a list, ensuring the application runs locally without errors.

## Acceptance Criteria

- A local development server can be started via a documented command (e.g., npm start or python -m http.server).
- The main page loads in a browser with `dir="rtl"` and `lang="ar"` attributes set.
- The UI displays the list of institutions from `data/institutions.json`.
- The interface uses Arabic terminology for labels (e.g., 'المؤسسات' instead of 'Institutions').
- No critical JavaScript errors occur in the browser console upon loading.
- The code is committed to the repository with a clear entry point.

## Approved Plan

```json
{
  "allowed_fallbacks": [
    "If the execution environment lacks Node.js, switch to a pure Python Flask implementation (`app.py`, `requirements.txt`) and replace `npm start` with `python -m flask run`. All other steps (HTML, CSS, JS, tests) remain the same, with Jest tests replaced by `pytest` + `playwright` equivalents.",
    "If fetching the JSON file fails due to static serving issues, embed the JSON data directly in `app.js` as a constant fallback."
  ],
  "expected_evidence": [
    "Commit SHA that includes all new files.",
    "CI pipeline logs showing `npm install`, server start, successful Jest test run, and lint pass.",
    "Generated test report JSON confirming e2e validation of RTL attributes, Arabic label, and correct number of list items.",
    "ESLint report file with zero issues.",
    "Updated README excerpt with exact run commands and expected URL."
  ],
  "intended_files": [
    "package.json",
    "jest.config.js",
    "server.js",
    "public/index.html",
    "public/app.js",
    "public/style.css",
    "README.md (updated)",
    "tests/e2e.test.js",
    "tests/fetchData.test.js",
    ".eslintrc.json",
    ".gitignore"
  ],
  "objective_alignment": "Creates a minimal viable Arabic RTL web application skeleton that loads and displays synthetic institution data, directly satisfying the SMART objective and the first operability criteria of the Definition of Done.",
  "risks": [
    "Node.js version incompatibility – mitigated by specifying an LTS version in `engines` field of package.json.",
    "Port leakage in CI – mitigated by using the `get-port` library to allocate a free port and ensuring the server process is terminated after tests.",
    "Puppeteer binary size – mitigated by using the `puppeteer-core` package with a pre‑installed Chrome binary in the CI environment.",
    "Accidental inclusion of large files – mitigated by the explicit `.gitignore`."
  ],
  "steps": [
    "1. Choose a lightweight stack: Node.js with Express for the server and plain HTML/CSS/JS for the client. All dependencies are declared in package.json and require no external secrets.",
    "2. Add a `package.json` that defines scripts: `npm install`, `npm start` (runs `node server.js`), `npm test` (runs Jest), and `npm run lint` (runs ESLint). Include Jest and Puppeteer as devDependencies.",
    "3. Create `jest.config.js` to configure the test environment for Node and to allow Puppeteer tests.",
    "4. Implement `server.js` to serve static files from the `public/` directory and expose the `data/` folder as a static route (`/data`). The server listens on a port provided by the `PORT` environment variable or defaults to 3000.",
    "5. Add a `.gitignore` file that excludes `node_modules/`, `coverage/`, and any generated logs or OS files.",
    "6. Create `public/index.html` with `<html lang=\"ar\" dir=\"rtl\">` and a placeholder `<ul id=\"institution-list\"></ul>` preceded by an Arabic heading `<h1>المؤسسات</h1>`.",
    "7. Add `public/style.css` with explicit RTL styling (e.g., `body { direction: rtl; text-align: right; font-family: sans-serif; margin: 0; padding: 1rem; }`).",
    "8. Add `public/app.js` that fetches `/data/institutions.json`, parses the JSON, and populates the `<ul id=\"institution-list\">` with `<li>` elements containing the institution names.",
    "9. Update `README.md` with a clear “Running the Application” section that documents the commands `npm install && npm start` and the URL `http://localhost:3000`.",
    "10. Write an end‑to‑end test `tests/e2e.test.js` using Puppeteer that:",
    "    - Starts the server on a random free port,",
    "    - Navigates to `http://localhost:<port>` in a headless Chromium instance,",
    "    - Verifies that the `<html>` element has `lang=\"ar\"` and `dir=\"rtl\"`,",
    "    - Checks that the heading text is exactly `المؤسسات`,",
    "    - Waits for the list items to be rendered and asserts that the number of `<li>` elements matches the length of the JSON array,",
    "    - Confirms that no console errors of type `error` appear during page load.",
    "11. Add a unit test `tests/fetchData.test.js` that mocks the `fetch` call and verifies that `app.js` correctly updates the DOM when given a sample JSON payload.",
    "12. Add an ESLint configuration `.eslintrc.json` that enforces no `no-console` errors and uses the recommended ruleset.",
    "13. Commit all new files with descriptive commit messages, ensuring the commit SHA is recorded for evidence."
  ],
  "verification": [
    "Run `npm install && npm start`; the command must exit with status 0 and output a listening port message.",
    "Execute `npm test`; all Jest tests (unit and e2e) must pass with a 100% success rate.",
    "Run `npm run lint`; ESLint must report zero errors or warnings.",
    "CI workflow logs must show successful installation, server start, test execution, and linting.",
    "The e2e test provides a JSON report (`npm test -- --outputFile=report.json`) confirming that the RTL attributes, Arabic heading, and dynamic list rendering succeeded.",
    "The commit SHA referenced in the evidence must contain all intended files."
  ]
}
```
