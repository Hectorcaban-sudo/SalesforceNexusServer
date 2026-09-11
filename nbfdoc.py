"""
Example Salesforce Nexus AI Server payload processor.

Contract: read one JSON object from stdin, print one JSON object to stdout.
A non-zero exit code, invalid JSON on stdout, or exceeding the timeout is
treated as a processing failure.

Logging: print any diagnostic/log messages to stderr (not stdout - stdout is
reserved for the JSON result). Every stderr line is automatically mirrored
into the Salesforce Nexus AI Server System Logs page, tagged with this
processor's name, whether the run succeeds or fails.

Context: two environment variables give you access to the rest of the
system without needing any imports:
  - NEXUS_ORG: the Salesforce org that triggered this event (login_url,
    auth_type, client_id/secret, username/password/security_token,
    api_version) - "{}" if there's no org context (e.g. a manual test run
    with no org selected).
  - NEXUS_ADMIN_CONFIG: {"dss_client": {...}, "langflow": {...},
    "email": {...}, "processing_mode": {...}} - the same admin configuration
    the built-in processing modes use, including credentials, so you can
    call out to Dataiku DSS, Langflow, or send your own email (via smtplib
    and the "email" settings) directly from your script.
"""
import sys
import os
import json
from simple_salesforce import Salesforce
import requests
from io import BytesIO
from urllib.parse import urlparse
def process(payload: dict) -> dict:
    # Anything printed here goes to the System Logs page automatically.
    print(f"Received payload with keys: {list(payload.keys())}", file=sys.stderr)

    org = json.loads(os.environ.get("NEXUS_ORG", "{}"))
    admin_config = json.loads(os.environ.get("NEXUS_ADMIN_CONFIG", "{}"))
    if org:
        print(f"Triggered by org: {org.get('name')} ({org.get('login_url')})", file=sys.stderr)
        #print(f"Triggered by org: with keys: {list(org.keys())}", file=sys.stderr)

    payload2 = payload["ChangeEventHeader"]

    changeType = payload2["changeType"]
    print(f"changeType: {changeType}", file=sys.stderr)

    if(changeType == 'CREATE'):
        print(f"Received ChangeEventHeader with keys: {list(payload2.keys())}", file=sys.stderr)
        linked_entity_id = payload["LinkedEntityId"]          # Opportunity ID
        content_document_id = payload["ContentDocumentId"]


        try:

            
            def get_site_id(access_token, hostname, site_path):
                url = f"https://graph.microsoft.us/v1.0/sites/{hostname}:/{site_path}"
                resp = requests.get(url, headers={"Authorization": f"Bearer {access_token}"})
                js = resp.json()
                return js["id"]

            def list_drives(access_token, site_id):
                url = f"https://graph.microsoft.us/v1.0/sites/{site_id}/drives"
                resp = requests.get(url, headers={"Authorization": f"Bearer {access_token}"})
                js = resp.json()
                return js["value"]   # list of drive objects

            def extract_prefix(url):
                host = urlparse(url).hostname  # e.g., baesystemsins--uat.sandbox.my.salesforce.com
                parts = host.split(".")
                # Remove the last two parts: "salesforce" and "com"
                return ".".join(parts[:-2])

            
            def get_graph_token(tenant_id, client_id, client_secret):
                token_url = f"https://login.microsoftonline.us/{tenant_id}/oauth2/v2.0/token"
                data = {
                    "client_id": client_id,
                    "scope": "https://graph.microsoft.us/.default",
                    "client_secret": client_secret,
                    "grant_type": "client_credentials"
                }
                token_result = requests.post(token_url, data=data).json()
                access_token = token_result["access_token"]
                return access_token #requests.post(token_url, data=data).json()["access_token"]

            salesforcedomain = extract_prefix(org.get('login_url'))
            print(f"salesforcedomain: {salesforcedomain}", file=sys.stderr)
            # ---- Salesforce auth ----
            sf = Salesforce(
            consumer_key=org.get('client_id'),
            consumer_secret=org.get('client_secret'),            
            domain=salesforcedomain #'baesystemsins--staging.sandbox.my' # Do not include 'https://' or '.salesforce.com'
            )

            opp = sf.Opportunity.get(linked_entity_id)

            business = opp["Business_Area__c"]
            print(f"NBF Business Area: {business}", file=sys.stderr)

            #Select Id, VersionData, Title from ContentVersion where ContentDocumentId =:cd.ContentDocumentId
            # ------------------------------------------
            # 2. Query Salesforce for file download URL
            # ------------------------------------------
            # Get ContentVersion for the document
            query = f"""
                SELECT Id, Title,FileExtension,VersionData
                FROM ContentVersion
                WHERE ContentDocumentId = '{content_document_id}'
                ORDER BY VersionNumber DESC
                LIMIT 1
            """
            result = sf.query(query)
            content_version = result["records"][0]

            version_id = content_version["Id"]

            # Actual file download URL
            download_url = f"{sf.base_url}sobjects/ContentVersion/{version_id}/VersionData"
            print(f"download_url: {download_url})", file=sys.stderr)


            file_response = requests.get(
                download_url,
                headers={"Authorization": f"Bearer {sf.session_id}"}
            )

            file_bytes = BytesIO(file_response.content)

            

            # ------------------------------------------
            # 3. Upload to SharePoint (Microsoft Graph)
            # ------------------------------------------

            # ---- Microsoft Graph OAuth ----
            tenant_id = "microsof_ID"
            client_id = "client_id"
            client_secret = "client_secret"

            token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
            # token_data = {
            #     "client_id": client_id,
            #     "scope": "https://graph.microsoft.com/.default",
            #     "client_secret": client_secret,
            #     "grant_type": "client_credentials"
            # }

            # token_result = requests.post(token_url, data=token_data).json()
            # access_token = token_result["access_token"]

            
            # Example usage:
            access_token = get_graph_token(tenant_id, client_id, client_secret)


            # ---- Upload file to SharePoint document library ----
            #site_id = "baesystemsus.sharepoint.us"
           
            file_name = f"{content_version["Title"]}.{content_version["FileExtension"]}"  # rename however you want

            
            # site_id = get_site_id(
            #     access_token,
            #     "baesystemsus.sharepoint.us",
            #     "sites/IS-HQ_InSNBF"
            # )

            site_id = "3675b009-0016-4159-87c4-48f00a952f61"
            drive_id = "b!CbB1NhYAWUGHxEjwCpUvYUo8zvNQ-HlHiDzmfa1bZjceuJh7lu5ASpY0zv68kXih"

            print(f"site_id: {site_id})", file=sys.stderr)


            # drives = list_drives(access_token, site_id)
            # for d in drives:
            #     print("Drive:", d["name"], " â†’ ID:", d["id"],file=sys.stderr)


            #//Get the business area
            # Get the current date and time
            from datetime import datetime
            now = datetime.now()

            # Extract the year
            current_year = now.year
            mainfolder = str(current_year) + '%20NBF%20Reports'


            subfolder = business + ' Projects'

            print(f"subfolder: {subfolder})", file=sys.stderr)

            upload_url = f"https://graph.microsoft.us/v1.0/drives/{drive_id}/root:/{mainfolder}/{subfolder}/{file_name}:/content"

            upload_resp = requests.put(
                upload_url,
                headers={"Authorization": f"Bearer {access_token}"},
                data=file_bytes.getvalue()
            )
            js = upload_resp.json()
            uploaded_item_id = js["id"]

            checkin_url = f"https://graph.microsoft.us/v1.0/drives/{drive_id}/items/{uploaded_item_id}/checkin"

            checkin_payload = {
                "comment": "Checked in via API"                
            }

            checkin_resp = requests.post(
                        checkin_url,
                        headers={"Authorization": f"Bearer {access_token}"},
                        json=checkin_payload
                    )
            #js = checkin_resp.json()
            #print(f"checkin_resp: {js})", file=sys.stderr)

        except Exception as exc:              
              print(f"Exception: {exc})", file=sys.stderr)
              return {
                          "status": "Failed",
                          "summary": "Processed by custom uploaded script",
                          "echo": payload,
                      }


        # Your custom logic goes here. This example just echoes the payload
        # back with a computed field, as a starting point.
        return {
            "status": "ok",
            "summary": "Processed by custom uploaded script",
            "echo": payload,
        }

    else:
        # Your custom logic goes here. This example just echoes the payload
            # back with a computed field, as a starting point.
            return {
                "status": "ok",
                "summary": "Processed by ProcessNBDocument script. Non Create Event",
                "echo": payload,
            }


if __name__ == "__main__":
    input_payload = json.loads(sys.stdin.read() or "{}")
    result = process(input_payload)
    print(json.dumps(result))
