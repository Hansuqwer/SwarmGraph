# Secret Scanning

SwarmGraph uses gitleaks with Flutter-aware rules for local development.

```bash
pre-commit install
pre-commit run --all-files
gitleaks detect --no-git --source . --config .gitleaks.toml --redact
```

The config extends the upstream default rules and adds checks for common
Flutter/mobile artifacts:

- `firebase_options.dart` embedded Firebase API keys
- Android `key.properties`
- mobile signing/private-key artifacts such as `.p8`, `.p12`, `.jks`, and `.keystore`
- Firebase/Google app config files such as `google-services.json` and `GoogleService-Info.plist`
- Fastlane app/env files

Do not commit real `.env` files, vault files, mobile signing keys, or provider
API keys. Keep `.env.example` values empty or fake.

Allowlist scope is intentionally narrow: `.env.example`, archived/generated
patches under `docs/history/`, `docs/patches/`, `site/patches/`, local
GitNexus metadata, and named fake fixtures under
`tests/fixtures/secret_shapes/`. Do not add blanket `docs/` or `tests/` skips.
