# Tenant AI keys

D-11. Tokut is the system of record for tenant AI-key **refs** and inject **recipes**. Fort Knox keeps the secret. This page is the contract for DeepSeek on paseo-prims and for per-tenant OpenRouter spend walls.

Compatibility: based on `main` after D-09 / D-10 (PR #4). It does not wait on draft PR #5 (`cursor/keys-cli-resolve-ui-ad3e`, CLI `resolve` / `--check` and the keys-page backend+handle form). Metadata here is additive on `KeyStore.put`, `GET /api/keys`, and `tokut keys put`. PR #5 should keep forwarding `inject`, `openrouter_project`, `openrouter_tag`, and `spend_alias` if it rebuilds the POST body.

Live inventory observed 2026-09-05, handles only, not migrated by this change:

| Slot | Then | Vault |
| --- | --- | --- |
| `eidos/deepseek` | inline | DeepSeek SoT `knox:bc3fdbe01f704a72` |
| `reeves/deepseek` | inline | same DeepSeek SoT when that slot is wired; do not assume it is a copy |
| `reeves/openrouter` | inline | separate OpenRouter route, not the DeepSeek record |
| `reeves/nvidia` | inline | out of scope here |

## Ownership

| Piece | Owner |
| --- | --- |
| Slot refs, spend metadata, inject recipes, orchestration for other agents | Tokut |
| Secret custody | Fort Knox |
| Tenant list | kai (`kai tenants` / `GET /tenants/api`) |
| Runtime consumers | PrimsDrive and Paseo |
| One-time stamp when Knox is blocked | SafePaste, temporary, Daniel re-stamps, Tokut performs it |

Chat is not a key store. SafePaste is not a source of truth. `~/.config/tokut/keys.json` stores refs and recipes, mode `0600`, never the secret as SoT.

## Two mechanisms

DeepSeek and OpenRouter are different slots. Do not send DeepSeek through OpenRouter BYOK for dsh.

**DeepSeek is direct Knox.** Slot `(tenant, deepseek)`. Backend `knox`. Ref is a Knox record id. The known DeepSeek vault record is `knox:bc3fdbe01f704a72`. `resolve` answers whether the slot is usable and returns the Fort Knox recipe (`knox request` → `knox approve` → `knox invoke --env-var DEEPSEEK_API_KEY -- <child>`). Tokut does not unwrap and does not print the secret.

**OpenRouter is the spend wall.** Slot `(tenant, openrouter)`. One management key and one OpenRouter project per spend plane. Metadata on that slot:

- `openrouter_project` — project id (spend wall)
- `openrouter_tag` — tag Daniel uses to read spend
- `spend_alias` — another **kai** tenant whose OpenRouter project pays, when this tenant does not have its own

Intended OpenRouter projects, once Daniel creates them and the refs are recorded (not created here):

| Tenant | OpenRouter project |
| --- | --- |
| eidos | own management key / project |
| aic | own management key / project |
| reeves | own management key / project (historical inline slot) |
| prims (Prim Foundation) | no own project by default; `spend_alias` `eidos` |
| ridge | planned; no spend plane until one is named |

## Slot model

Identity stays `(tenant, provider)` from D-08 / D-09. Optional fields sit on the record:

```json
{
  "tenant": "eidos",
  "provider": "openrouter",
  "backend": "knox",
  "ref": "knox:<openrouter-management-handle>",
  "openrouter_project": "<eidos-project-id>",
  "openrouter_tag": "eidos",
  "inject": {
    "dsh_credentials": "~/.dsh/.credentials.yaml",
    "paseo_prims": "paseo-prims"
  }
}
```

`spend_alias` is omitted when the slot's own tenant is the spend plane. Setting it to the same tenant is rejected. It is valid only on an `openrouter` slot, and the target must already be a kai tenant. `openrouter_project` and `openrouter_tag` are rejected on `deepseek` so a Knox record is not mislabeled as an OpenRouter project.

List, `GET /api/keys`, and `tokut keys list` return these fields. They return a masked Knox handle, never the secret, and they drop secret-shaped metadata if a file was hand-edited. Do not put a key, grant, or stamp in those fields.

## Planned planes and D-08

kai is the tenant source of truth. ADR 0001 (`eidos`, `aic`, `arp`, `gmw`, `reeves`) is only the fallback when the kai door is down. That list does **not** grow a sixth store.

`prims` (Prim Foundation) and `ridge` are not in that fallback. Until `kai tenants` lists them they are **planned inject planes**, exposed on `GET /api/keys` as `planned_inject_planes` and rejected by `KeyStore.put`. Prim Foundation piggybacks Eidos spend only through an explicit `spend_alias` of `eidos` on a future `(prims, openrouter)` slot. That is not a second OpenRouter account and not a plaintext key file. ridge has no alias until Daniel names a spend plane. Do not invent one.

When kai lists `prims`, the planned row drops off the payload and a real slot is allowed, still without a secret in Tokut:

```json
{
  "tenant": "prims",
  "provider": "openrouter",
  "backend": "knox",
  "ref": "knox:<handle-for-the-eidos-spend-plane>",
  "openrouter_project": "<eidos-project-id>",
  "openrouter_tag": "prims",
  "spend_alias": "eidos"
}
```

A separate Prim Foundation OpenRouter project happens only if Daniel creates one. Default is the alias.

## Durable storage

| Store | Holds | Does not hold |
| --- | --- | --- |
| `~/.config/tokut/keys.json` | tenant, provider, backend, Knox ref, OpenRouter project/tag, `spend_alias`, inject recipe | secret as source of truth |
| Fort Knox | secret bytes for the record id | Tokut's tenant index |
| `~/.dsh/.credentials.yaml` | interim dsh runtime copy on the Paseo/homebrew cell | the system of record |
| Chat, tickets, git, SafePaste | nothing durable | — |

`inline` plaintext remains the migrate-only backend from D-10. New DeepSeek and OpenRouter slots should be `knox` refs. This change does not rewrite the live file and does not call Knox.

Hermes `.env` stays the reeves mirror for inline puts only. It is not the dsh inject path.

## Inject recipes

Recipes are data on the slot. Placeholders from `tokut.key_meta.INJECT_PLANE_PLACEHOLDERS`:

| Plane key | Placeholder | Meaning |
| --- | --- | --- |
| `dsh_credentials` | `~/.dsh/.credentials.yaml` | Interim Paseo/homebrew dsh file. Not flipped off by this change. |
| `paseo_prims` | `paseo-prims` | Cell that should receive DeepSeek, then later OpenRouter. |

Example on the DeepSeek slot that feeds that cell (ref is the known vault id; do not copy a secret in beside it):

```json
{
  "tenant": "eidos",
  "provider": "deepseek",
  "backend": "knox",
  "ref": "knox:bc3fdbe01f704a72",
  "env_var": "DEEPSEEK_API_KEY",
  "inject": {
    "dsh_credentials": "~/.dsh/.credentials.yaml",
    "paseo_prims": "paseo-prims"
  }
}
```

Which historical inline slot owns that Knox record is an inventory fact, not a guess this PR writes down. The paseo-prims cell is the Prim Foundation consumer; its spend plane is eidos. Attach this recipe to the slot that actually holds `knox:bc3fdbe01f704a72`. Leave `reeves/deepseek` alone unless that inventory shows the same record.

Tokut orchestrates the recipe (which slot, which ref, which path). Tokut does not materialize the yaml and does not implement unlock-broker. When Knox is warm the human proof is: `knox request` → `knox approve` → `knox invoke` into the child that needs `DEEPSEEK_API_KEY`, aimed at the paseo-prims cell. Lab UI `:3080` continues to use `dsh-web-knox`; that is a consumer, not the SoR.

`{}` clears `inject`. Omitting the field on a later put keeps the stored recipe.

## SafePaste temporary bootstrap

Use this only when Knox is blocked **and** Daniel re-stamps. It is not the steady state. PrimsDrive must not keep a paste habit. Tokut owns the procedure. Fort Knox still owns custody once invoke works again.

1. Confirm the slot in Tokut (tenant, provider, Knox ref, inject paths). `resolve` is `use_invoke` or `needs_unlock`, and invoke cannot finish.
2. Daniel re-stamps out of band. Do not put the stamp in chat, tickets, docs, or git.
3. Tokut writes it only to the plane path on the slot (`dsh_credentials` → `~/.dsh/.credentials.yaml`) with mode `0600`. Do not write it into `~/.config/tokut/keys.json`.
4. Shred the temporary stamp file and clear the clipboard after that move. The credentials file is an interim runtime copy, not the system of record.
5. The slot still records only the Knox ref, spend metadata, and the recipe.
6. When Knox is warm, inject with the Knox recipe and remove the interim material from the credentials file. Do not SafePaste again for that slot.

## What this change does not do

- Migrate live keys or call Knox from CI or from Tokut.
- Flip Paseo off `~/.dsh/.credentials.yaml`.
- Implement unlock-broker.
- Add `prims` or `ridge` to the ADR fallback list.
- Store a secret in git, chat, or the SoR.

## Next proof (human, after merge)

1. On the DeepSeek slot that should feed paseo-prims, `tokut keys put deepseek --tenant <tenant> --backend knox --ref knox:bc3fdbe01f704a72 --inject '{"dsh_credentials":"~/.dsh/.credentials.yaml","paseo_prims":"paseo-prims"}'`.
2. When Knox is warm, inject that record onto the paseo-prims cell with `knox invoke` (not OpenRouter BYOK, not a paste).
3. If Knox is blocked, run the SafePaste SOP above only with a fresh Daniel stamp, then delete the interim copy once invoke works.
4. Record OpenRouter management refs per eidos, aic, and reeves the same way, with `openrouter_project` / `openrouter_tag`. Add `(prims, openrouter)` with `spend_alias` `eidos` only after kai lists `prims`, unless Daniel has created a separate project.
