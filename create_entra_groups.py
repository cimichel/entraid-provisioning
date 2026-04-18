import csv
import json
import logging
import os
import re
import time

import requests
from logging.handlers import RotatingFileHandler


# ========================
# CONFIG
# ========================
TENANT_ID = os.environ.get("AZURE_TENANT_ID", "your-tenant-id")
CLIENT_ID = os.environ.get("AZURE_CLIENT_ID", "your-client-id")
CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET", "your-client-secret")

CSV_FILE = "groups.csv"
DRY_RUN = True  # Toggle True or False

GRAPH_URL = "https://graph.microsoft.com/v1.0"

# ========================
# LOGGING
# ========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("provisioning.log", encoding="utf-8"),
    ]
)
handler = RotatingFileHandler(
    "provisioning.log",
    maxBytes=1_000_000,  # 1MB
    backupCount=3
)

# ========================
# AUTH
# ========================


def get_token():
    if DRY_RUN:
        return "fake-token"

    app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        client_credential=CLIENT_SECRET,
    )
    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"])

    if "access_token" not in result:
        raise Exception(
            f"Failed to get token: {result.get('error_description', result)}")

    return result["access_token"]

# ========================
# Email and data validation
# ========================


def is_valid_email(email):
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email)


def validate_row(row):
    required_fields = ["group_name", "mail_nickname", "owner_upn"]

    for field in required_fields:
        if not row.get(field):
            return False, f"Missing field: {field}"

    if not is_valid_email(row["owner_upn"]):
        return False, f"Invalid owner email: {row['owner_upn']}"

    members = row.get("members_upns", "").split(";")
    for m in members:
        if m and not is_valid_email(m.strip()):
            return False, f"Invalid member email: {m}"

    return True, None

# ========================
# GRAPH HELPERS
# ========================


def get_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


def resolve_upn(token, upn, cache):
    """Resolve UPN to object ID. Using cache to do not repeat calls."""
    if upn in cache:
        return cache[upn]

    response = requests.get(f"{GRAPH_URL}/users/{upn}",
                            headers=get_headers(token), timeout=30)

    if response.status_code == 200:
        cache[upn] = response.json()["id"]
    else:
        logging.warning(f"UPN not found in tenant: {upn}")
        cache[upn] = None

    return cache[upn]


def group_already_exists(token, group_name):
    """Verifies if group already exists in Entra before creating a new one."""
    encoded = group_name.replace("'", "''")
    url = f"{GRAPH_URL}/groups?$filter=displayName eq '{encoded}'&$select=id,displayName"
    response = requests.get(url, headers=get_headers(token), timeout=30)

    if response.status_code == 200 and response.json().get("value"):
        return response.json()["value"][0]["id"]

    return None

# ========================
# Create New Group.
# ========================


def create_group(token, row):
    if DRY_RUN:
        logging.info(f"[DRY RUN] Would create group: {row['group_name']}")
        return {"id": "dry-run-id"}

    body = {
        "displayName":        row["group_name"],
        "description":        row.get("description", ""),
        "mailEnabled":        False,
        "mailNickname":       row["mail_nickname"],
        "securityEnabled":    True,
        "isAssignableToRole": row.get("assignable_to_role", "false").lower() == "true",
        "groupTypes":         [],
    }

    response = requests.post(
        f"{GRAPH_URL}/groups", json=body, headers=get_headers(token), timeout=30)

    if response.status_code not in [200, 201]:
        raise Exception(f"Failed to create group: {response.text}")

    return response.json()

# ========================
# Add Group Owner
# ========================


def add_owner(token, group_id, owner_upn, cache):
    logging.info(f"Adding owner {owner_upn} to group {group_id}")

    if DRY_RUN:
        return

    owner_id = resolve_upn(token, owner_upn, cache)
    if not owner_id:
        logging.warning(f"Owner not found, skipping: {owner_upn}")
        return

    body = {"@odata.id": f"{GRAPH_URL}/directoryObjects/{owner_id}"}
    response = requests.post(
        f"{GRAPH_URL}/groups/{group_id}/owners/$ref",
        json=body,
        headers=get_headers(token),
        timeout=30
    )

    if response.status_code not in [200, 201, 204]:
        logging.warning(f"Failed to add owner {owner_upn}: {response.text}")

# ========================
# Add Members
# ========================


def add_members(token, group_id, members, cache):
    for member in members:
        member = member.strip()
        if not member:
            continue

        logging.info(f"Adding member {member} to group {group_id}")

        if DRY_RUN:
            continue

        member_id = resolve_upn(token, member, cache)
        if not member_id:
            logging.warning(f"Member not found, skipping: {member}")
            continue

        body = {"@odata.id": f"{GRAPH_URL}/directoryObjects/{member_id}"}
        response = requests.post(
            f"{GRAPH_URL}/groups/{group_id}/members/$ref",
            json=body,
            headers=get_headers(token),
            timeout=30
        )

        if response.status_code not in [200, 201, 204]:
            logging.warning(f"Failed to add member {member}: {response.text}")

# ========================
# Main method
# ========================


def main():
    logging.info("Starting group creation process...")
    logging.info(f"DRY_RUN = {DRY_RUN}")

    token = get_token()
    upn_cache = {}
    audit_log = []
    seen_names = set()

    with open(CSV_FILE, newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            group_name = row["group_name"]
            result = {"group_name": group_name,
                      "status": None, "group_id": None}

            # Duplicate check (within .csv file)
            if group_name in seen_names:
                logging.warning(f"Duplicate group skipped: {group_name}")
                result["status"] = "skipped_duplicate_csv"
                audit_log.append(result)
                continue

            seen_names.add(group_name)

            # Validation
            valid, error = validate_row(row)
            if not valid:
                logging.error(f"Validation failed for {group_name}: {error}")
                result["status"] = f"invalid: {error}"
                audit_log.append(result)
                continue

            # Idempotency check (against Entra ID)
            if not DRY_RUN:
                existing_id = group_already_exists(token, group_name)
                if existing_id:
                    logging.warning(
                        f"Group already exists in Entra, skipping: {group_name} ({existing_id})")
                    result["status"] = "skipped_already_exists"
                    result["group_id"] = existing_id
                    audit_log.append(result)
                    continue

            try:
                group = create_group(token, row)
                group_id = group["id"]
                result["group_id"] = group_id

                # Small pause for Graph eventual consistency
                if not DRY_RUN:
                    time.sleep(1)

                add_owner(token, group_id, row["owner_upn"], upn_cache)

                members = row.get("members_upns", "").split(";")
                add_members(token, group_id, members, upn_cache)

                logging.info(f"Successfully processed group: {group_name}")
                result["status"] = "success"

            except Exception as e:
                logging.error(f"Error processing {group_name}: {str(e)}")
                result["status"] = f"failed: {str(e)}"

            audit_log.append(result)

    # Saving audit log file
    with open("audit_log.json", "w", encoding="utf-8") as f:
        json.dump(audit_log, f, indent=2)

    # Return exec summary
    statuses = [r["status"] for r in audit_log]
    success = statuses.count("success")
    skipped = sum(1 for s in statuses if s and s.startswith("skipped"))
    failed = sum(1 for s in statuses if s and s.startswith("failed"))
    invalid = sum(1 for s in statuses if s and s.startswith("invalid"))

    logging.info("Process completed.")
    logging.info(
        f"Success: {success} | Skipped: {skipped} | Failed: {failed} | Invalid: {invalid}")
    logging.info("Audit log saved to audit_log.json")


if __name__ == "__main__":
    main()
