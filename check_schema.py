import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv(dotenv_path="../.env")
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SECRET_KEY")
sb = create_client(url, key)

# Let's inspect the first raw row
resp = sb.table("progress_sync").select("next_review").limit(1).execute()
print(repr(resp.data[0]['next_review']))
