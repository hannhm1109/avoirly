"""Probe only the isolated recovered stack, never send messages or model calls."""

import base64
import hashlib
import json
import os
import time
from pathlib import Path

import httpx

STAGE = {"step": "startup"}


def difference_path(left, right, path=""):
    """Return schema field names only, never recovered values."""
    if isinstance(left, dict) and isinstance(right, dict):
        if left.keys() != right.keys():
            return path + ".keys"
        for key in left:
            if left[key] != right[key]:
                return difference_path(left[key], right[key], path + "." + key)
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return path + ".length"
        for index, (a, b) in enumerate(zip(left, right, strict=True)):
            if a != b:
                return difference_path(a, b, path + "." + str(index))
    return path


def main():
    root = Path("/verify")
    access = json.loads((root / "access.private.json").read_text())
    expected = json.loads(base64.b64decode(access["canary_base64"]))
    web = os.environ["AVOIRLY_WEB_ORIGIN"]
    api = os.environ["AVOIRLY_API_ORIGIN"]
    auth = os.environ["SUPABASE_URL"]
    client = httpx.Client(verify="/verify/tls/cert.pem", timeout=15)
    for attempt in range(45):
        try:
            if client.get(api + "/api/v1/health").status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    else:
        raise ValueError("Recovered API unavailable")
    report = {"restored_api_healthy": True}
    STAGE["step"] = "auth_logins"
    tokens = []
    for account in access["accounts"]:
        response = client.post(
            auth + "/auth/v1/token?grant_type=password",
            headers={"apikey": os.environ["SUPABASE_PUBLISHABLE_KEY"]},
            json={"email": account["email"], "password": account["password"]},
        )
        response.raise_for_status()
        tokens.append(response.json()["access_token"])
    report["two_restored_auth_logins"] = len(tokens) == 2
    STAGE["step"] = "case_restore"
    owner = {"Authorization": "Bearer " + tokens[0], "Origin": web}
    stranger = {"Authorization": "Bearer " + tokens[1], "Origin": web}
    response = client.get(api + "/api/v1/cases/" + expected["id"], headers=owner)
    response.raise_for_status()
    case = response.json()
    for field in [
        "id",
        "status",
        "version",
        "current_revision",
        "potential_credit_net",
        "documents",
        "extractions",
        "comparison",
        "draft",
        "recovery",
    ]:
        if case[field] != expected[field]:
            STAGE["step"] = (
                "case_restore_" + field + difference_path(case[field], expected[field])
            )
            raise ValueError("Recovered case field differs")
    report["known_draft_and_credit_ledger_match"] = True
    if (
        client.get(
            api + "/api/v1/cases/" + expected["id"], headers=stranger
        ).status_code
        != 404
    ):
        raise ValueError("Recovered owner isolation failed")
    if client.get(api + "/api/v1/cases/" + expected["id"]).status_code != 401:
        raise ValueError("Recovered authentication guard failed")
    report["restored_owner_isolation"] = True
    STAGE["step"] = "source_downloads"
    checked = 0
    for role, document in case["documents"].items():
        response = client.get(
            api + "/api/v1/documents/" + document["id"] + "/content", headers=owner
        )
        response.raise_for_status()
        if (
            hashlib.sha256(response.content).hexdigest()
            != access["source_sha256"][role]
        ):
            raise ValueError("Recovered source bytes differ")
        if (
            client.get(
                api + "/api/v1/documents/" + document["id"] + "/content",
                headers=stranger,
            ).status_code
            != 404
        ):
            raise ValueError("Recovered private download guard failed")
        checked += 1
    for evidence in case["recovery"]["evidence"]:
        response = client.get(
            api + "/api/v1/evidence/" + evidence["id"] + "/content", headers=owner
        )
        response.raise_for_status()
        if hashlib.sha256(response.content).hexdigest() != evidence["sha256"]:
            raise ValueError("Recovered evidence bytes differ")
        checked += 1
    report["source_and_proof_files_verified"] = checked
    STAGE["step"] = "private_buckets"
    for bucket in ["avoirly-documents", "avoirly-backups"]:
        response = client.get(
            auth + "/storage/v1/bucket/" + bucket,
            headers={"apikey": os.environ["SUPABASE_SECRET_KEY"]},
        )
        response.raise_for_status()
        if response.json()["public"] is not False:
            raise ValueError("Recovered bucket is public")
    report["private_buckets_restored"] = True
    STAGE["step"] = "web_login"
    browser = httpx.Client(
        verify="/verify/tls/cert.pem", timeout=20, headers={"Origin": web}
    )
    response = browser.post(
        web + "/auth/login",
        json={k: access["accounts"][0][k] for k in ["email", "password"]},
    )
    response.raise_for_status()
    if not any(
        cookie.secure and cookie.has_nonstandard_attr("HttpOnly")
        for cookie in browser.cookies.jar
    ):
        raise ValueError("Recovered web secure session missing")
    STAGE["step"] = "web_gateway"
    response = browser.get(web + "/api/v1/cases/" + expected["id"])
    response.raise_for_status()
    if response.json()["draft"] != expected["draft"]:
        raise ValueError("Recovered web gateway draft differs")
    browser.post(web + "/auth/logout").raise_for_status()
    report["restored_web_login_gateway_logout"] = True
    if browser.get(web + "/api/v1/cases/" + expected["id"]).status_code != 401:
        raise ValueError("Recovered logout failed")
    (root / "service-report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "recovered_service_probe_failed": type(exc).__name__,
                    "probe_stage": STAGE["step"],
                    "http_status": exc.response.status_code
                    if isinstance(exc, httpx.HTTPStatusError)
                    else None,
                }
            )
        )
        raise SystemExit(1) from None
