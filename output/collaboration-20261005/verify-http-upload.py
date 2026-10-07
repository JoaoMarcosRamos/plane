"""Real multipart/session integration; no credentials are printed or saved."""
import hashlib
import http.client
import json
from pathlib import Path
from uuid import uuid4

folder = Path(__file__).parent
connection = http.client.HTTPConnection("127.0.0.1", 8941)
connection.request("GET", "/fixture/info/")
info = json.loads(connection.getresponse().read())
connection.request("GET", "/fixture/login/author")
login = connection.getresponse()
cookie = login.getheader("Set-Cookie").split(";", 1)[0]
login.read()
base = f"/api/workspaces/{info['workspace_slug']}/radar/objects/{info['object_id']}"
headers = {"Cookie": cookie}
connection.request("GET", base + "/collaboration/", headers=headers)
snapshot = json.loads(connection.getresponse().read())
data = (folder / "upload-evidence.txt").read_bytes()
boundary = uuid4().hex
body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="upload-evidence.txt"\r\n'
        'Content-Type: text/plain\r\n\r\n').encode() + data + f'\r\n--{boundary}--\r\n'.encode()
headers.update({"Content-Type": f"multipart/form-data; boundary={boundary}",
                "Idempotency-Key": "collaboration-http-proof", "X-Radar-Expected-Versions": json.dumps({info["object_id"]: snapshot["object_version"]})})
connection.request("POST", base + "/attachments/", body, headers)
response = connection.getresponse()
assert response.status == 200
result = json.loads(response.read())
connection.request("POST", base + "/attachments/", body, headers)
replay = connection.getresponse()
assert replay.status == 200 and json.loads(replay.read()) == result
connection.request("GET", base + f"/attachments/{result['data']['item_id']}/download/", headers={"Cookie": cookie})
download = connection.getresponse()
assert download.status == 200 and download.read() == data
report = {"upload_status": response.status, "download_status": download.status, "sha256": hashlib.sha256(data).hexdigest(),
          "replay_identical": True, "object_id": info["object_id"], "attachment_id": result["data"]["item_id"],
          "command_id": result["command_id"], "provenance_id": result["provenance_id"]}
(folder / "http-upload-evidence.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
