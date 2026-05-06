from flask import Flask, render_template_string, jsonify
import sqlite3

app = Flask(__name__)
DB_PATH = 'warehouse.db'

# --- FRONTEND HTML, CSS, AND JAVASCRIPT ---
# We put this in a string so you only have to manage one file!
HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Live Tray Tracker</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #f4f4f9; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        .header { background: #333; color: white; padding: 15px; border-radius: 8px; margin-bottom: 20px; display: flex; justify-content: space-between;}
        .input-group { margin-bottom: 20px; display: flex; gap: 10px; }
        input { padding: 10px; font-size: 16px; flex-grow: 1; border: 1px solid #ccc; border-radius: 4px; }
        button { padding: 10px 20px; font-size: 16px; background: #28a745; color: white; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background: #218838; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 15px; }
        .card { background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); border-left: 5px solid #007bff; }
        .tray-id { font-size: 24px; font-weight: bold; color: #333; margin-bottom: 10px; }
        .data-row { font-size: 16px; color: #555; margin: 5px 0; }
        .error { color: red; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>Live Tray Tracker</h2>
            <div style="text-align: right;">
                <small>Next Auto-Sync In:</small><br>
                <b id="timer">15</b>s
            </div>
        </div>

        <div class="input-group">
            <input type="text" id="trayInput" placeholder="Enter Tray Number (e.g., 22421)">
            <button onclick="addTray()">Track Tray</button>
        </div>
        <div id="message"></div>

        <div class="grid" id="trayGrid">
            <!-- Tracked trays will appear here -->
        </div>
    </div>

    <script>
        // Store the tray IDs we are currently tracking
        let trackedTrays = [];
        let countdown = 15;

        // 1. Add a new tray to the tracker
        async function addTray() {
            const input = document.getElementById('trayInput');
            const trayId = input.value.trim();
            const msgBox = document.getElementById('message');
            
            if (!trayId) return;
            if (trackedTrays.includes(trayId)) {
                msgBox.innerHTML = `<span class="error">Already tracking Tray ${trayId}</span>`;
                return;
            }

            // Immediately fetch its data from the database
            const data = await fetchTrayData(trayId);
            
            if (data.success) {
                trackedTrays.push(trayId);
                msgBox.innerHTML = ''; // clear error
                input.value = ''; // clear input
                renderGrid();
            } else {
                msgBox.innerHTML = `<span class="error">Tray ${trayId} not found in database.</span>`;
            }
        }

        // 2. Fetch data for a single tray from our Python API
        async function fetchTrayData(trayId) {
            const response = await fetch(`/api/tray/${trayId}`);
            return await response.json();
        }

        // 3. Update the UI with the latest data
        async function renderGrid() {
            const grid = document.getElementById('trayGrid');
            grid.innerHTML = ''; // Clear current display

            for (const trayId of trackedTrays) {
                const data = await fetchTrayData(trayId);
                
                if (data.success) {
                    grid.innerHTML += `
                        <div class="card" id="card-${trayId}">
                            <div class="tray-id">Tray: ${trayId}</div>
                            <div class="data-row"><b>Lane:</b> ${data.lane || 'N/A'}</div>
                            <div class="data-row"><b>Rack:</b> ${data.rack || 'N/A'}</div>
                        </div>
                    `;
                } else {
                    // If it disappears from the DB for some reason
                    grid.innerHTML += `
                        <div class="card" style="border-left-color: red;">
                            <div class="tray-id">Tray: ${trayId}</div>
                            <div class="data-row error">Lost connection to DB</div>
                        </div>
                    `;
                }
            }
        }

        // 4. Background Polling Loop (Every 15 seconds)
        setInterval(() => {
            countdown--;
            document.getElementById('timer').innerText = countdown;
            
            if (countdown <= 0) {
                if (trackedTrays.length > 0) {
                    renderGrid(); // Refresh all cards
                }
                countdown = 15; // Reset timer
            }
        }, 1000);
    </script>
</body>
</html>
"""

# --- BACKEND API ROUTES ---

@app.route('/')
def home():
    """Serves the main HTML page."""
    return render_template_string(HTML_PAGE)

@app.route('/api/tray/<tray_id>')
def get_tray(tray_id):
    """API endpoint for the frontend to query the database."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            # Only pull Lane and Rack (location) per instructions
            cursor.execute('''
                SELECT lane_code, location
                FROM tray_data 
                WHERE tray_id = ?
            ''', (tray_id,))
            
            result = cursor.fetchone()
            
            if result:
                return jsonify({
                    "success": True, 
                    "lane": result[0], 
                    "rack": result[1]
                })
            else:
                return jsonify({"success": False, "error": "Tray not found"})
                
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

if __name__ == '__main__':
    print("Starting Web Dashboard...")
    print("Open your browser and go to: http://127.0.0.1:5000")
    # Run the server on port 5000
    app.run(debug=True, port=5000)