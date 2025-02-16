import os
import sqlite3
import dropbox
import logging
from flask import Flask, request, jsonify

# Konfigurera logging
logging.basicConfig(level=logging.DEBUG)

# Ladda Dropbox Access Token från en miljövariabel
ACCESS_TOKEN = os.getenv("DROPBOX_ACCESS_TOKEN")
if not ACCESS_TOKEN:
    raise ValueError("ERROR: Saknar Dropbox Access Token. Ange den som en miljövariabel.")

dbx = dropbox.Dropbox(ACCESS_TOKEN)

# Initiera Flask
app = Flask(__name__)

# Databasanslutning
def get_db_connection():
    conn = sqlite3.connect("dropbox_index.db")
    conn.row_factory = sqlite3.Row
    return conn

# Skapa databastabeller
def create_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id TEXT PRIMARY KEY,
            name TEXT,
            path TEXT,
            size INTEGER,
            modified TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_state (
            cursor TEXT
        )
    """)
    conn.commit()
    conn.close()

# Hämta senaste cursor för Dropbox Delta API
def get_latest_cursor():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT cursor FROM sync_state ORDER BY ROWID DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row["cursor"] if row else None

# Uppdatera cursor i databasen
def update_cursor(new_cursor):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sync_state")
    cursor.execute("INSERT INTO sync_state (cursor) VALUES (?)", (new_cursor,))
    conn.commit()
    conn.close()

# Delta-baserad synkning
def sync_dropbox():
    try:
        cursor = get_latest_cursor()
        
        if not cursor:
            result = dbx.files_list_folder_get_latest_cursor("", recursive=True)
            update_cursor(result.cursor)
            return "Initial cursor skapad."

        result = dbx.files_list_folder_continue(cursor)
        conn = get_db_connection()
        cur = conn.cursor()

        for entry in result.entries:
            if isinstance(entry, dropbox.files.FileMetadata):
                cur.execute("""
                    INSERT INTO files (id, name, path, size, modified)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET 
                        name = excluded.name, 
                        path = excluded.path, 
                        size = excluded.size, 
                        modified = excluded.modified
                """, (entry.id, entry.name, entry.path_lower, entry.size, entry.client_modified))

            elif isinstance(entry, dropbox.files.DeletedMetadata):
                cur.execute("DELETE FROM files WHERE path = ?", (entry.path_lower,))

        conn.commit()
        conn.close()

        update_cursor(result.cursor)
        return "Synkronisering klar."

    except Exception as e:
        logging.error(f"Fel vid synkronisering: {e}")
        return f"Fel vid synkronisering: {e}"

# Webhook för Dropbox-notifiering
@app.route('/dropbox_webhook', methods=['GET', 'POST'])
def dropbox_webhook():
    logging.debug(f"Webhook request: {request.method} - {request.args}")
    
    if request.method == 'GET':
        challenge = request.args.get('challenge')
        if challenge:
            logging.info(f"Verifiering lyckades: {challenge}")
            return challenge, 200
        return "Missing challenge parameter", 400

    if request.method == 'POST':
        sync_result = sync_dropbox()
        return jsonify({"status": sync_result}), 200

# Debugg-endpoint för att testa webhook
@app.route('/debug', methods=['GET'])
def debug():
    return jsonify({"message": "Flask server fungerar", "ngrok_url": request.url_root}), 200

# API-endpoint för att manuellt trigga en synkning
@app.route('/sync', methods=['POST'])
def sync_manual():
    sync_result = sync_dropbox()
    return jsonify({"status": sync_result}), 200

# API-endpoint för att söka filer
@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('q')
    if not query:
        return jsonify({"error": "Ingen sökterm angiven"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, path, modified FROM files WHERE name LIKE ?", ('%' + query + '%',))
    results = cursor.fetchall()
    conn.close()
    return jsonify({"results": [dict(row) for row in results]})

# API-endpoint för att lista alla filer
@app.route('/list', methods=['GET'])
def list_files():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, path, modified FROM files")
    results = cursor.fetchall()
    conn.close()
    return jsonify({"files": [dict(row) for row in results]})

# API-endpoint för att hämta en fil från Dropbox
@app.route('/download', methods=['GET'])
def download():
    file_path = request.args.get('file')
    if not file_path:
        return jsonify({"error": "Ingen fil angiven"}), 400

    try:
        shared_links = dbx.sharing_list_shared_links(path=file_path)
        if shared_links.links:
            return jsonify({"download_url": shared_links.links[0].url})

        shared_link = dbx.sharing_create_shared_link_with_settings(file_path)
        return jsonify({"download_url": shared_link.url})

    except Exception as e:
        logging.error(f"Fel vid hämtning av fil: {e}")
        return jsonify({"error": str(e)}), 500

# Starta Flask-servern
if __name__ == '__main__':
    create_table()
    app.run(debug=True, host="0.0.0.0", port=5001)