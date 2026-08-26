# Frozen PDSA Plan

## SMART Objective

Establish a minimal runnable Arabic RTL web application skeleton with synthetic data persistence to satisfy DoD-A (Operability) and DoD-B (Language/UX) baseline requirements.

## Acceptance Criteria

- A build/run command exists and executes without errors.
- The application serves a web page in Arabic with RTL direction.
- The application includes a basic data model for 'Institutions' (as per Product Goal 1) and persists synthetic data across page reloads (e.g., using local storage or a simple file-based DB).
- Automated tests verify the build process and the presence of RTL/Arabic attributes.
- No secrets or real data are committed.

## Approved Plan

```json
{
  "allowed_fallbacks": [
    "If file‑based persistence fails in development mode, the server logs a warning and falls back to in‑memory storage for the current process."
  ],
  "expected_evidence": [
    "SHA‑256 hash of the frozen plan recorded in .autonomy/state.json.",
    "CI build log showing `npm ci` and `npm test` completing without errors.",
    "JSON test report (e.g., test-report.json) indicating all assertions passed.",
    "Programmatic evidence of RTL: the response body from GET / contains `<html lang=\"ar\" dir=\"rtl\">`.",
    "Evidence of persistence: test logs showing POSTed institution ID appears in subsequent GET response.",
    "README excerpt with exact commands and description of development vs test persistence modes."
  ],
  "intended_files": [
    "package.json",
    "server.js",
    "schema/institution.schema.json",
    "data/institutions.seed.json",
    "public/index.html",
    "public/app.js",
    "tests/app.test.js",
    "README.md",
    ".gitignore"
  ],
  "objective_alignment": "Create a minimal runnable Arabic RTL web application skeleton with synthetic data persistence, directly satisfying DoD-A (Operability) and DoD-B (Language/UX) as required by the SMART objective and the product goal.",
  "risks": [
    "Node runtime unavailable – mitigated by documenting the required Node version and failing fast if not present.",
    "File‑system write permission issues in CI – mitigated by using in‑memory storage for test mode and only writing to data/ in development mode.",
    "Potential zombie server processes – mitigated by explicit teardown hooks that kill the child process after each test suite.",
    "Schema mismatch – mitigated by validating incoming POST bodies against the JSON schema before acceptance."
  ],
  "steps": [
    "1. Choose a lightweight web stack: Node.js with Express and plain HTML/CSS/JS (no external secrets).",
    "2. Add a package.json with scripts: \"dev\":\"node server.js\", \"test\":\"node test/runTests.js\" and a start script that launches the server in development mode.",
    "3. Implement server.js that:",
    "   - Serves static files from /public.",
    "   - Provides a JSON API at /api/institutions.",
    "   - Detects NODE_ENV:",
    "       * In \"development\" mode uses a file‑based store at data/institutions.json (initializes the file with a predefined synthetic array if missing).",
    "       * In \"test\" mode uses an in‑memory array that is reset for each test run.",
    "   - Exposes GET /api/institutions and POST /api/institutions with validation against a strict JSON schema.",
    "4. Define the synthetic Institution schema (JSON Schema) with required fields: id (uuid string), name (Arabic string), address (Arabic string), type (enum[\"public\",\"private\"]). Store schema in schema/institution.schema.json.",
    "5. Create data/institutions.seed.json containing the explicit seed array:",
    "   [",
    "     {\"id\":\"1\",\"name\":\"المؤسسة العامة الأولى\",\"address\":\"شارع الملك عبدالعزيز، الرياض\",\"type\":\"public\"},",
    "     {\"id\":\"2\",\"name\":\"المؤسسة الخاصة الثانية\",\"address\":\"طريق الملك فهد، جدة\",\"type\":\"private\"}",
    "   ]",
    "   server.js copies this file to data/institutions.json on first run in development mode.",
    "6. Create public/index.html with <html lang=\"ar\" dir=\"rtl\"> and minimal Arabic UI text (e.g., \"قائمة المؤسسات\"). Include a placeholder div for the institution list.",
    "7. Add public/app.js that fetches the institution list, renders it, and provides a simple form to add a new institution via fetch POST to the API.",
    "8. Write README.md section documenting:",
    "   - Prerequisites (Node >=14).",
    "   - Exact build/run command: `npm ci && npm run dev`.",
    "   - How persistence works in each mode.",
    "   - How to run the automated test suite: `npm test`.",
    "9. Implement automated tests in tests/app.test.js using Mocha (or node's built‑in assert) with SuperTest:",
    "   - Test that the server starts in test mode and GET / returns HTML containing `<html lang=\"ar\" dir=\"rtl\">`.",
    "   - Positive test: POST a valid institution (Arabic fields) and then GET /api/institutions to verify the new record appears.",
    "   - Negative test: POST an invalid institution (e.g., missing \"name\" or invalid \"type\") and assert the response status is 400.",
    "   - Test that the seed data is loaded in development mode by spawning the server with NODE_ENV=\"development\" and verifying GET /api/institutions returns the two Arabic records defined in the seed file.",
    "   - Use async/await for all async operations and ensure proper teardown by killing the server process after each test suite.",
    "10. Add .gitignore entries for node_modules, data/, and any temporary test artifacts (e.g., .nyc_output, coverage).",
    "11. Update the existing CI workflow to run `npm ci && npm test` on each push (no conditional fallbacks)."
  ],
  "verification": [
    "Running `npm ci && npm run dev` starts the server and exits with code 0.",
    "Automated test suite (`npm test`) completes with exit code 0 and all assertions pass.",
    "Test 1 asserts the HTTP GET / response contains `<html lang=\"ar\" dir=\"rtl\">`.",
    "Test 2 posts a valid institution (Arabic fields) and then GETs the list to verify the record appears, proving in‑memory persistence in test mode.",
    "Test 3 posts invalid data and asserts a 400 response, confirming schema validation.",
    "Test 4 starts the server in development mode, reads data/institutions.json (seeded from institutions.seed.json), and verifies the two Arabic records are present.",
    "CI logs show successful npm install, server start in test mode, and all test assertions passed.",
    "README contains reproducible commands that a fresh clone can execute without manual steps."
  ]
}
```
