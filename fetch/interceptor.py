from mitmproxy import http
import json

class LatestDataCatcher:
    def __init__(self):
        # The file that will always hold the most recent data
        self.output_file = "latest.json"

    def response(self, flow: http.HTTPFlow):
        # Target your specific dashboard API
        if "ws_st_dashboard" in flow.request.pretty_url:
            
            # Ensure it was a successful request with a body
            if flow.response and flow.response.status_code == 200 and flow.response.content:
                resp_text = flow.response.get_text()
                
                # Format as JSON if possible, otherwise save raw text
                try:
                    data = json.loads(resp_text)
                    content_to_write = json.dumps(data, indent=4)
                except json.JSONDecodeError:
                    content_to_write = resp_text

                # Use 'w' to OVERWRITE the file, keeping only the latest data
                with open(self.output_file, "w", encoding="utf-8") as f:
                    f.write(content_to_write)
                    
                print(f"[+] Caught new data! Overwrote {self.output_file}")

# Register the addon
addons = [
    LatestDataCatcher()
]