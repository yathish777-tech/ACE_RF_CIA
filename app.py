import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from config import Config

# ── Shared extension instances ────────────────────────────────────────────────
from extensions import db, login_manager, mail

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # ── Init extensions ───────────────────────────────────────────────────
    db.init_app(app)
    mail.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view             = 'auth.login'
    login_manager.login_message          = 'Please log in to access this page.'
    login_manager.login_message_category = 'warning'

    # ── User loader ───────────────────────────────────────────────────────
    from models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # ── Blueprints ────────────────────────────────────────────────────────
    from routes.main          import main_bp
    from routes.auth          import auth_bp
    from routes.admin         import admin_bp
    from routes.user          import user_bp
    from routes.subject_staff import staff_bp
    from routes.tutor         import tutor_bp
    from routes.hod           import hod_bp
    from routes.coordinator   import coordinator_bp

    app.register_blueprint(auth_bp,        url_prefix='/auth')
    app.register_blueprint(main_bp)                              # handles '/'
    app.register_blueprint(admin_bp,       url_prefix='/admin')
    app.register_blueprint(user_bp,        url_prefix='/user')
    app.register_blueprint(staff_bp,       url_prefix='/staff')
    app.register_blueprint(tutor_bp,       url_prefix='/tutor')
    app.register_blueprint(hod_bp,         url_prefix='/hod')
    app.register_blueprint(coordinator_bp, url_prefix='/coordinator')

    # ── Ensure upload folder exists ───────────────────────────────────────
    upload_folder = os.path.join(app.root_path, 'uploads')
    os.makedirs(upload_folder, exist_ok=True)
    app.config.setdefault('UPLOAD_FOLDER', upload_folder)

    # ── Auto-create DB tables on first run ────────────────────────────────
    with app.app_context():
        db.create_all()

    return app


# ── Module-level app (used by email_utils lazy import) ────────────────────────
app = create_app()

if __name__ == '__main__':
    app.run(debug=True)