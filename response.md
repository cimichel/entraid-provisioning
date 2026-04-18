# DevOps Engineer Take-Home Task
## Bulk Provisioning of Microsoft Entra ID Security Groups

**Submitted by:** Cintia Michel, April 2026

---

## 1. Approach and Steps

The solution uses Python to automate group creation via the Microsoft Graph API, following four phases:

1. **Validate** the CSV before touching the tenant data
2. **Dry run** to confirm what would be created
3. **Provision** groups, owners, and members
4. **Verify** outcomes via audit log

**Assumptions:**
- Service principal has `Group.ReadWrite.All` and `User.Read.All`
- All users referenced in the CSV exist in the Entra tenant
- This runs under an approved change request

---

## 2. Tools and Technologies

| Tool | Why |
|---|---|
| Python 3.11+ | Strong CSV handling, readable, easy to hand over |
| MSAL | Official Microsoft library for OAuth2 client credentials |
| Microsoft Graph API | Used for Entra group management |
| `requests` | Lightweight HTTP client, no heavy SDK needed |

Terraform and Bicep were ruled out — this is a one-off task, not ongoing infrastructure.

---

## 3. Implementation

Delivered artefacts:
- `create_entra_groups.py` — main script
- `README.md` — runbook
- `groups.csv` — input data
- `provisioning.log` and `audit_log.json` — dry run evidence

The script separates auth, validation, API calls, and logging into distinct sections. Credentials are always loaded from environment variables, never hardcoded.

---

## 4. Validation and Testing

**Pre-run:** every row is validated before any API call — required fields, email format, alphanumeric `mail_nickname`, valid `assignable_to_role`, and intra-CSV duplicate detection.

**Post-run:** `audit_log.json` shows per-group outcomes. Spot-check 5–10 groups in the Entra portal and confirm via Graph API read-back query.

---

## 5. Error Handling and Edge Cases

| Scenario | Handling |
|---|---|
| Duplicate in CSV | Caught at validation; row skipped |
| Group already exists in Entra | Idempotency check; marked `skipped_already_exists` |
| Invalid owner/member UPN | Assignment skipped; group still created |
| Partial failure | Logged; script continues; safe to rerun |
| Auth failure | Fatal exit with error detail |

The script is fully idempotent — reruns skip existing groups and only attempt failed ones.

---

## 6. Operational and Safety Considerations

- **Logging:** `provisioning.log` (rotating, max 1MB, 3 backups) + `audit_log.json` (structured results) generated every run
- **Auditability:** script outputs bridge the CSV request to Entra's own audit log; both attached to the change record
- **Rollback:** no automatic deletion — filter `audit_log.json` for `status=success` and delete manually under a separate change request
- **Least privilege:** `Group.ReadWrite.All` + `User.Read.All` only; no Global Admin required
- **Change control:** run under an approved change request; `isAssignableToRole=true` groups flagged separately due to elevated IAM implications

---

## 7. Documentation

A `README.md` is included covering setup, environment variables, usage, expected outputs and rollback.

---

## References

- [Find your Azure Tenant ID](https://learn.microsoft.com/en-us/azure/azure-portal/get-subscription-tenant-id)
- [Microsoft Graph API - Create Group](https://learn.microsoft.com/en-us/graph/api/group-post-groups)
- [MSAL Python](https://learn.microsoft.com/en-us/entra/msal/python/)
