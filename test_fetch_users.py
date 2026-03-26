import os
from supabase import create_client

def main():
    url = "https://uzpmpjkkwapaohleejtt.supabase.co"
    key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV6cG1wamtrd2FwYW9obGVlanR0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI5NzkzMjksImV4cCI6MjA4ODU1NTMyOX0.vnmV6eC05k4BRMR3SgrJBrn5x0gb0_4wI9_L39pGfl0"
    sb = create_client(url, key)

    response = sb.table("review_log").select("user_id").limit(10).execute()
    print(set(item['user_id'] for item in response.data))

if __name__ == "__main__":
    main()
