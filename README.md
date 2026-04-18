# 🔐 Entra ID security group provisioner

Bulk creates 50 Microsoft Entra ID security groups CSV file via the Microsoft Graph API.

---

## 📋 Prerequisites

- Python 3.11+
- Azure App Registration with **application permissions** (admin consented):
  - `Group.ReadWrite.All`
  - `User.Read.All`

---

## ⚙️ Setup

**1. Create and activate a virtual environment (recommended):**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**2. Install dependencies:**

```bash
pip install -r requirements.txt
```

**3. Set environment variables (hardcoded for activity):**

```bash
export AZURE_TENANT_ID="your-tenant-id"
export AZURE_CLIENT_ID="your-client-id"
export AZURE_CLIENT_SECRET="your-client-secret"
```

---

## 🚀 Usage

**1. Dry run first (always):**

Set `DRY_RUN = True` in the script (default), then:

```bash
python create_entra_groups.py
```

**2. Live run:**

Set `DRY_RUN = False`, then run:

```bash
python create_entra_groups.py
```

---

## 📥 Input

CSV file must have the following columns:

| Column | Description |
|---|---|
| `group_name` | Display group name |
| `description` | Description of the group |
| `mail_nickname` | Alphanumeric only, unique in tenant |
| `group_type` | `Security` |
| `assignable_to_role` | `true` or `false` |
| `owner_upn` | Must already exist in the tenant |
| `members_upns` | Semicolon-separated, must already exist in tenant |

---

## 📤 Output

| File | Description |
|---|---|
| `provisioning.log` | Full results log |
| `audit_log.json` | Group results — status, group ID, owner/member outcomes |

---

## 🛡️ Error Handling

- ⚠️ Invalid rows are logged and skipped but they don't stop the script run
- ♻️ Groups that already exist in Entra ID are skipped 
- 🔁 Any partial failures are recorded in `audit_log.json`, safe to rerun

---

## 🔙 Rollback

Filter `audit_log.json` for `status=success` to get group IDs, then:

```bash
az ad group delete --group <group-id>
```

---

## 📚 References used in this project:

- [Find your Azure Tenant ID](https://learn.microsoft.com/en-us/azure/azure-portal/get-subscription-tenant-id)
- [Microsoft Graph API - Groups](https://learn.microsoft.com/en-us/graph/api/group-post-groups)
- [MSAL Python](https://learn.microsoft.com/en-us/entra/msal/python/)
