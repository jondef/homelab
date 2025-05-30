import imaplib
import email
import subprocess
import time
import os
from sessions import TastyworksSession
from trader import execute_trade

username = 'jdefilla@gmail.com'
app_password = 'xmuo ywfb htnw nhfo'
imap_server = 'imap.gmail.com'

def connect_to_gmail():
    mail = imaplib.IMAP4_SSL(imap_server)
    mail.login(username, app_password)
    mail.select('inbox')
    return mail

def check_for_new_emails(mail):
    status, messages = mail.search(None, '(UNSEEN FROM "noreply@tradingview.com")')  # UNSEEN FROM ...
    if status == 'OK':
        if messages[0].split() > 0:
            with TastyworksSession(os.environ.get("TT_USERNAME"), os.environ.get("TT_PASSWORD")) as session:


                for num in messages[0].split():
                    # Fetch the email
                    status, msg = mail.fetch(num, '(RFC822)')

                    # Parse the email message
                    for response in msg:
                        if isinstance(response, tuple):
                            msg = email.message_from_bytes(response[1])

                            subject = msg.get('Subject')
                            body = msg.get_payload(decode=True).decode()

                            execute_trade(session, subject, body)

                    mail.store(num, '+FLAGS', '\\Seen')
    mail.close()
    mail.logout()




def main():
    while True:
        try:
            mail = connect_to_gmail()
            check_for_new_emails(mail)
            print("Retrying in 60 seconds...")
            time.sleep(60)  # Check every minute
        except Exception as e:
            print(f"Error: {e}")

if __name__ == '__main__':
    main()
