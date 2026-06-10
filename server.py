from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import json
import os
import re
import uuid

def load_env():
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        return
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

load_env()

ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "frontend"
DATA_DIR = ROOT / "data"
REPORTS_FILE = DATA_DIR / "reports.json"

FIREBASE_CONFIG_KEYS = {
    "apiKey": "FIREBASE_API_KEY",
    "authDomain": "FIREBASE_AUTH_DOMAIN",
    "projectId": "FIREBASE_PROJECT_ID",
    "storageBucket": "FIREBASE_STORAGE_BUCKET",
    "messagingSenderId": "FIREBASE_MESSAGING_SENDER_ID",
    "appId": "FIREBASE_APP_ID",
}

def parse_multipart_form(headers, body):
    """Parse multipart/form-data without using cgi module"""
    content_type = headers.get('Content-Type', '')
    boundary_match = re.search(r'boundary=([^;]+)', content_type)
    if not boundary_match:
        return {}
    
    boundary = boundary_match.group(1).encode()
    parts = body.split(boundary)
    
    result = {}
    
    for part in parts:
        if not part or part == b'--' or part == b'--\r\n' or part == b'\r\n':
            continue
        
        # Split headers and content
        if b'\r\n\r\n' in part:
            header_section, content = part.split(b'\r\n\r\n', 1)
            content = content.rstrip(b'\r\n--')
            
            # Parse headers
            headers_text = header_section.decode('utf-8', errors='ignore')
            content_disposition = re.search(r'name="([^"]+)"', headers_text)
            
            if content_disposition:
                field_name = content_disposition.group(1)
                # Check if it's a file
                filename_match = re.search(r'filename="([^"]+)"', headers_text)
                if filename_match:
                    filename = filename_match.group(1)
                    result[field_name] = {
                        'type': 'file',
                        'filename': filename,
                        'content': content
                    }
                else:
                    result[field_name] = {
                        'type': 'field',
                        'value': content.decode('utf-8', errors='ignore').strip()
                    }
    
    return result

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def read_reports():
    DATA_DIR.mkdir(exist_ok=True)
    if not REPORTS_FILE.exists():
        REPORTS_FILE.write_text("[]", encoding="utf-8")
    return json.loads(REPORTS_FILE.read_text(encoding="utf-8"))

def write_reports(reports):
    DATA_DIR.mkdir(exist_ok=True)
    REPORTS_FILE.write_text(json.dumps(reports, indent=2), encoding="utf-8")

def split_list(value):
    if not value:
        return []
    parts = re.split(r"[,;\n]+", str(value))
    return [part.strip() for part in parts if part.strip()]

def generate_observations(payload):
    doc_type = payload.get("documentType", "Medical document")
    symptoms = payload.get("symptoms", "")
    lower = f"{doc_type} {symptoms}".lower()

    observations = []
    if "x-ray" in lower or "xray" in lower or "chest" in lower:
        observations = [
            "Mild lower-lung opacity pattern should be reviewed against prior imaging.",
            "Cardiac silhouette appears within normal limits.",
            "No acute bony abnormalities detected.",
        ]
    elif "ecg" in lower or "ekg" in lower:
        observations = [
            "Normal sinus rhythm at 72 bpm.",
            "No significant ST-segment elevation or depression.",
            "QT interval within normal range.",
        ]
    else:
        observations = [
            "Document reviewed and key clinical information extracted.",
            "Patient symptoms and history documented for physician review.",
            "Complete analysis requires clinical correlation.",
        ]

    return [
        {"text": text, "confidence": ["High confidence", "Medium confidence", "Clinical review recommended"][i % 3]}
        for i, text in enumerate(observations)
    ]

def create_report(payload):
    report_id = f"VX-{uuid.uuid4().hex[:8].upper()}"
    history = split_list(payload.get("history"))
    medications = split_list(payload.get("medications"))
    observations = generate_observations(payload)
    timestamp = now_iso()

    concerns = [
        "Findings may warrant physician evaluation.",
        "Comparison with previous records is recommended.",
        "Additional testing may be considered."
    ]
    next_steps = [
        "Schedule physician consultation.",
        "Share this report with a healthcare provider.",
        "Upload previous imaging for comparison.",
        "Request expert validation review."
    ]

    return {
        "id": report_id,
        "status": "ai_generated",
        "createdAt": timestamp,
        "updatedAt": timestamp,
        "patient": {
            "name": payload.get("patientName") or "Demo Patient",
            "patientId": payload.get("patientId") or f"VX-{uuid.uuid4().hex[:6].upper()}",
            "age": payload.get("age") or "Not provided",
            "gender": payload.get("gender") or "Not provided",
        },
        "upload": {
            "documentType": payload.get("documentType") or "Medical document",
            "fileName": payload.get("fileName") or "No file name provided",
            "analysisDate": datetime.now().strftime("%B %d, %Y at %I:%M %p"),
            "symptoms": payload.get("symptoms") or "No symptoms entered",
        },
        "medicalHistory": {
            "conditions": history or ["No historical conditions entered"],
            "medications": medications or ["No medications entered"],
        },
        "currentFindings": observations,
        "potentialConcerns": concerns,
        "recommendedNextSteps": next_steps,
        "validation": {
            "reviewer": "",
            "notes": "",
            "badges": ["AI Generated", "Clinical Review Recommended"],
        },
        "auditTrail": [
            {"time": timestamp, "actor": "system", "event": "AI report generated"}
        ],
        "disclaimer": (
            "This AI-generated analysis is intended to support, not replace, "
            "professional medical judgment. Final clinical decisions require "
            "licensed healthcare provider review."
        ),
    }

class VegaHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Custom logging to show requests
        print(f"📝 {format % args}")
    
    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        
        if parsed.path == "/api/health":
            self.send_json(200, {"ok": True, "service": "Vega Medical AI"})
            return
            
        if parsed.path == "/api/firebase-config":
            config = {}
            configured_count = 0
            for public_key, env_key in FIREBASE_CONFIG_KEYS.items():
                value = os.environ.get(env_key, "")
                config[public_key] = value
                if value:
                    configured_count += 1
            
            configured = configured_count == len(FIREBASE_CONFIG_KEYS)
            self.send_json(200, {"configured": configured, "firebase": config})
            return
            
        if parsed.path == "/api/reports":
            self.send_json(200, {"reports": read_reports()})
            return
        
        self.serve_static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        
        if parsed.path == "/api/analyze":
            try:
                content_type = self.headers.get('Content-Type', '')
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length)
                
                payload = {}
                
                if 'multipart/form-data' in content_type:
                    # Parse multipart form data
                    parsed_form = parse_multipart_form(self.headers, body)
                    for key, data in parsed_form.items():
                        if data['type'] == 'field':
                            payload[key] = data['value']
                        elif data['type'] == 'file':
                            payload['fileName'] = data['filename']
                            payload['file_content'] = data['content']  # Store for later use
                else:
                    # Parse JSON
                    try:
                        payload = json.loads(body.decode('utf-8'))
                    except:
                        pass
                
                report = create_report(payload)
                reports = read_reports()
                reports.insert(0, report)
                write_reports(reports)
                self.send_json(201, {"report": report})
                
            except Exception as exc:
                print(f"Error in analyze: {exc}")
                self.send_json(400, {"error": str(exc)})
            return

        match = re.fullmatch(r"/api/reports/([^/]+)/validate", parsed.path)
        if match:
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length)
                payload = json.loads(body.decode('utf-8'))
                
                reports = read_reports()
                report_id = match.group(1)
                for report in reports:
                    if report["id"] == report_id:
                        status = payload.get("status", "expert_reviewed")
                        if status not in {"ai_generated", "expert_reviewed", "clinically_validated"}:
                            self.send_json(400, {"error": "Invalid validation status"})
                            return
                        badges = ["AI Generated"]
                        if status in {"expert_reviewed", "clinically_validated"}:
                            badges.append("Expert Reviewed")
                        if status == "clinically_validated":
                            badges.append("Clinically Validated")
                        report["status"] = status
                        report["updatedAt"] = now_iso()
                        report["validation"] = {
                            "reviewer": payload.get("reviewer", "Clinical reviewer"),
                            "notes": payload.get("notes", ""),
                            "badges": badges,
                        }
                        write_reports(reports)
                        self.send_json(200, {"report": report})
                        return
                self.send_json(404, {"error": "Report not found"})
            except Exception as exc:
                self.send_json(400, {"error": str(exc)})
            return

        self.send_json(404, {"error": "Route not found"})

    def serve_static(self, request_path):
        if request_path in {"", "/"}:
            request_path = "/index.html"
        
        # Remove query parameters
        if '?' in request_path:
            request_path = request_path.split('?')[0]
        
        safe_path = request_path.lstrip("/")
        file_path = FRONTEND_DIR / safe_path
        
        # Security check
        try:
            file_path = file_path.resolve()
            if not str(file_path).startswith(str(FRONTEND_DIR.resolve())):
                self.send_response(403)
                self.end_headers()
                return
        except:
            self.send_response(404)
            self.end_headers()
            return
        
        if not file_path.exists():
            self.send_response(404)
            self.end_headers()
            return
        
        # Determine content type
        content_type = "text/plain"
        if file_path.suffix == ".html":
            content_type = "text/html"
        elif file_path.suffix == ".css":
            content_type = "text/css"
        elif file_path.suffix == ".js":
            content_type = "application/javascript"
        elif file_path.suffix == ".png":
            content_type = "image/png"
        elif file_path.suffix == ".jpg" or file_path.suffix == ".jpeg":
            content_type = "image/jpeg"
        
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        print(f"✅ Served: {file_path}")

def main():
    host = "127.0.0.1"
    port = 8000
    
    print("=" * 60)
    print("🏥 VEGA MEDICAL AI PLATFORM")
    print("=" * 60)
    print(f"✓ Server running at http://{host}:{port}")
    print(f"✓ Frontend directory: {FRONTEND_DIR}")
    print(f"✓ Data directory: {DATA_DIR}")
    
    # Check if frontend exists
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        print(f"✅ Frontend found at: {index_path}")
    else:
        print(f"❌ ERROR: index.html not found at {index_path}")
        print(f"   Please create the frontend folder and add index.html")
        return
    
    # Check Firebase config
    firebase_configured = all(os.environ.get(key) for key in FIREBASE_CONFIG_KEYS.values())
    if firebase_configured:
        print(f"✅ Firebase: Configured")
    else:
        print(f"⚠️ Firebase: Missing configuration - check .env file")
        missing = [k for k in FIREBASE_CONFIG_KEYS.values() if not os.environ.get(k)]
        print(f"   Missing: {', '.join(missing)}")
    
    print("=" * 60)
    print("\n🌐 Access at: http://{}:{}\n".format(host, port))
    
    server = ThreadingHTTPServer((host, port), VegaHandler)
    server.serve_forever()

if __name__ == "__main__":
    main()