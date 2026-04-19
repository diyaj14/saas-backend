from cryptography.fernet import Fernet
import os
from dotenv import load_dotenv

load_dotenv()

# We use the ENCRYPTION_KEY you already have in your .env
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
fernet = Fernet(ENCRYPTION_KEY.encode())

def encrypt_token(token: str) -> str:
    return fernet.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    return fernet.decrypt(encrypted_token.encode()).decode()
