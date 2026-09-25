import uuid

from fastapi.testclient import TestClient
import pytest

from tests.helpers import access_token_cookie, create_test_user
from ubiblio import crud, models, schemas
from ubiblio.database import SessionLocal


@pytest.fixture
def client():
    from ubiblio.main import app

    with TestClient(app) as c:
        yield c


def _create_book(title: str):
    db = SessionLocal()
    try:
        crud.createBook(
            db,
            schemas.BookCreate(
                title=title,
                author="Test Author",
                owned=True,
                withdrawn=False,
                ebook=False,
            ),
        )
        return db.query(models.Book).filter(models.Book.title == title).first()
    finally:
        db.close()


def _delete_book(book_id: int):
    db = SessionLocal()
    try:
        crud.deleteBook(db, book_id)
    finally:
        db.close()


class TestAdminMediatedCirculation:
    def test_patron_cannot_checkout(self, client):
        title = f"circ-book-{uuid.uuid4().hex[:8]}"
        book = _create_book(title)
        try:
            with create_test_user() as patron:
                with access_token_cookie(client, patron):
                    response = client.post(
                        f"/withdraw/{book.id}",
                        data={"borrower": patron.username},
                        follow_redirects=False,
                    )
            assert response.status_code == 403
        finally:
            _delete_book(book.id)

    def test_admin_checks_out_for_patron(self, client):
        title = f"circ-book-{uuid.uuid4().hex[:8]}"
        book = _create_book(title)
        try:
            with create_test_user(is_admin=True) as admin:
                with create_test_user() as patron:
                    with access_token_cookie(client, admin):
                        response = client.post(
                            f"/withdraw/{book.id}",
                            data={"borrower": patron.username},
                            follow_redirects=False,
                        )
                    assert response.status_code == 303
                    db = SessionLocal()
                    try:
                        loaned = crud.getBookById(db, book.id)
                        assert loaned.withdrawn is True
                        assert loaned.withdrawnBy == patron.username
                    finally:
                        db.close()
        finally:
            _delete_book(book.id)

    def test_admin_creates_local_patron(self, client):
        username = f"patron_{uuid.uuid4().hex[:8]}"
        with create_test_user(is_admin=True) as admin:
            with access_token_cookie(client, admin):
                response = client.post(
                    "/createLocalUser",
                    data={"username": username, "password": "desk123"},
                    follow_redirects=False,
                )
        assert response.status_code == 303
        db = SessionLocal()
        try:
            created = crud.get_user_by_username(db, username)
            assert created is not None
            assert created.isAdmin is False
            crud.deleteUser(db, created.id)
        finally:
            db.close()
