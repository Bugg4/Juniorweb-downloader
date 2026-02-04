import os
import requests
from dotenv import load_dotenv

def test_notification():
    # Load environment variables from .env
    load_dotenv()
    
    topic = os.getenv("NTFY_TOPIC")
    
    if not topic:
        print("❌ Error: NTFY_TOPIC not found in .env file.")
        print("Please make sure you have NTFY_TOPIC=your_topic_name in your .env file.")
        return

    print(f"🚀 Sending test notification with attachment to topic: {topic}...")
    
    file_to_attach = "utils.py"
    
    try:
        with open(file_to_attach, "rb") as f:
            file_content = f.read()

        response = requests.post(
            f"https://ntfy.sh/{topic}",
            data=file_content,
            headers={
                "X-Title": "Test Attachment Notification",
                "X-Message": f"Attached file: {file_to_attach}",
                "X-Filename": file_to_attach,
                "X-Tags": "tada,robot,paperclip"
            }
        )
        response.raise_for_status()
        print(f"✅ Success! Notification with {file_to_attach} sent.")
        print(f"Response: {response.status_code}")
    except Exception as e:
        print(f"❌ Failed to send notification: {e}")

if __name__ == "__main__":
    test_notification()
