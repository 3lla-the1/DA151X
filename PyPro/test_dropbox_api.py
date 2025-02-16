import requests
import pytest
from unittest.mock import patch

BASE_URL = "http://127.0.0.1:5001"  # Byt till ngrok-URL om du testar externt

def test_debug():
    response = requests.get(f"{BASE_URL}/debug")
    assert response.status_code == 200
    assert "Flask server fungerar" in response.json()["message"]

def test_list_files():
    response = requests.get(f"{BASE_URL}/list")
    assert response.status_code == 200
    assert isinstance(response.json()["files"], list)

def test_list_files_structure():
    # Testa att listan innehåller rätt struktur
    response = requests.get(f"{BASE_URL}/list")
    assert response.status_code == 200
    files = response.json()["files"]
    if files:  # Om det finns filer, kontrollera att strukturen stämmer
        assert "name" in files[0]
        assert "path" in files[0]
        assert "modified" in files[0]

# SÖKNING 
def test_search():
    response = requests.get(f"{BASE_URL}/search?q=TESTER")
    assert response.status_code == 200
    assert isinstance(response.json()["results"], list)

def test_search_no_results():
    response = requests.get(f"{BASE_URL}/search?q=DOES_NOT_EXIST")
    assert response.status_code == 200
    assert isinstance(response.json()["results"], list)
    assert len(response.json()["results"]) == 0  # Ska returnera en tom lista

def test_search_results_match_query():
    # Testa att sökresultaten matchar söktermen
    query = "TESTER"
    response = requests.get(f"{BASE_URL}/search?q={query}")
    assert response.status_code == 200
    results = response.json()["results"]
    for result in results:
        assert query.lower() in result["name"].lower()  # Filnamn ska matcha sökterm

# NEDLADDNING
def test_download():
    response = requests.get(f"{BASE_URL}/download?file=/veermakers/tester.png")
    assert response.status_code in [200, 500]  # 500 om filen inte finns

def test_download_non_existent_file():
    response = requests.get(f"{BASE_URL}/download?file=/veermakers/nonexistent.png")
    assert response.status_code == 500  # Ska returnera fel om filen inte finns

#WEBHOOK
def test_webhook_missing_challenge():
    response = requests.get(f"{BASE_URL}/dropbox_webhook")
    assert response.status_code == 400  # Borde returnera fel eftersom "challenge" saknas

def test_webhook_sync_update(mock_dropbox):
    #Testa att webhook-synkning hanterar en uppdaterad fil
    response = requests.post(f"{BASE_URL}/dropbox_webhook")
    assert response.status_code == 200
    assert "Synkronisering klar." in response.json()["status"]

#DATABAS
def test_sync_updates_database(mock_dropbox):
    #Testa att synkronisering faktiskt uppdaterar databasen
    """Testar att en ny fil läggs till i databasen efter synkronisering."""
    response = requests.post(f"{BASE_URL}/sync")
    assert response.status_code == 200
    assert "Synkronisering klar." in response.json()["status"]

    # Kontrollera att den nya filen finns i listan
    list_response = requests.get(f"{BASE_URL}/list")
    assert list_response.status_code == 200
    files = list_response.json()["files"]
    assert any(f["name"] == "mock_file.txt" for f in files)  # Filen ska finnas


def test_sync_removes_deleted_file(mock_dropbox):
    # Testa att en borttagen fil inte längre finns efter synkronisering
    """Testar att en borttagen fil försvinner från databasen efter synkronisering."""
    # Lägg först till en fil
    response = requests.post(f"{BASE_URL}/sync")
    assert response.status_code == 200

    # Mocka att filen nu tas bort
    with patch("dropbox.Dropbox.files_list_folder_continue") as mock_delta:
        mock_delta.return_value.entries = [
            type("DeletedMetadata", (), {"path_lower": "/mock_file.txt"})
        ]

        response = requests.post(f"{BASE_URL}/sync")
        assert response.status_code == 200

        # Kontrollera att filen inte längre finns
        list_response = requests.get(f"{BASE_URL}/list")
        assert list_response.status_code == 200
        files = list_response.json()["files"]
        assert not any(f["name"] == "mock_file.txt" for f in files)  # Filen ska vara borta


    

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

def test_sync_with_mock(mock_dropbox):
    """Testar synkronisering utan att anropa Dropbox API."""
    response = requests.post(f"{BASE_URL}/sync")
    assert response.status_code == 200
    assert "status" in response.json()