import os
from flask import Flask
from sqlalchemy import inspect, text
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
        user = User.query.get(int(user_id))
        if user:
            app.logger.info(
                '[auth:user-loader] current_user.id=%s role=%s secondary_role=%s',
                user.id, user.role, user.secondary_role
            )
        return user

    @app.context_processor
    def inject_permission_helpers():
        from utils.permissions import has_role, has_any_role, user_roles
        return {
            'has_role': has_role,
            'has_any_role': has_any_role,
            'user_roles': user_roles
        }
                  
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
        _ensure_runtime_columns()

    return app


def _ensure_runtime_columns():
    """Keep older local databases compatible with newly added columns."""
    inspector = inspect(db.engine)
    column_map = {
        table: {column['name'] for column in inspector.get_columns(table)}
        for table in ('seating_allotment', 'exam_attendance', 'halls', 'seating_allocation', 'hall_attendance')
        if inspector.has_table(table)
    }
    alter_statements = []
    if 'seating_allotment' in column_map and 'exam_date' not in column_map['seating_allotment']:
        alter_statements.append('ALTER TABLE seating_allotment ADD COLUMN exam_date DATE NULL')
    if 'exam_attendance' in column_map and 'exam_date' not in column_map['exam_attendance']:
        alter_statements.append('ALTER TABLE exam_attendance ADD COLUMN exam_date DATE NULL')
    if 'halls' in column_map:
        hall_columns = {
            'hall_name': 'VARCHAR(100) NULL',
            'hall_number': 'VARCHAR(20) NULL',
            'block': 'VARCHAR(50) NULL',
            'floor': 'VARCHAR(20) NULL',
            'capacity': 'INTEGER NULL',
            'is_special': 'BOOLEAN NOT NULL DEFAULT 0',
            'created_at': 'DATETIME NULL',
        }
        for column, definition in hall_columns.items():
            if column not in column_map['halls']:
                alter_statements.append(f'ALTER TABLE halls ADD COLUMN {column} {definition}')
    if 'seating_allocation' in column_map:
        allocation_columns = {
            'cia_id': 'INTEGER NULL',
            'hall_id': 'INTEGER NULL',
            'bench_position': 'INTEGER NULL',
            'seat_side': 'VARCHAR(10) NULL',
            'seat_label': 'VARCHAR(40) NULL',
            'row_group': 'INTEGER NULL',
            'col_number': 'INTEGER NULL',
            'student_reg_no': 'VARCHAR(30) NULL',
            'student_name': 'VARCHAR(100) NULL',
            'year': 'VARCHAR(20) NULL',
            'department': 'VARCHAR(100) NULL',
            'exam_date': 'DATE NULL',
            'generated_by': 'VARCHAR(100) NULL',
            'created_at': 'DATETIME NULL',
        }
        for column, definition in allocation_columns.items():
            if column not in column_map['seating_allocation']:
                alter_statements.append(f'ALTER TABLE seating_allocation ADD COLUMN {column} {definition}')
    if 'hall_attendance' in column_map:
        attendance_columns = {
            'cia_id': 'INTEGER NULL',
            'hall_id': 'INTEGER NULL',
            'student_reg_no': 'VARCHAR(30) NULL',
            'invigilator_staff_id': 'INTEGER NULL',
            'status': 'VARCHAR(10) NOT NULL DEFAULT "Present"',
            'exam_date': 'DATE NULL',
            'marked_at': 'DATETIME NULL',
        }
        for column, definition in attendance_columns.items():
            if column not in column_map['hall_attendance']:
                alter_statements.append(f'ALTER TABLE hall_attendance ADD COLUMN {column} {definition}')
    for statement in alter_statements:
        db.session.execute(text(statement))
    if alter_statements:
        db.session.commit()


# ── Module-level app (used by email_utils lazy import) ────────────────────────
app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
