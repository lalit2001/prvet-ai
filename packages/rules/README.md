# `crv-rules`

Bundled Semgrep rulepacks + JSON schema for user-authored custom rules.
Enable/disable and edit rules from the admin UI at `/admin/rules` — never from the CLI.

## Layout

```
packages/rules/
  semgrep/
    python/     # bundled Python rules
    javascript/ # ...
    typescript/
    java/
    go/
  custom-rule.schema.json   # schema for the UI rule editor and API POST payloads
```
