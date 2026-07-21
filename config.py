import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'cia-retest-secret-key-2024')

    # ── MySQL ──────────────────────────────────────────────────────────────
<<<<<<< HEAD
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL','mysql+pymysql://root:12345@localhost/cia_rf_1')
=======
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL','mysql+pymysql://root:acecse@localhost/cia_rf_1')
>>>>>>> 97305f9825985f1f7603cf9af7bf80690728dfdb
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── Gmail SMTP (SSL port 465) ──────────────────────────────────────────
    
    # The key fix: MAIL_DEFAULT_SENDER must match MAIL_USERNAME
    MAIL_SERVER         = 'smtp.gmail.com'
    MAIL_PORT           = 465
    MAIL_USE_TLS        = False
    MAIL_USE_SSL        = True
    MAIL_USERNAME       = os.environ.get('MAIL_USERNAME',  'aceciaretest@gmail.com')
    MAIL_PASSWORD       = os.environ.get('MAIL_PASSWORD',  'wlkxbxyfcihtowma')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_USERNAME',  'aceciaretest@gmail.com')
    # ↑↑ THIS WAS THE MISSING LINE — Flask-Mail requires MAIL_DEFAULT_SENDER
    # to match MAIL_USERNAME for Gmail. Without it OTP emails silently fail.

   
    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")