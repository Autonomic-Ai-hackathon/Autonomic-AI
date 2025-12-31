# delete_collections.py
from google.cloud import firestore

# If running on Cloud Run / Cloud Functions / Cloud Shell (ADC), this is enough:
db = firestore.Client()

# If running locally with a service account, use this instead (same pattern as your seeder):
# from google.oauth2 import service_account
# creds = service_account.Credentials.from_service_account_file("./serviceAccountKey.json")
# db = firestore.Client(credentials=creds, project=creds.project_id)

COLLECTIONS_TO_DELETE = ["chats", "logs", "agents", "pointers"]

def delete_collection_recursive(collection_name: str, chunk_size: int = 5000) -> int:
    """
    Deletes every document in the collection AND all descendant subcollections.
    Returns the number of deleted documents.
    """
    col_ref = db.collection(collection_name)
    deleted_count = db.recursive_delete(col_ref, chunk_size=chunk_size)
    return deleted_count

def main():
    print("⚠️  DANGER: This will permanently delete Firestore data.")
    print("Collections:", ", ".join(COLLECTIONS_TO_DELETE))
    confirm = input("Type DELETE to continue: ").strip()

    if confirm != "DELETE":
        print("Cancelled.")
        return

    total = 0
    for name in COLLECTIONS_TO_DELETE:
        print(f"\nDeleting collection: {name}")
        deleted = delete_collection_recursive(name, chunk_size=5000)
        total += deleted
        print(f"Deleted {deleted} docs from '{name}' (including subcollections).")

    print(f"\n✅ Done. Total documents deleted: {total}")

if __name__ == "__main__":
    main()
