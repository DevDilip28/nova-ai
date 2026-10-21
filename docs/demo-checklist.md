# NOVA AI demo and submission checklist

This checklist is intentionally unchecked. It records work to perform; it does not claim any result has passed.

## Before recording

- [ ] Select Alexa+ as the primary track if that remains the intended entry; select any mini challenge only if its separate requirements are met.
- [ ] Review the current [Build, Ship, Shape official rules](https://amazonappdev2026.devpost.com/rules), deadlines, eligibility, selected track, and required form fields.
- [ ] Configure `.env` locally. Do not show its contents, credentials, terminal history containing secrets, or real personal data in the recording.
- [ ] Install from the lockfiles and run `npm ci` and `npm run build`.
- [ ] Run `npm audit`, review each advisory and fix option, and resolve or document remaining exposure. Avoid `npm audit fix --force` without reviewing breaking changes.
- [ ] Install backend requirements and start the API and MCP server using the scripts in the root README.
- [ ] Confirm `/api/health` reports the intended provider configuration without exposing credentials.
- [ ] Exercise one AI chat request, a follow-up using prior context, one current web research request, and verify source links open.
- [ ] Exercise microphone push-to-talk if the selected browser supports it; show typing as the fallback. Do not describe a wake word.
- [ ] Create a small project, inspect its generated files and workspace path, and verify dependency setup waits for explicit approval. Do not run unreviewed generated code.
- [ ] Connect an MCP client to `http://127.0.0.1:8001/mcp`; list tools, call a safe read-only tool, and verify the negotiated protocol version is at least `2025-11-25` and the transport is Streamable HTTP.
- [ ] Verify modifying MCP tools stay within a registered project and that install/build requests require approval.
- [ ] If judges need remote access, choose and test a secure, temporary tunnel or hosted endpoint. Do not expose the unauthenticated loopback demo directly to the public internet.

## Video plan (official rules currently say under 3 minutes, public, English, YouTube or Vimeo)

- [ ] Start with the user problem and what NOVA does.
- [ ] Show the web UI and the AI chat workflow.
- [ ] Show one real research answer with its retrieved source links.
- [ ] Show project generation, inspect the created files, and show the approval boundary before dependency installation.
- [ ] Show the MCP server in a compatible MCP client and identify its negotiated protocol version and Streamable HTTP endpoint.
- [ ] Describe voice accurately as button-activated push-to-talk; no Alexa+ integration or wake word is implemented.
- [ ] Avoid third-party copyrighted music/footage unless permission is available; keep the video under three minutes.
- [ ] Publish the video publicly on YouTube or Vimeo and copy its URL into the submission.

## Repository and form

- [ ] Choose public or private GitHub visibility. For public, ensure the MIT license is visible. For private, share with `testing@devpost.com` and invite the Amazon reviewer accounts required by the current rules.
- [ ] Confirm `.env`, credentials, databases, generated user projects, virtual environments, dependencies, and build artifacts are ignored and absent from the staged repository.
- [ ] Add the GitHub repository URL and a concise feature description to the submission.
- [ ] Provide product feedback for every tool, API, and SDK used: purpose, what worked, what needs improvement, onboarding experience, and whether you would use it again. Identify AWS services accurately.
- [ ] Since NOVA predates the hackathon, describe only the actual work completed during the submission window; do not imply the whole project was created during it.
- [ ] Include screenshots if the form or gallery supports them; keep them consistent with the live demo and redact credentials/personal data.
- [ ] Review all claims against what was actually demonstrated. Do not claim official Alexa+ integration, wake-word support, production readiness, or successful runtime checks that were not performed.

