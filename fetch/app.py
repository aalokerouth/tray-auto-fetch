from mitmproxy import http
import json

class DataCollector:
    def __init__(self):
        # We'll save the intercepted data here
        self.output_file = "intercepted_traffic.log"

    def response(self, flow: http.HTTPFlow):
        # 1. Filter by your target service's domain or URL path
        # Replace 'api.target-service.com' with the actual domain you are looking for.
        if "api.target-service.com" in flow.request.pretty_url:
            
            # 2. Extract Request Info
            req_url = flow.request.pretty_url
            req_method = flow.request.method
            
            print(f"[+] Intercepted {req_method} to: {req_url}")

            # 3. Extract Response Info
            if flow.response and flow.response.content:
                # Get the plain text response body
                resp_text = flow.response.get_text()
                
                try:
                    # If it's a JSON API, parsing it makes it easier to read/extract specific keys
                    data = json.loads(resp_text)
                    formatted_data = json.dumps(data, indent=4)
                except json.JSONDecodeError:
                    # If it's not JSON, just log the raw text
                    formatted_data = resp_text

                # 4. Save to your collection file
                with open(self.output_file, "a", encoding="utf-8") as f:
                    f.write(f"--- {req_method} {req_url} ---\n")
                    f.write(f"Status Code: {flow.response.status_code}\n")
                    f.write(f"Response Body:\n{formatted_data}\n\n")

# Register the addon with mitmproxy
addons = [
    DataCollector()
]