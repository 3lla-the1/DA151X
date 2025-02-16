import requests
import pytest
from unittest.mock import patch

BASE_URL = "http://127.0.0.1:5001"  # Byt till ngrok-URL om du testar externt

def test_debug():
    response = requests.get(f"{BASE_URL}/debug")
    assert response.status_code == 200
    assert "Flask server fungerar" in response.json().get("message", "")

def test_list_files():
    response = requests.get(f"{BASE_URL}/list")
    assert response.status_code == 200
    assert isinstance(response.json().get("files", []), list)

def test_list_files_structure():
    response = requests.get(f"{BASE_URL}/list")
    assert response.status_code == 200
    files = response.json().get("files", [])
    if files:
        assert all("name" in f and "path" in f and "modified" in f for f in files)

# SÖKNING 
def test_search():
    response = requests.get(f"{BASE_URL}/search?q=TESTER")
    assert response.status_code == 200
    assert isinstance(response.json().get("results", []), list)

def test_search_no_results():
    response = requests.get(f"{BASE_URL}/search?q=DOES_NOT_EXIST")
    assert response.status_code == 200
    assert isinstance(response.json().get("results", []), list)
    assert len(response.json()["results"]) == 0

def test_search_results_match_query():
    query = "TESTER"
    response = requests.get(f"{BASE_URL}/search?q={query}")
    assert response.status_code == 200
    results = response.json().get("results", [])
    for result in results:
        assert query.lower() in result.get("name", "").lower()

# NEDLADDNING
def test_download():
    response = requests.get(f"{BASE_URL}/download?file=/veermakers/tester.png")
    assert response.status_code in [200, 500]

def test_download_non_existent_file():
    response = requests.get(f"{BASE_URL}/download?file=/veermakers/nonexistent.png")
    assert response.status_code == 500

# WEBHOOK
def test_webhook_missing_challenge():
    response = requests.get(f"{BASE_URL}/dropbox_webhook")
    assert response.status_code == 400

@pytest.fixture
def mock_dropbox():
    """Mockar Dropbox API-anrop och simulerar en fil som läggs till vid synkning."""
    with patch("dropbox.Dropbox.files_list_folder") as mock_list_folder, \
         patch("dropbox.Dropbox.files_list_folder_continue") as mock_continue:

        mock_files = [
            type("FileMetadata", (), {
                "id": "123",
                "name": "mock_file.txt",
                "path_lower": "/mock_file.txt",
                "size": 1024,
                "client_modified": "2025-02-16T14:05:52Z"
            })
        ]
        
        mock_list_folder.return_value.entries = mock_files
        mock_continue.return_value.entries = mock_files

        yield mock_list_folder, mock_continue

# DATABAS

def test_sync_updates_database(mock_dropbox):
    """Testar att en ny fil läggs till i databasen efter synkronisering."""
    response = requests.post(f"{BASE_URL}/sync")
    assert response.status_code == 200

    response_json = response.json()
    if "expired_access_token" in response_json.get("status", ""):
        pytest.fail("Dropbox access token has expired. Renew it in the backend.")

    assert "Synkronisering klar." in response_json.get("status", "")

    list_response = requests.get(f"{BASE_URL}/list")
    assert list_response.status_code == 200
    files = list_response.json().get("files", [])
    assert any(f.get("name") == "mock_file.txt" for f in files)

def test_sync_removes_deleted_file(mock_dropbox):
    """Testar att en borttagen fil försvinner från databasen efter synkronisering."""
    response = requests.post(f"{BASE_URL}/sync")
    assert response.status_code == 200

    with patch("dropbox.Dropbox.files_list_folder_continue") as mock_delta:
        mock_delta.return_value.entries = [
            type("DeletedMetadata", (), {"path_lower": "/mock_file.txt"})
        ]

        response = requests.post(f"{BASE_URL}/sync")
        assert response.status_code == 200

        list_response = requests.get(f"{BASE_URL}/list")
        assert list_response.status_code == 200
        files = list_response.json().get("files", [])
        assert not any(f.get("name") == "mock_file.txt" for f in files)
