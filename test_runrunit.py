import os
import requests
from dotenv import load_dotenv

load_dotenv("runrun_report/.env")
APP_KEY = os.getenv("APP_KEY")
USER_TOKEN = os.getenv("USER_TOKEN")

headers = {
    "App-Key": APP_KEY,
    "User-Token": USER_TOKEN,
    "Content-Type": "application/json",
}

# Pegar uma task para teste
resp = requests.get("https://runrun.it/api/v1.0/tasks?limit=1", headers=headers)
print("GET /tasks?limit=1:", resp.status_code)
tasks = resp.json()
if tasks:
    task_id = tasks[0]["id"]
    print("Task ID:", task_id)
    resp_tasks = requests.get("https://runrun.it/api/v1.0/tasks?limit=50", headers=headers)
    # Try to see if there is a download endpoint or URL in the headers
    resp_docs = requests.get(f"https://runrun.it/api/v1.0/documents/38902288/download", headers=headers, allow_redirects=False)
    print("GET /documents/38902288/download:", resp_docs.status_code)
    if resp_docs.status_code in (301, 302):
        print("Redirect Location:", resp_docs.headers.get("Location"))
        
    resp_docs2 = requests.get(f"https://runrun.it/api/v1.0/documents/38902288", headers=headers)
    print("GET /documents/38902288:", resp_docs2.status_code)
    import json
    print(json.dumps(resp_docs2.json(), indent=2))
