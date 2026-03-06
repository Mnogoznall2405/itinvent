import sys
from backend.services.mail_service import mail_service
from backend.database.session import SessionLocal
from backend.models.user import User

def main():
    db = SessionLocal()
    user = db.query(User).filter(User.is_active == True).first()

    if not user:
        print("No user found")
        sys.exit(1)

    print(f"Testing with user: {user.login} (ID: {user.id})")

    try:
        inbox = mail_service.get_inbox(user_id=user.id, limit=20)
        found = False
        for item in inbox.get('items', []):
            msg = mail_service.get_message(user_id=user.id, message_id=item['id'])
            if msg.get('attachments'):
                found_att = False
                for att in msg['attachments']:
                    if att.get('id'):
                        found = True
                        found_att = True
                        print(f"Found message {msg['id']} with attachment {att['name']} (ID: {att['id']})")
                        print(f"Trying to download attachment...")
                        res = mail_service.download_attachment(user_id=user.id, message_id=msg['id'], attachment_id=att['id'])
                        print("Download successful!", res[0], res[1], len(res[2]), "bytes")
                        break
                if found_att:
                    break
        if not found:
            print("No messages with attachments found in the recent inbox.")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
