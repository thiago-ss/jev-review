# Install Jev as a GitHub App

The app uses predefined repository permissions:

| Permission | Access | Purpose |
| --- | --- | --- |
| Contents | Read | Read trusted base-branch ownership files |
| Checks | Read | Verify CI identity, freshness and outcome |
| Pull requests | Write | Read PR diffs, publish reviews and request reviewers |
| Metadata | Read (implicit) | Repository identity |

It has no repository contents-write or administration permission. Jev does not push code or merge PRs. The private app is operated by its owner; this is not a hosted marketplace service.

## Deployment shape

Keep the code and secrets in `thiago-ss/jev-review` (the controller). Install the app on the selected target repository. The controller's trusted default-branch workflow polls the target hourly and supports manual dispatch. Each job mints a target-scoped installation token. Dry-run tokens have read-only permissions; comment and approval jobs add pull-request write. Webhooks are disabled, so no public webhook server is needed.

Registration, installation and activation are separate steps. GitHub account authorization is required to register/install the app. Installing it does not automatically activate the workflow.

## Register

For the selected pilot, use `thiago-ss/jev-review` and fallback reviewer `thiago-ss`.

```sh
python3 scripts/register_github_app.py --no-browser
```

Open the printed local URL and follow its browser page. It presents the permission manifest and sends it to GitHub. GitHub returns to localhost; the helper exchanges the temporary code and saves credentials under ignored `.local/github-app/` with owner-only permissions. It prints only public app metadata and the installation link. Keep the helper running until the callback completes.

Select **Only select repositories** on GitHub's installation page and choose the target. For an organization-owned private app, register under that organization; a private personal app is not a general installation service for other owners.

## Configure and start

Use the setup helper to prepare `config/production.json` from the actual registered app identity and selected target. Supply a trusted fallback reviewer and, when known, required check names and their GitHub App IDs. Omitted checks or calibration do not authorize approval.

```sh
python3 scripts/configure_github_app.py \
  --credentials .local/github-app/credentials.json \
  --repo thiago-ss/jev-review --reviewer thiago-ss \
  --check "test (3.9):15368" --check "test (3.12):15368"
```

After setting `TYPESAFE_API_KEY` in your environment, repeat with `--configure-actions` to upload the app key and Jev key into the controller's Actions secrets. Secret values go over stdin to `gh`, never command-line arguments. Setup leaves `JEV_ENABLED=false` and `JEV_EXECUTE=false` even when called again, so subsequent scheduled jobs remain disabled while configuration is staged. For an existing deployment, wait for or cancel active runs before reconfiguration; changing variables does not revoke an already issued token.

Review and commit the generated config on the trusted default branch before enabling the workflow. Then set `JEV_ENABLED=true`, set `JEV_COMMENTS=false` and leave `JEV_EXECUTE=false`, then dispatch `jev-review.yml`.

```sh
gh variable set JEV_COMMENTS --repo thiago-ss/jev-review --body false
gh variable set JEV_ENABLED --repo thiago-ss/jev-review --body true
gh workflow run jev-review.yml --repo thiago-ss/jev-review --ref main
```

Inspect the JSON output in Actions. No PR mutations happen in this mode.

Once enabled, the workflow defaults to evidence comments when `JEV_COMMENTS` is unset or true. Set it to true after a read-only trial to publish risk/checklist/CI tables, confidence bars, exact commit evidence and an Actions run link. This `--comment-only` path never approves or requests reviewers. Explicit `JEV_EXECUTE=true` enables policy-gated approvals and trusted reviewer requests. Auto-approval additionally requires representative held-out calibration and every policy gate. App installation does not waive the [production DoD](acceptance.md).

## Security and recovery

Protect the controller's code, workflow, config and secrets: its App private key can authorize the app's installations. Scope tokens to one target and keep job duration below the token lifetime. Never execute a target PR checkout with these credentials. Disable `JEV_ENABLED` to stop runs; revoke the installation or rotate the app key if compromised. Protect target branches against stale approvals.

See [GitHub's manifest documentation](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest), the [official token Action](https://github.com/actions/create-github-app-token), and [local verification evidence](evidence/github-app.md).
