from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import crud, schemas
from ..database import SessionLocal
from ..dependencies import (
    get_rate_limiter, templates,
    admin_user, current_user,
)

router = APIRouter()


@router.get("/read/{bookId}", dependencies=[get_rate_limiter(times=1, seconds=1)], response_class=HTMLResponse)
async def book_read(bookId, request: Request, user: current_user):
    db = SessionLocal()
    try:
        readingListItem = schemas.readingListItemCreate(book=bookId, user_id=user.id)
        crud.readBook(db, readingListItem)
    finally:
        db.close()
    return RedirectResponse(url='/readingLists')


@router.get("/unread/{bookId}", dependencies=[get_rate_limiter(times=1, seconds=1)], response_class=HTMLResponse)
async def book_unread(bookId, request: Request, user: current_user):
    db = SessionLocal()
    try:
        crud.bookUnRead(db, bookId)
    finally:
        db.close()
    return RedirectResponse(url='/readingLists')


@router.get("/readingLists", dependencies=[get_rate_limiter(times=2, seconds=2)], response_class=HTMLResponse)
async def reading_list(request: Request, user: current_user):
    db = SessionLocal()
    try:
        readingList = crud.readingList(db, user.id)
        books = [crud.getBookById(db, i.book) for i in readingList]
    finally:
        db.close()
    context = {
        "books": books,
        "user": user,
        "request": request,
    }
    return templates.TemplateResponse(request, "readinglist.html", context)


def _book_schema(book, withdrawn: bool, withdrawn_by: str | None = None) -> schemas.Book:
    return schemas.Book(
        id=book.id, title=book.title, author=book.author, summary=book.summary,
        genre=book.genre, library=book.library, shelf=book.shelf, collection=book.collection,
        notes=book.notes, ISBN=book.ISBN, owned=book.owned, ebook=book.ebook,
        customField1=book.customField1, customField2=book.customField2,
        withdrawn=withdrawn, withdrawnBy=withdrawn_by,
    )


@router.get("/return/{bookId}", dependencies=[get_rate_limiter(times=1, seconds=1)], response_class=HTMLResponse)
async def book_return(bookId, request: Request, user: admin_user):
    db = SessionLocal()
    try:
        book = crud.getBookById(db, bookId)
        if book:
            crud.bookReturn(db, _book_schema(book, withdrawn=False, withdrawn_by=None))
    finally:
        db.close()
    return RedirectResponse(url='/withdrawn')


@router.get("/withdraw/{bookId}", dependencies=[get_rate_limiter(times=1, seconds=1)], response_class=HTMLResponse)
async def book_withdraw_get(bookId, request: Request, user: admin_user):
    return RedirectResponse(url=f'/bookDetails/{bookId}')


@router.post("/withdraw/{bookId}", dependencies=[get_rate_limiter(times=1, seconds=1)], response_class=HTMLResponse)
async def book_withdraw(bookId, request: Request, user: admin_user, borrower: str = Form(...)):
    borrower = (borrower or "").strip()
    db = SessionLocal()
    try:
        book = crud.getBookById(db, bookId)
        if not book:
            return RedirectResponse(url='/searchbooks', status_code=status.HTTP_303_SEE_OTHER)
        if book.withdrawn:
            return RedirectResponse(url=f'/bookDetails/{bookId}', status_code=status.HTTP_303_SEE_OTHER)
        patron = crud.get_user_by_username(db, borrower)
        if not patron:
            return RedirectResponse(url=f'/bookDetails/{bookId}', status_code=status.HTTP_303_SEE_OTHER)
        crud.bookWithdraw(db, _book_schema(book, withdrawn=True, withdrawn_by=patron.username))
    finally:
        db.close()
    return RedirectResponse(url='/withdrawn', status_code=status.HTTP_303_SEE_OTHER)


@router.get("/withdrawn", dependencies=[get_rate_limiter(times=2, seconds=2)], response_class=HTMLResponse)
async def withdrawn_list(request: Request, user: current_user):
    db = SessionLocal()
    try:
        books = list(crud.browseWithdrawn(db))
    finally:
        db.close()
    context = {
        "user": user,
        "books": books,
        "request": request,
    }
    return templates.TemplateResponse(request, "withdrawn.html", context)


@router.get("/wishlist", dependencies=[get_rate_limiter(times=2, seconds=2)], response_class=HTMLResponse)
async def wishlist(request: Request, user: current_user):
    db = SessionLocal()
    try:
        books = crud.browseWishlist(db)
    finally:
        db.close()
    context = {
        "user": user,
        "books": books,
        "request": request,
    }
    return templates.TemplateResponse(request, "wishlist.html", context)
