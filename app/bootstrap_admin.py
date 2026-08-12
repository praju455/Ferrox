from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db import SessionLocal
from app.models import User, UserRole


def bootstrap_admin() -> None:
    settings = get_settings()
    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        raise RuntimeError("BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD are required")
    email = settings.bootstrap_admin_email.strip().lower()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email,
                full_name="Ferrox Administrator",
                password_hash=hash_password(settings.bootstrap_admin_password),
                role=UserRole.admin,
            )
            db.add(user)
        else:
            user.password_hash = hash_password(settings.bootstrap_admin_password)
            user.role = UserRole.admin
            user.is_active = True
        db.commit()
        print(f"Administrator ready: {email}")


if __name__ == "__main__":
    bootstrap_admin()
