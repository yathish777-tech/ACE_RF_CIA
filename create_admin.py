from app import app
from models import db, User

with app.app_context():
    user = User(
        name="Admin",
        email="admin@gmail.com",
        role="admin"
    )
    user.set_password("admin123")

    db.session.add(user)
    db.session.commit()

    print("Admin created successfully!")